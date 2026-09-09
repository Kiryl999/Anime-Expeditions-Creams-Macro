"""Aiming and clearing the portal picker's search box.

Two live failures drove this. The box is aimed at the shipped `portal_search`
crop -- the 47x10px placeholder word "Search..." at the LEFT end of the bar --
and `_click_found_image` clicks a match's centre, so on a layout where the bar
sits differently the click lands outside the field ("clicks too far left").
The macro then typed into nothing. Worse, the clearing step was Ctrl+A, and a
Ctrl that misses the field reaches Roblox, where it toggles the camera and
leaves the rest of the run fighting the view.
"""
import threading

import core.runner_portals as portal_module
from core import keys
from core.runner import MacroRunner
from core.runner_constants import DEFAULT_COORDS, PORTAL_SEARCH_CLEAR_KEYS


def _runner(coords=None):
    runner = object.__new__(MacroRunner)
    runner.events = []
    runner.logged = []
    runner._coords = dict(DEFAULT_COORDS, **(coords or {}))
    runner._checkpoint = lambda stop: False
    runner._set_status = lambda **kw: None
    runner._log = lambda message: runner.logged.append(message)
    runner._spam_back_until_gone = lambda hwnd, stop: None
    runner._click_ref = lambda hwnd, x, y, **k: runner.events.append(("ref", x, y))
    runner._click_found_image = (
        lambda hwnd, name, timeout, stop, **k:
        runner.events.append(("image", name)) or {"score": 0.99})
    kb = type("Kb", (), {})()
    kb.combo = lambda *a, **k: runner.events.append(("combo", a))
    kb.tap = lambda vk, **k: runner.events.append(("tap", vk))
    kb.type_text = lambda text, **k: runner.events.append(("type", text))
    runner._keyboard = kb
    return runner


def test_auto_falls_back_to_the_shipped_crop():
    """With no override saved, behaviour is unchanged: match the crop inside
    the search region and click it."""
    runner = _runner()

    assert runner._focus_portal_search(1, threading.Event()) is True
    assert ("image", "portal_search") in runner.events
    assert not any(e[0] == "ref" for e in runner.events)


def test_a_saved_point_wins_over_the_crop():
    """The override is the whole fix for a crop whose centre misses the
    field -- so it must not fall back to the image search."""
    runner = _runner({"portal_search_x": 470, "portal_search_y": 181})

    assert runner._focus_portal_search(1, threading.Event()) is True
    assert ("ref", 470, 181) in runner.events
    assert not any(e[0] == "image" for e in runner.events)


def test_a_half_set_point_is_ignored():
    """One axis alone cannot aim anything; _optional_cxy treats it as unset
    rather than pairing it with a guess."""
    runner = _runner({"portal_search_x": 470})

    assert runner._focus_portal_search(1, threading.Event()) is True
    assert ("image", "portal_search") in runner.events


def test_ctrl_is_never_pressed():
    """The safety-critical one. Ctrl reaches Roblox when the click misses and
    changes the camera view, which no run recovers from on its own."""
    runner = _runner()

    runner._focus_portal_search(1, threading.Event())

    assert not any(e[0] == "combo" for e in runner.events)
    assert keys.VK_CONTROL not in [e[1] for e in runner.events if e[0] == "tap"]


def test_the_field_is_cleared_from_the_start_of_the_text():
    """HOME first: a click can land mid-text, and backspaces alone would then
    leave whatever sat to the right of the cursor in the box."""
    runner = _runner()

    runner._focus_portal_search(1, threading.Event())

    taps = [e[1] for e in runner.events if e[0] == "tap"]
    assert taps[0] == keys.VK_HOME
    assert taps.count(keys.VK_BACK) == PORTAL_SEARCH_CLEAR_KEYS


def test_a_missing_search_box_fails_loudly_and_says_what_to_do():
    runner = _runner()
    runner._click_found_image = lambda *a, **k: None

    assert runner._focus_portal_search(1, threading.Event()) is False
    assert any("Macro Coordinates" in line for line in runner.logged)
    # Nothing typed into a field that was never focused.
    assert not any(e[0] in ("tap", "type", "combo") for e in runner.events)


def test_both_portal_lead_ins_go_through_it(monkeypatch):
    """The Event kind and the Inventory tab reach the same picker; a fix in
    one that skips the other is how this drifted apart in the first place."""
    import core.runner_event as event_module
    import inspect

    for func in (portal_module.PortalsOp._select_portal_on_picker,
                 event_module.EventOps._select_summer_portal):
        assert "_focus_portal_search" in inspect.getsource(func)
        assert "VK_CONTROL" not in inspect.getsource(func)


# ---------------------------------------------------------------------------
# The card-list box
# ---------------------------------------------------------------------------

def test_the_built_in_box_is_used_when_nothing_is_saved():
    from core.runner_constants import PORTAL_SEARCHES

    runner = _runner()

    assert runner._portal_list_region() == tuple(int(v) for v in PORTAL_SEARCHES["portals"])


def test_a_saved_box_replaces_the_built_in_one():
    runner = _runner({"portal_list_x": 533, "portal_list_y": 208,
                      "portal_list_w": 343, "portal_list_h": 88})

    assert runner._portal_list_region() == (533, 208, 343, 88)


def test_a_half_set_box_falls_back_instead_of_guessing():
    from core.runner_constants import PORTAL_SEARCHES

    runner = _runner({"portal_list_x": 533, "portal_list_y": 208})

    assert runner._portal_list_region() == tuple(int(v) for v in PORTAL_SEARCHES["portals"])


def test_a_zero_sized_box_falls_back():
    """Width or height of zero would match nothing at all, which reads as
    'the card is gone' rather than 'your box is wrong'."""
    from core.runner_constants import PORTAL_SEARCHES

    runner = _runner({"portal_list_x": 533, "portal_list_y": 208,
                      "portal_list_w": 0, "portal_list_h": 88})

    assert runner._portal_list_region() == tuple(int(v) for v in PORTAL_SEARCHES["portals"])


def test_the_card_search_looks_in_the_saved_box(monkeypatch):
    """The whole point of the override: the first pass has to hit, so no pick
    pays the fallback timeout any more."""
    import core.runner_portals as portal_module

    runner = _runner({"portal_list_x": 533, "portal_list_y": 208,
                      "portal_list_w": 343, "portal_list_h": 88})
    regions = []

    def fake_wait_any(hwnd, names, **kwargs):
        regions.append(kwargs.get("region"))
        return {"score": 0.96, "cx": 700, "cy": 250}, "summer_portal"

    monkeypatch.setattr(portal_module.vision, "wait_for_image_any", fake_wait_any)

    match, name = runner._find_portal_card(1, threading.Event(), ("summer_portal",))
    assert match is not None
    assert regions == [(533, 208, 343, 88)], "found on the first pass, no widening"
    assert not any("outside the searched list area" in line for line in runner.logged)
