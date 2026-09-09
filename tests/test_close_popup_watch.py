"""Guards for which tasks watch for a full-screen "Click anywhere to close".

The panel covers the whole screen, Victory included, so a task that can hit
one and does not watch for it does not fail loudly -- it polls a hidden
result screen until MATCH_RESULT_TIMEOUT and loses the run. The watch is
gated (one extra image search per poll tick) so the gate itself is the thing
worth pinning down: it was hardcoded to Spirit City Act 3 on the assumption
that its boss intro was the only such panel, until Snowy Castle Act 3's
"Iron Wolf" secret-unit reveal turned up doing the same thing.
"""
import pytest

from core.runner import MacroRunner
from core import runner_constants as rc


@pytest.mark.parametrize("map_name", rc.CLOSE_POPUP_RAID_MAPS)
def test_every_listed_raid_map_watches_on_its_act_3(map_name):
    task = {"mode": "raid", "map": map_name, "stage": rc.CLOSE_POPUP_RAID_STAGE}

    assert MacroRunner._wants_close_popup_watch(task)


def test_snowy_castle_act_3_is_covered():
    """The case this gate was widened for -- Iron Wolf can drop at any point
    in the round, so the panel is not tied to a fixed moment in the fight the
    way Spirit City's cutscene is."""
    assert MacroRunner._wants_close_popup_watch(
        {"mode": "raid", "map": "Snowy Castle", "stage": "3"})


@pytest.mark.parametrize("stage", ["1", "2"])
@pytest.mark.parametrize("map_name", rc.CLOSE_POPUP_RAID_MAPS)
def test_the_other_acts_of_those_maps_do_not_watch(map_name, stage):
    """Only Act 3 throws the panel, and the watch costs a search per poll."""
    assert not MacroRunner._wants_close_popup_watch(
        {"mode": "raid", "map": map_name, "stage": stage})


@pytest.mark.parametrize("task", [
    {"mode": "story", "map": "Crimson Shore", "stage": "3"},
    {"mode": "raid", "map": "Some Future Raid", "stage": "3"},
    {"mode": "portal", "map": "Summer Portal", "stage": "3"},
    {"mode": "raid", "map": "Spirit City"},          # no stage at all
    {},
])
def test_unlisted_tasks_do_not_watch(task):
    assert not MacroRunner._wants_close_popup_watch(task)


def test_an_integer_stage_still_matches():
    """Task stages arrive as strings from the UI, but a task built in a test
    or migrated from older saved data can carry an int -- the gate compares
    str(stage) so both read the same."""
    assert MacroRunner._wants_close_popup_watch(
        {"mode": "raid", "map": "Spirit City", "stage": 3})


def test_listed_maps_are_real_raid_maps():
    """A typo here disables the watch silently: the name has to match the
    task's `map` value, which comes from TASK_DATA.raid.maps in ui/app.js."""
    import re
    from pathlib import Path

    app_js = (Path(__file__).resolve().parent.parent / "ui" / "app.js").read_text(encoding="utf-8")
    match = re.search(r"raid:\s*\{.*?maps:\s*\[(.*?)\]", app_js, re.S)
    assert match, "couldn't find TASK_DATA.raid.maps in ui/app.js"
    raid_maps = [a or b for a, b in re.findall(r"'([^']*)'|\"([^\"]*)\"", match.group(1))]

    assert set(rc.CLOSE_POPUP_RAID_MAPS) <= set(raid_maps)


def test_the_watched_stage_is_a_real_act():
    assert rc.CLOSE_POPUP_RAID_STAGE in rc.ACT_ORDER


# ---------------------------------------------------------------------------
# Actually dismissing the panel
# ---------------------------------------------------------------------------

def _popup_runner(monkeypatch, frames):
    """A runner whose close-panel search returns `frames` in order.

    Each entry is a match dict or None -- so a test can say "up, then gone"
    or "up, still up".
    """
    import core.runner as runner_module
    from core.runner_constants import DEFAULT_COORDS

    runner = object.__new__(MacroRunner)
    runner.events = []
    runner.logged = []
    runner._coords = dict(DEFAULT_COORDS)
    runner._log = lambda message: runner.logged.append(message)
    runner._debug_save = lambda *a, **k: None
    mouse = type("Mouse", (), {})()
    mouse.click = lambda x, y, **k: runner.events.append(("click", x, y))
    mouse.shuffle_click = lambda x, y, **k: runner.events.append(("shuffle", x, y))
    runner._mouse = mouse

    seen = iter(frames)
    monkeypatch.setattr(runner_module.vision, "find_image",
                        lambda hwnd, name, **k: next(seen, None))
    monkeypatch.setattr(runner_module.wm, "activate_window",
                        lambda hwnd: runner.events.append(("focus",)) or True)
    monkeypatch.setattr(runner_module.wm, "get_window_rect_screen",
                        lambda hwnd: (0, 0, 1152, 756))
    monkeypatch.setattr(runner_module.time, "sleep", lambda s: None)
    return runner


def test_nothing_happens_when_no_panel_is_up(monkeypatch):
    runner = _popup_runner(monkeypatch, [None])

    assert runner._click_close_popup_if_found(1) is False
    assert runner.events == []


def test_the_panel_click_takes_focus_and_hovers_in(monkeypatch):
    """Reported live: the cursor moved to the panel and nothing happened. A
    bare click_match neither focused the window nor approached with the real
    relative moves some Roblox buttons need before a click registers."""
    match = {"score": 0.98, "cx": 576, "cy": 700}
    runner = _popup_runner(monkeypatch, [match, None])

    assert runner._click_close_popup_if_found(1) is True
    kinds = [e[0] for e in runner.events]
    assert kinds[0] == "focus", "focus before the click, like every other click path"
    assert "shuffle" in kinds, "hover-in, not a bare jump-and-click"
    assert "click" not in kinds


def test_a_panel_that_survives_the_click_gets_the_screen_middle(monkeypatch):
    """The panel hides Victory, so a click that silently failed used to repeat
    every tick until the match timed out."""
    match = {"score": 0.98, "cx": 576, "cy": 700}
    runner = _popup_runner(monkeypatch, [match, match])

    assert runner._click_close_popup_if_found(1) is True
    points = [(e[1], e[2]) for e in runner.events if e[0] == "shuffle"]
    assert points[-1] == (runner._coords["screen_middle_x"], runner._coords["screen_middle_y"])
    assert any("still up" in line for line in runner.logged)


def test_a_panel_that_closes_is_not_clicked_twice(monkeypatch):
    match = {"score": 0.98, "cx": 576, "cy": 700}
    runner = _popup_runner(monkeypatch, [match, None])

    runner._click_close_popup_if_found(1)
    assert len([e for e in runner.events if e[0] == "shuffle"]) == 1
    assert not any("still up" in line for line in runner.logged)
