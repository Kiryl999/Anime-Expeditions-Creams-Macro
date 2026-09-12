"""Portal picker: search Summer, click the tier card, confirm -- the extra
step that makes the Portal event kind specialized. Used both on entry (after
the Portal kind card) and post-victory (after the Victory screen's Select
Portal button)."""

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
    # A real MacroRunner always has these; the fixture skips __init__.
    runner._coords = dict(DEFAULT_COORDS)
    runner._click_ref = lambda hwnd, x, y, **k: runner.clicked.append(("ref", x, y))
    kb = type("Kb", (), {})()
    kb.combo = lambda *a, **k: runner.clicked.append(("combo", a))
    kb.tap = lambda vk, **k: runner.clicked.append(("tap", vk))
    kb.type_text = lambda text, **k: runner.typed.append(text)
    runner._keyboard = kb
    runner._click_found_image = (
        lambda hwnd, name, timeout, stop_event, **k: runner.clicked.append(("image", name)) or {"score": 0.99})
    # The tier card no longer goes through _click_found_image -- it shares
    # PortalsOp._find_portal_card with the Inventory lead-in.
    runner._find_portal_card = (
        lambda hwnd, stop_event, candidates: runner.clicked.append(("card", candidates))
        or ({"score": 0.97, "cx": 500, "cy": 250}, candidates[0]))
    # The search path by default -- the "card already listed" shortcut is
    # tested on its own below.
    runner._peek_portal_card = lambda hwnd, stop_event, candidates: (None, None)
    mouse = type("Mouse", (), {})()
    mouse.click = lambda x, y, **k: runner.clicked.append(("click", x, y))
    runner._mouse = mouse
    return runner


def test_select_summer_portal_entry_skips_select_new_portal(monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner_module.time, "sleep", lambda s: None)
    assert runner._select_summer_portal(hwnd=1, stop_event=threading.Event(), entry=True) is True
    images = [call[1] for call in runner.clicked if call[0] == "image"]
    assert images == ["portal_search", "portal_activate"]
    assert "select_new_portal" not in images
    assert ("card", ("summer_portal",)) in runner.clicked
    assert runner.typed == ["summer"]


def test_select_summer_portal_post_victory_clicks_select_new_portal_first(monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner_module.time, "sleep", lambda s: None)
    assert runner._select_summer_portal(hwnd=1, stop_event=threading.Event(), entry=False) is True
    images = [call[1] for call in runner.clicked if call[0] == "image"]
    assert images == ["select_new_portal", "portal_search", "portal_activate"]
    assert ("card", ("summer_portal",)) in runner.clicked
    assert runner.typed == ["summer"]


def test_select_summer_portal_clears_the_box_without_ever_pressing_ctrl(monkeypatch):
    """The box is cleared with HOME + backspaces, never Ctrl+A.

    The click into it is aimed at a crop of the placeholder word "Search...",
    so it can miss -- and a Ctrl that misses reaches Roblox, where it toggles
    the camera and leaves the rest of the run fighting the view. Reported
    live. Backspace and HOME do nothing when they miss.
    """
    runner = _runner()
    monkeypatch.setattr(runner_module.time, "sleep", lambda s: None)
    runner._select_summer_portal(hwnd=1, stop_event=threading.Event(), entry=True)

    assert not any(call[0] == "combo" for call in runner.clicked), "no key combo may be sent here"
    taps = [call[1] for call in runner.clicked if call[0] == "tap"]
    assert runner_module.keys.VK_CONTROL not in taps
    assert taps and taps[0] == runner_module.keys.VK_HOME, "HOME first, so backspaces clear the whole field"
    assert taps.count(runner_module.keys.VK_BACK) >= len("summer")
    assert runner.typed == ["summer"]


def test_select_summer_portal_backs_out_when_tier_card_missing(monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner_module.time, "sleep", lambda s: None)
    runner._find_portal_card = lambda hwnd, stop_event, candidates: (None, None)
    assert runner._select_summer_portal(hwnd=1, stop_event=threading.Event(), entry=True) is False
    assert runner.backs == [1]


def test_select_summer_portal_backs_out_when_confirm_missing(monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner_module.time, "sleep", lambda s: None)
    runner._click_found_image = (
        lambda hwnd, name, timeout, stop_event, **k: runner.clicked.append(("image", name)) or (
            None if name == "portal_activate" else {"score": 0.99}))
    assert runner._select_summer_portal(hwnd=1, stop_event=threading.Event(), entry=False) is False
    assert runner.backs == [1]


def test_select_summer_portal_skips_the_search_when_the_card_is_already_listed(monkeypatch):
    """One portal owned: the tier card is listed before anything is typed, so
    the box is never touched and the card is clicked straight away."""
    runner = _runner()
    monkeypatch.setattr(runner_module.time, "sleep", lambda s: None)
    card = {"score": 0.98, "cx": 290, "cy": 255}
    runner._peek_portal_card = lambda hwnd, stop_event, candidates: (card, "summer_portal")
    clicked = []
    monkeypatch.setattr(runner_module.vision, "click_match",
                        lambda mouse, hwnd, match: clicked.append(match))

    assert runner._select_summer_portal(hwnd=1, stop_event=threading.Event(), entry=False) is True
    images = [call[1] for call in runner.clicked if call[0] == "image"]
    assert images == ["select_new_portal", "portal_activate"], "no portal_search click"
    assert runner.typed == []
    assert not any(call[0] == "card" for call in runner.clicked), "no card search"
    assert clicked == [card]
    assert any("skipping the search" in line for line in runner.logged)


def _enter_stage_runner(calls):
    runner = object.__new__(MacroRunner)
    runner._checkpoint = lambda stop_event: False
    runner._set_status = lambda **kw: None
    runner._log = lambda message: None
    runner._click_and_verify_gone = lambda *a, **k: (calls.append(("confirm", a)) or True)
    runner._click_start_and_wait_teleport = lambda *a, **k: (calls.append(("start", a)) or True)
    runner._click_enter_matchmaking = lambda *a, **k: True
    runner._wait_teleport_in = lambda *a, **k: True
    return runner


def test_enter_selected_stage_portal_leaps_straight_to_start():
    """Portal's activate step already landed on the Start screen -- no
    nav_select_stage confirm; the solo tail clicks nav_start directly."""
    calls = []
    runner = _enter_stage_runner(calls)
    task = {"play_mode": "solo", "mode": "event", "stage": "portal"}
    assert runner._enter_selected_stage(
        hwnd=1, stop_event=threading.Event(), task=task, mode="event", coords={}, webhook={}) is True
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
