"""Portal picker: search the task's portal name, click the card, confirm.
Used both on entry (Inventory > Portals tab) and post-victory (after the
Victory screen's Select Portal button). Plus how a portal's stage screen is
entered afterwards."""

import threading

import core.runner as runner_module
from core.runner import MacroRunner
from core.runner_constants import DEFAULT_COORDS


def _runner():
    runner = object.__new__(MacroRunner)
    runner.clicked = []
    runner.backs = []
    runner.logged = []
    runner.typed = []
    runner._checkpoint = lambda stop_event: False
    runner._set_status = lambda **kw: None
    runner._log = lambda message: runner.logged.append(message)
    runner._spam_back_until_gone = lambda hwnd, stop_event: runner.backs.append(hwnd)
    runner._interruptible_sleep = lambda *a, **k: None
    runner.screenshots = []
    runner._save_debug_screenshot_unconditional = (
        lambda hwnd, name: runner.screenshots.append(name) or None)
    # A real MacroRunner always has these; the fixture skips __init__.
    runner._coords = dict(DEFAULT_COORDS)
    runner._click_ref = lambda hwnd, x, y, **k: runner.clicked.append(("ref", x, y))
    kb = type("Kb", (), {})()
    kb.combo = lambda *a, **k: runner.clicked.append(("combo", a))
    kb.tap = lambda vk, **k: runner.clicked.append(("tap", vk))
    kb.type_text = lambda text, **k: runner.clicked.append(("type", text)) or runner.typed.append(text)
    runner._keyboard = kb
    runner._click_found_image = (
        lambda hwnd, name, timeout, stop_event, **k: runner.clicked.append(("image", name)) or {"score": 0.99})
    # portal_activate is the one confirm here that goes through the verified
    # click instead (a dropped click there is invisible downstream) -- it
    # records the same way so the ordering assertions still read the same.
    runner._click_and_verify_gone = (
        lambda hwnd, stop_event, name, timeout, **k: runner.clicked.append(("image", name)) or True)
    runner._find_portal_card = (
        lambda hwnd, stop_event, candidates: runner.clicked.append(("card", candidates))
        or ({"score": 0.97, "cx": 500, "cy": 250}, candidates[0]))
    mouse = type("Mouse", (), {})()
    mouse.click = lambda x, y, **k: runner.clicked.append(("click", x, y))
    runner._mouse = mouse
    return runner


def test_post_victory_clicks_select_portal_then_searches_then_confirms(monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner_module.time, "sleep", lambda s: None)
    assert runner._select_portal_post_victory(1, threading.Event(), "summer") is True
    images = [call[1] for call in runner.clicked if call[0] == "image"]
    assert images == ["select_new_portal", "portal_search", "portal_activate"]
    assert runner.typed == ["summer"]


def test_the_name_is_typed_before_any_card_is_looked_for(monkeypatch):
    """The portals look alike in the picker; only the name printed on the card
    differs. So the card may only be searched for once the game's search has
    filtered the list by that name -- never before, where the generic crop
    would happily match whichever portal is at the front."""
    runner = _runner()
    monkeypatch.setattr(runner_module.time, "sleep", lambda s: None)
    assert runner._select_portal_on_picker(1, threading.Event(), "Frost Rift") is True
    order = [call[0] for call in runner.clicked]
    assert order.index("type") < order.index("card")
    assert order.count("card") == 1
    assert runner.typed == ["Frost Rift"]


def test_the_box_is_cleared_without_ever_pressing_ctrl(monkeypatch):
    """The box is cleared with END + backspaces, never Ctrl+A.

    The click into it is aimed at a crop of the placeholder word "Search...",
    so it can miss -- and a Ctrl that misses reaches Roblox, where it toggles
    the camera and leaves the rest of the run fighting the view. Reported
    live. Backspace and END do nothing when they miss.
    """
    runner = _runner()
    monkeypatch.setattr(runner_module.time, "sleep", lambda s: None)
    runner._select_portal_on_picker(1, threading.Event(), "summer")

    assert not any(call[0] == "combo" for call in runner.clicked), "no key combo may be sent here"
    taps = [call[1] for call in runner.clicked if call[0] == "tap"]
    assert runner_module.keys.VK_CONTROL not in taps
    assert taps and taps[0] == runner_module.keys.VK_END, "END first, so backspaces clear the whole field"
    assert taps.count(runner_module.keys.VK_BACK) >= len("summer")
    assert runner.typed == ["summer"]


