"""Auto Fishing: watch the rod for the whole round, cast on a timer.

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
    DEFAULT_COORDS, FISHING_CHECK_INTERVAL, FISHING_CLICK_INTERVAL,
    FISHING_MAX_ATTEMPTS_PER_MATCH, FISHING_MISS_CONFIRMATIONS, FISHING_MISS_RECHECK,
    FISHING_RETRY_DELAY, FISHING_ROD_IMAGE, FISHING_XP_IMAGE, FISHING_XP_REGION,
)

# Where the bar's rank label sits in the 1152x756 reference space.
_XP_BAR = {"score": 0.97, "cx": 1044, "cy": 721}


def _runner(monkeypatch, xp_frames=(), rod_found=True):
    runner = object.__new__(MacroRunner)
    runner.events = []
    runner.logged = []
    runner.xp_regions = []
    runner._coords = dict(DEFAULT_COORDS)
    runner._reset_fishing_for_match()
    runner._best_match_score = lambda hwnd, name, region=None: 0.42
    runner._debug_save = lambda hwnd, name, match: None
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

    def look(hwnd, name, **k):
        runner.xp_regions.append(k.get("region"))
        return next(seen, None)

    monkeypatch.setattr(runner_module.vision, "find_image", look)
    monkeypatch.setattr(runner_module.vision, "wait_for_image", look)
    monkeypatch.setattr(runner_module.vision, "ref_to_screen",
                        lambda hwnd, x, y: (int(x), int(y)))
    return runner


def _clock(monkeypatch, start=1000.0):
    """A clock the rod watch's pacing can be stepped through."""
    now = [start]
    monkeypatch.setattr(runner_module.time, "time", lambda: now[0])
    return now


def _look(runner, clock, times, step=FISHING_MISS_RECHECK):
    """Ask the rod watch ``times`` times, ``step`` seconds apart. Returns the
    last answer."""
    result = None
    for _ in range(times):
        result = runner._ensure_rod_out(1)
        clock[0] += step
    return result


def _rod_clicks(runner):
    return runner.events.count(("image", FISHING_ROD_IMAGE))


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
# Watching the rod
# ---------------------------------------------------------------------------

def test_the_rod_button_is_not_clicked_when_the_rod_is_already_out(monkeypatch):
    """Clicking it again would put the rod AWAY. The XP bar is checked first
    precisely so that cannot happen."""
    runner = _runner(monkeypatch, xp_frames=[_XP_BAR])

    assert runner._ensure_rod_out(1) is True
    assert _rod_clicks(runner) == 0


def test_the_rod_is_taken_out_once_the_bar_stays_away(monkeypatch):
    runner = _runner(monkeypatch, xp_frames=[None, None, None, _XP_BAR])
    clock = _clock(monkeypatch)

    assert _look(runner, clock, FISHING_MISS_CONFIRMATIONS) is True
    assert _rod_clicks(runner) == 1
    assert any("rod is out" in line for line in runner.logged)


def test_one_bad_look_never_touches_the_rod(monkeypatch):
    """The button toggles. A single frame the label did not match on -- a
    dark phase of the map was enough -- must not put a rod that is out away."""
    runner = _runner(monkeypatch, xp_frames=[_XP_BAR, None, None, _XP_BAR])
    clock = _clock(monkeypatch)

    assert runner._ensure_rod_out(1) is True
    clock[0] += FISHING_CHECK_INTERVAL
    assert _look(runner, clock, FISHING_MISS_CONFIRMATIONS) is True, (
        "casting carries on while a miss is being confirmed")
    assert _rod_clicks(runner) == 0


def test_a_rod_the_game_puts_away_mid_round_is_noticed(monkeypatch):
    """Checked once per match, a rod that went away stayed away until the
    next match -- in Infinite that is a hundred waves."""
    runner = _runner(monkeypatch, xp_frames=[_XP_BAR, None, None, None, _XP_BAR])
    clock = _clock(monkeypatch)

    assert runner._ensure_rod_out(1) is True
    clock[0] += FISHING_CHECK_INTERVAL
    assert _look(runner, clock, FISHING_MISS_CONFIRMATIONS) is True
    assert _rod_clicks(runner) == 1


def test_the_bar_is_not_searched_on_every_tick(monkeypatch):
    runner = _runner(monkeypatch, xp_frames=[_XP_BAR] * 5)
    clock = _clock(monkeypatch)

    runner._ensure_rod_out(1)
    for _ in range(10):
        clock[0] += 1
        assert runner._ensure_rod_out(1) is True

    assert len(runner.xp_regions) == 1, "looked at again only after FISHING_CHECK_INTERVAL"


def test_a_rod_click_that_never_shows_the_bar_is_retried_later(monkeypatch):
    """Fishing must never stop a run -- and one failed click must not stop
    fishing for the rest of it either: that cost a run 9.5 hours."""
    runner = _runner(monkeypatch, xp_frames=[None] * 4)
    clock = _clock(monkeypatch)

    assert _look(runner, clock, FISHING_MISS_CONFIRMATIONS) is False
    assert any("XP bar never showed" in line for line in runner.logged)
    assert any("just put it away" in line for line in runner.logged), (
        "the likeliest cause has to be named -- a wrong crop makes this click "
        "TOGGLE the rod off instead of on")
    assert any("Trying again in" in line for line in runner.logged)
    assert runner._fishing_paused is False


