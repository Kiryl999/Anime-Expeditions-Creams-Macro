"""Auto Fishing: rod out once, then cast on a timer while the round runs.

Casting is a plain left-click on water, so the feature is deliberately thin.
The parts worth pinning down are the ones that can quietly ruin a round: the
rod button toggles (clicking it while the rod is out puts it away), and a cast
landing between a Place Unit block's select and place steps drops the unit in
the water.

Positioning is out of scope on purpose -- the player parks the character with
their own Walk Path block, which already re-runs after a Challenge interleave.
"""
import threading

import pytest

import core.runner as runner_module
from core.runner import MacroRunner
from core.runner_constants import (
    DEFAULT_COORDS, FISHING_CLICK_INTERVAL, FISHING_ROD_IMAGE, FISHING_XP_IMAGE,
)


def _runner(monkeypatch, xp_frames=(), rod_found=True):
    runner = object.__new__(MacroRunner)
    runner.events = []
    runner.logged = []
    runner._coords = dict(DEFAULT_COORDS)
    runner._fishing_rod_attempted = False
    runner._fishing_gave_up = False
    runner._best_match_score = lambda hwnd, name: 0.42
    runner._save_debug_screenshot_unconditional = lambda hwnd, name: None
    runner._log = lambda message: runner.logged.append(message)
    runner._set_status = lambda **kw: None
    runner._checkpoint = lambda stop: False
    runner._click_found_image = (
        lambda hwnd, name, timeout, stop, **k:
        runner.events.append(("image", name)) or ({"score": 0.99} if rod_found else None))
    mouse = type("Mouse", (), {})()
    mouse.click = lambda x, y, **k: runner.events.append(("click", x, y))
    runner._mouse = mouse

    seen = iter(xp_frames)
    monkeypatch.setattr(runner_module.vision, "find_image",
                        lambda hwnd, name, **k: next(seen, None))
    monkeypatch.setattr(runner_module.vision, "wait_for_image",
                        lambda hwnd, name, **k: next(seen, None))
    monkeypatch.setattr(runner_module.vision, "ref_to_screen",
                        lambda hwnd, x, y: (int(x), int(y)))
    return runner


# ---------------------------------------------------------------------------
# Reading the task
# ---------------------------------------------------------------------------

def test_fishing_is_off_without_the_toggle():
    assert MacroRunner._fishing_point({"fishing_x": 500, "fishing_y": 400}) is None


def test_fishing_is_off_without_a_point():
    """The toggle alone cannot aim at anything."""
    assert MacroRunner._fishing_point({"fishing": True}) is None
    assert MacroRunner._fishing_point({"fishing": True, "fishing_x": 500}) is None


def test_a_configured_task_yields_its_point():
    assert MacroRunner._fishing_point(
        {"fishing": True, "fishing_x": 500, "fishing_y": 400}) == (500, 400)


def test_the_point_is_per_task_not_shared():
    """Two tasks on two maps carry two points -- the reason this is not a
    global Macro Coordinate."""
    a = {"fishing": True, "fishing_x": 500, "fishing_y": 400}
    b = {"fishing": True, "fishing_x": 120, "fishing_y": 660}

    assert MacroRunner._fishing_point(a) != MacroRunner._fishing_point(b)


@pytest.mark.parametrize("task, expected", [
    ({}, FISHING_CLICK_INTERVAL),
    ({"fishing_interval": 10}, 10.0),
    ({"fishing_interval": "12"}, 12.0),
    ({"fishing_interval": "nonsense"}, FISHING_CLICK_INTERVAL),
    ({"fishing_interval": 0}, FISHING_CLICK_INTERVAL),   # falsy -> default
    ({"fishing_interval": -5}, 1.0),                     # clamped, never a busy loop
])
def test_the_interval_is_configurable_with_a_sane_floor(task, expected):
    assert MacroRunner._fishing_interval(task) == expected


# ---------------------------------------------------------------------------
# Getting the rod out
# ---------------------------------------------------------------------------

def test_the_rod_button_is_not_clicked_when_the_rod_is_already_out(monkeypatch):
    """Clicking it again would put the rod AWAY. The XP bar is checked first
    precisely so that cannot happen."""
    runner = _runner(monkeypatch, xp_frames=[{"score": 0.97}])

    assert runner._ensure_rod_out(1) is True
    assert not any(e[0] == "image" for e in runner.events)


def test_the_rod_is_taken_out_when_the_bar_is_absent(monkeypatch):
    runner = _runner(monkeypatch, xp_frames=[None, {"score": 0.97}])

    assert runner._ensure_rod_out(1) is True
    assert ("image", FISHING_ROD_IMAGE) in runner.events