def test_backs_out_when_the_card_is_missing(monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner_module.time, "sleep", lambda s: None)
    runner._find_portal_card = lambda hwnd, stop_event, candidates: (None, None)
    assert runner._select_portal_on_picker(1, threading.Event(), "summer") is False
    assert runner.backs == [1]
    assert any("Portal Name" in line for line in runner.logged), "say what to check"
    # The screen is the only way to tell a search that matched nothing from
    # a card no crop fits -- so it is saved, and before backing out of it.
    assert runner.screenshots == ["portal_card_not_found"]


def test_backs_out_when_the_confirm_is_missing(monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner_module.time, "sleep", lambda s: None)
    runner._click_and_verify_gone = (
        lambda hwnd, stop_event, name, timeout, **k: runner.clicked.append(("image", name)) or (
            name != "portal_activate"))
    assert runner._select_portal_post_victory(1, threading.Event(), "summer") is False
    assert runner.backs == [1]


def _enter_stage_runner(calls):
    runner = object.__new__(MacroRunner)
    runner._checkpoint = lambda stop_event: False
    runner._set_status = lambda **kw: None
    runner._log = lambda message: None
    runner._click_and_verify_gone = lambda *a, **k: (calls.append(("confirm", a)) or True)
    runner._click_start_and_wait_teleport = lambda *a, **k: (calls.append(("start", a)) or True)
    runner._click_enter_matchmaking = lambda *a, **k: True
    runner._wait_teleport_in = lambda *a, **k: True
    runner._interruptible_sleep = lambda seconds, stop_event=None: calls.append(("sleep", seconds))
    return runner


def test_enter_selected_stage_portal_leaps_straight_to_start():
    """Portal's activate step already landed on the Start screen -- no
    nav_select_stage confirm; the solo tail clicks nav_start directly."""
    calls = []
    runner = _enter_stage_runner(calls)
    task = {"play_mode": "solo", "mode": "portals", "map": "summer"}
    assert runner._enter_selected_stage(
        hwnd=1, stop_event=threading.Event(), task=task, mode="portals", coords={}, webhook={}) is True
    assert not any(c[0] == "confirm" for c in calls)
    assert any(c[0] == "start" for c in calls)


def test_enter_selected_stage_story_still_clicks_select_stage_confirm():
    """Non-portal modes still press the nav_select_stage confirm before Start."""
    calls = []
    runner = _enter_stage_runner(calls)
    task = {"play_mode": "solo", "mode": "story", "stage": "1"}
    assert runner._enter_selected_stage(
        hwnd=1, stop_event=threading.Event(), task=task, mode="story", coords={}, webhook={}) is True
    assert any(c[0] == "confirm" for c in calls)
    assert any(c[0] == "start" for c in calls)


def test_enter_selected_stage_lets_the_portal_stage_screen_settle_before_start():
    """Portals skip the confirm click that made every other mode wait for the
    stage screen to finish opening, so the Start search used to start against
    a screen still animating in -- and a Start button found mid-animation is
    clicked where it was, not where it ends up. Reported live over Remote
    Desktop as "it presses Start too early"."""
    calls = []
    runner = _enter_stage_runner(calls)
    task = {"play_mode": "solo", "mode": "portals"}
    assert runner._enter_selected_stage(
        hwnd=1, stop_event=threading.Event(), task=task, mode="portals", coords={}, webhook={}) is True

    order = [c[0] for c in calls]
    assert order.index("sleep") < order.index("start"), "the settle has to come before the Start search"
    assert ("sleep", runner_module.PORTAL_STAGE_SETTLE) in calls


def test_enter_selected_stage_does_not_stall_non_portal_modes():
    """Story already waits through its confirm click -- no extra settle."""
    calls = []
    runner = _enter_stage_runner(calls)
    task = {"play_mode": "solo", "mode": "story", "stage": "1"}
    runner._enter_selected_stage(
        hwnd=1, stop_event=threading.Event(), task=task, mode="story", coords={}, webhook={})
    assert not any(c[0] == "sleep" for c in calls)