def test_nothing_is_clicked_again_before_the_retry_delay(monkeypatch):
    runner = _runner(monkeypatch, xp_frames=[None] * 20)
    clock = _clock(monkeypatch)

    _look(runner, clock, FISHING_MISS_CONFIRMATIONS)
    _look(runner, clock, 10, step=FISHING_RETRY_DELAY / 20)

    assert _rod_clicks(runner) == 1


def test_repeated_failures_pause_only_until_the_next_match(monkeypatch):
    runner = _runner(monkeypatch, xp_frames=[None] * 20)
    clock = _clock(monkeypatch)

    _look(runner, clock, FISHING_MISS_CONFIRMATIONS)      # first try fails
    clock[0] += FISHING_RETRY_DELAY
    _look(runner, clock, FISHING_MISS_CONFIRMATIONS)      # second try fails
    assert _rod_clicks(runner) == FISHING_MAX_ATTEMPTS_PER_MATCH
    assert runner._fishing_paused is True
    assert any("Pausing fishing until the next match" in line for line in runner.logged)

    clock[0] += FISHING_RETRY_DELAY
    _look(runner, clock, FISHING_MISS_CONFIRMATIONS)
    assert _rod_clicks(runner) == FISHING_MAX_ATTEMPTS_PER_MATCH, "paused -- the button is left alone"

    runner._reset_fishing_for_match()
    assert runner._fishing_paused is False


def test_a_missing_rod_button_is_retried_later(monkeypatch):
    runner = _runner(monkeypatch, xp_frames=[None] * 3, rod_found=False)
    clock = _clock(monkeypatch)

    assert _look(runner, clock, FISHING_MISS_CONFIRMATIONS) is False
    assert any("couldn't find the rod button" in line for line in runner.logged)


def test_a_missing_crop_is_reported_once_and_not_fatal(monkeypatch):
    runner = _runner(monkeypatch)
    monkeypatch.setattr(
        runner_module.vision, "find_image",
        lambda *a, **k: (_ for _ in ()).throw(runner_module.vision.TemplateNotFound("no crop")))

    assert runner._ensure_rod_out(1) is False
    assert any(FISHING_XP_IMAGE in line or "no crop" in line for line in runner.logged)


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


def test_the_failure_says_how_close_the_crop_got(monkeypatch):
    """\"Not found\" is ambiguous: 0.88 against a 0.90 threshold needs the
    sensitivity lowered, 0.30 is the wrong picture entirely."""
    runner = _runner(monkeypatch, xp_frames=[None] * 4)
    clock = _clock(monkeypatch)

    _look(runner, clock, FISHING_MISS_CONFIRMATIONS)

    assert any("best match 0.42" in line and "threshold 0.90" in line
               for line in runner.logged)


def test_fishing_says_when_it_is_working(monkeypatch):
    """Silence is indistinguishable from "it never even tried" -- which is
    exactly how a working setup looked when every success path was quiet."""
    runner = _runner(monkeypatch, xp_frames=[_XP_BAR])

    assert runner._ensure_rod_out(1) is True
    assert any("rod is already out" in line for line in runner.logged)


def test_a_missing_bar_is_said_before_the_rod_is_touched(monkeypatch):
    runner = _runner(monkeypatch, xp_frames=[None])
    _clock(monkeypatch)

    runner._ensure_rod_out(1)

    assert any("XP bar not seen" in line for line in runner.logged)
    assert _rod_clicks(runner) == 0


def test_the_bar_is_only_looked_for_in_the_bottom_right(monkeypatch):
    """Searched over the whole window at a lowered sensitivity, the rank label
    matched something elsewhere and reported "rod is already out" with the rod
    away -- so it was never taken out. Reported live."""
    runner = _runner(monkeypatch, xp_frames=[None, None, None, _XP_BAR])
    clock = _clock(monkeypatch)

    assert _look(runner, clock, FISHING_MISS_CONFIRMATIONS) is True
    assert runner.xp_regions == [FISHING_XP_REGION] * (FISHING_MISS_CONFIRMATIONS + 1), (
        "every look, and the check after the click")


def test_a_hit_says_how_good_it_was_and_where(monkeypatch):
    runner = _runner(monkeypatch, xp_frames=[_XP_BAR])

    runner._ensure_rod_out(1)

    assert any("rod is already out" in line and "score 0.97 at (1044, 721)" in line
               for line in runner.logged)


def test_the_failure_score_is_measured_where_the_bar_is_looked_for(monkeypatch):
    runner = _runner(monkeypatch, xp_frames=[None] * 4)
    clock = _clock(monkeypatch)
    measured = []
    runner._best_match_score = lambda hwnd, name, region=None: measured.append(region) or 0.42

    _look(runner, clock, FISHING_MISS_CONFIRMATIONS)

    assert measured == [FISHING_XP_REGION]


def test_the_rod_watch_starts_fresh_every_match_and_every_run():
    """MacroRunner is a module-level singleton -- state left over from a
    previous match or run once kept fishing off until the app restarted."""
    import inspect

    assert "_reset_fishing_for_match" in inspect.getsource(MacroRunner._play_one_match)
    assert "_reset_fishing_for_match" in inspect.getsource(MacroRunner._run)


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