def test_a_rod_click_that_never_shows_the_bar_gives_up_quietly(monkeypatch):
    """Fishing must never be able to stop a run -- it reports and steps aside."""
    runner = _runner(monkeypatch, xp_frames=[None, None])

    assert runner._ensure_rod_out(1) is False
    assert any("XP bar never showed" in line for line in runner.logged)
    assert any("just put it away" in line for line in runner.logged), (
        "the likeliest cause has to be named -- a wrong crop makes this click "
        "TOGGLE the rod off instead of on")


def test_a_missing_rod_button_gives_up_quietly(monkeypatch):
    runner = _runner(monkeypatch, xp_frames=[None], rod_found=False)

    assert runner._ensure_rod_out(1) is False
    assert any("couldn't find the rod button" in line for line in runner.logged)


def test_a_missing_crop_is_reported_once_and_not_fatal(monkeypatch):
    runner = _runner(monkeypatch)
    monkeypatch.setattr(
        runner_module.vision, "find_image",
        lambda *a, **k: (_ for _ in ()).throw(runner_module.vision.TemplateNotFound("no crop")))

    assert runner._ensure_rod_out(1) is False
    assert any(FISHING_XP_IMAGE in line or "no crop" in line for line in runner.logged)


# ---------------------------------------------------------------------------
# Casting
# ---------------------------------------------------------------------------

def test_the_first_tick_casts_immediately(monkeypatch):
    runner = _runner(monkeypatch)
    runner._last_fishing_cast_at = 0.0

    runner._tick_fishing(1, (500, 400), 6.0)

    assert ("click", 500, 400) in runner.events


def test_a_cast_inside_the_interval_is_skipped(monkeypatch):
    import time

    runner = _runner(monkeypatch)
    runner._last_fishing_cast_at = time.time()

    runner._tick_fishing(1, (500, 400), 6.0)

    assert runner.events == []


def test_the_interval_is_measured_from_the_last_cast(monkeypatch):
    import time

    runner = _runner(monkeypatch)
    runner._last_fishing_cast_at = time.time() - 7.0

    runner._tick_fishing(1, (500, 400), 6.0)

    assert ("click", 500, 400) in runner.events
    assert runner._last_fishing_cast_at == pytest.approx(time.time(), abs=1.0)


def test_the_cast_goes_through_reference_space():
    """Stored points are reference-space; the click has to be converted or it
    lands wrong on any window that is not exactly 1152x756."""
    import inspect

    source = inspect.getsource(MacroRunner._tick_fishing)
    assert "ref_to_screen" in source


# ---------------------------------------------------------------------------
# Not getting in the way
# ---------------------------------------------------------------------------

def test_the_cast_is_held_back_while_other_clicks_happen():
    """A Place Unit block is select-then-place; a cast between those two steps
    puts the unit in the water. The poll loop therefore casts last and only
    when nothing else clicked in that tick."""
    import inspect

    source = inspect.getsource(MacroRunner._wait_for_match_result)
    assert "clicked_something" in source and "block_acted" in source
    cast = source.index("_tick_fishing")
    for earlier in ("_run_battle_blocks_tick", "_take_portal_offer_if_found",
                    "_click_close_popup_if_found"):
        assert source.index(earlier) < cast, f"{earlier} must run before a cast"


def test_both_crops_have_a_folder_to_put_them_in():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "Assets" / "ui"
    for name in (FISHING_ROD_IMAGE, FISHING_XP_IMAGE):
        assert (root / name).is_dir(), f"{name} needs a folder for its crop"


def test_the_ui_default_interval_matches_the_backend():
    """DEFAULT_FISHING_INTERVAL in ui/app.js seeds new tasks; a task saved with
    the JS default has to mean the same thing the runner falls back to."""
    import re
    from pathlib import Path

    app_js = (Path(__file__).resolve().parent.parent / "ui" / "app.js").read_text(encoding="utf-8")
    match = re.search(r"const DEFAULT_FISHING_INTERVAL = (\d+)", app_js)
    assert match, "couldn't find DEFAULT_FISHING_INTERVAL in ui/app.js"
    assert float(match.group(1)) == FISHING_CLICK_INTERVAL


def test_the_rod_button_is_clicked_at_most_once_per_match(monkeypatch):
    """The button TOGGLES. A second click on a rod that did come out puts it
    away again, and nothing on screen can tell those two states apart -- so
    one attempt is all there is, whatever comes of it."""
    runner = _runner(monkeypatch, xp_frames=[None, None, None, None, None, None])

    for _ in range(3):
        runner._ensure_rod_out(1)

    rod_clicks = [e for e in runner.events if e == ("image", FISHING_ROD_IMAGE)]
    assert len(rod_clicks) == 1


def test_a_missing_crop_is_logged_once_not_every_tick(monkeypatch):
    """This runs on every poll of every fishing round -- a log line per tick
    would bury the run."""
    runner = _runner(monkeypatch)
    monkeypatch.setattr(
        runner_module.vision, "find_image",
        lambda *a, **k: (_ for _ in ()).throw(runner_module.vision.TemplateNotFound("no crop")))

    for _ in range(5):
        runner._ensure_rod_out(1)

    assert len(runner.logged) == 1


def test_the_rod_is_checked_inside_the_match_not_before_it():
    """The XP bar is in-game HUD and is not up before the round runs. Checking
    too early reported "rod is away" while it was out, and the click that
    followed put it away -- reported live."""
    import inspect

    assert "_ensure_rod_out" not in inspect.getsource(MacroRunner._play_one_match)
    assert "_ensure_rod_out" in inspect.getsource(MacroRunner._wait_for_match_result)


def test_the_rod_is_only_reached_for_when_a_cast_would_follow():
    """No point taking a rod out in a tick that is already busy -- and the rod
    check is an image search of its own."""
    import inspect

    source = inspect.getsource(MacroRunner._wait_for_match_result)
    guard = source.index("if fishing_point and not clicked_something and not block_acted:")
    assert source.index("_ensure_rod_out") > guard


def test_a_failed_attempt_stops_fishing_for_the_whole_run(monkeypatch):
    """One click per MATCH is not enough. The button toggles, so match 1 puts
    the rod away, match 2 takes it out, match 3 puts it away again -- an
    alternating flip that is worse than not fishing. Reported live."""
    runner = _runner(monkeypatch, xp_frames=[None, None])

    assert runner._ensure_rod_out(1) is False
    assert runner._fishing_gave_up is True

    # A later match resets the per-match flag; the run-scoped one must not be.
    runner._fishing_rod_attempted = False
    runner.events.clear()
    monkeypatch.setattr(runner_module.vision, "wait_for_image", lambda *a, **k: None)

    assert runner._ensure_rod_out(1) is False
    assert not any(e == ("image", FISHING_ROD_IMAGE) for e in runner.events), (
        "the rod button must not be touched again after giving up")


def test_the_failure_says_how_close_the_crop_got(monkeypatch):
    """\"Not found\" is ambiguous: 0.88 against a 0.90 threshold needs the
    sensitivity lowered, 0.30 is the wrong picture entirely."""
    runner = _runner(monkeypatch, xp_frames=[None, None])

    runner._ensure_rod_out(1)

    assert any("best match 0.42" in line and "threshold 0.90" in line
               for line in runner.logged)


def test_the_bar_is_waited_for_before_deciding_the_rod_is_away():
    """A single look can land on a frame where the HUD has not drawn yet, and
    the cost of a wrong answer is the rod being put away."""
    import inspect

    source = inspect.getsource(MacroRunner._ensure_rod_out)
    check = source.index("FISHING_XP_IMAGE")
    assert "wait_for_image" in source[:check + 200]
    assert "find_image(" not in source, "a one-shot look is what caused the live failure"


def test_fishing_says_when_it_is_working(monkeypatch):
    """Silence is indistinguishable from "it never even tried" -- which is
    exactly how a working setup looked when every success path was quiet."""
    runner = _runner(monkeypatch, xp_frames=[{"score": 0.97}])

    assert runner._ensure_rod_out(1) is True
    assert any("rod is already out" in line for line in runner.logged)


def test_the_first_cast_is_announced_and_the_rest_are_not(monkeypatch):
    """One line per cast would be ~30 a round; none at all leaves no evidence
    the feature ran."""
    runner = _runner(monkeypatch)
    runner._last_fishing_cast_at = 0.0

    runner._tick_fishing(1, (500, 400), 6.0)
    first = len(runner.logged)
    assert first == 1 and "casting at (500, 400)" in runner.logged[0]

    runner._last_fishing_cast_at -= 10.0     # next cast is due
    runner._tick_fishing(1, (500, 400), 6.0)

    assert len(runner.logged) == first, "only the first cast of a match talks"


def test_giving_up_is_cleared_when_a_new_run_starts():
    """MacroRunner is a module-level singleton, so a run-scoped flag that is
    only set in __init__ survives until the whole app restarts -- which is how
    one failed rod attempt silently disabled fishing for good."""
    import inspect

    source = inspect.getsource(MacroRunner._run)
    assert "_fishing_gave_up = False" in source
