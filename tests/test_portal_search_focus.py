"""Aiming and clearing the portal picker's search box.

Two live failures drove this. The box is aimed at the shipped `portal_search`
crop -- the 47x10px placeholder word "Search..." at the LEFT end of the bar --
and `_click_found_image` clicks a match's centre, so on a layout where the bar
sits differently the click lands outside the field ("clicks too far left").
The macro then typed into nothing. Worse, the clearing step was Ctrl+A, and a
Ctrl that misses the field reaches Roblox, where it toggles the camera and
leaves the rest of the run fighting the view.

And clearing is skipped when the box is known to be empty: the game only
draws that placeholder in an empty box, and 33 keys plus a Macro Speed pause
on every pick were spent on a box that usually opens empty.
"""
import threading

import core.runner_portals as portal_module
from core import keys
from core.runner import MacroRunner
from core.runner_constants import (DEFAULT_COORDS, PORTAL_SEARCH_CLEAR_KEYS,
                                   PORTAL_SEARCH_PLACEHOLDER_BAND)

SAVED_POINT = {"portal_search_x": 470, "portal_search_y": 181}


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
    # By default a saved point finds no "Search..." placeholder, so the box
    # may hold text and gets cleared.
    runner._portal_search_is_empty = lambda hwnd, point: False
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
    for coords in (None, SAVED_POINT):
        runner = _runner(coords)

        runner._focus_portal_search(1, threading.Event())

        assert not any(e[0] == "combo" for e in runner.events)
        assert keys.VK_CONTROL not in [e[1] for e in runner.events if e[0] == "tap"]


def test_the_field_is_cleared_from_the_end_of_the_text():
    """END first: a click can land mid-text, and backspace deletes to the LEFT
    of the cursor -- from the end it takes everything. It used to be HOME,
    which parks the cursor where backspace deletes nothing at all."""
    runner = _runner(SAVED_POINT)

    runner._focus_portal_search(1, threading.Event())

    taps = [e[1] for e in runner.events if e[0] == "tap"]
    assert taps[0] == keys.VK_END
    assert keys.VK_HOME not in taps
    assert taps.count(keys.VK_BACK) == PORTAL_SEARCH_CLEAR_KEYS


def test_clearing_pays_the_macro_speed_pause_once_not_per_key(monkeypatch):
    """Each paced tap waits out the Macro Speed delay. Paced, the 33 clearing
    keys waited it 33 times -- about 20s of a search box that looked stuck at
    600ms, reported live on a Remote Desktop setup. The keys go out unpaced,
    with one pause after them, the way type_text handles its characters."""
    runner = _runner(SAVED_POINT)
    paced, pauses = [], []
    runner._keyboard.tap = lambda vk, **k: paced.append(k.get("pace", True))
    monkeypatch.setattr(portal_module.pacing, "action_pause", lambda: pauses.append(1))

    assert runner._focus_portal_search(1, threading.Event()) is True
    assert len(paced) == PORTAL_SEARCH_CLEAR_KEYS + 1
    assert not any(paced), "a clearing key was sent paced"
    assert pauses == [1]


# ---------------------------------------------------------------------------
# Not clearing a box that is already empty
# ---------------------------------------------------------------------------

def test_a_box_found_by_its_placeholder_is_not_cleared(monkeypatch):
    """The shipped crop IS the "Search..." placeholder, which the game only
    draws in an empty box -- finding it already proves there is nothing to
    clear. No keys, no Macro Speed pause."""
    runner = _runner()
    pauses = []
    monkeypatch.setattr(portal_module.pacing, "action_pause", lambda: pauses.append(1))

    assert runner._focus_portal_search(1, threading.Event()) is True
    assert ("image", "portal_search") in runner.events
    assert not any(e[0] == "tap" for e in runner.events)
    assert pauses == []


def test_a_saved_point_with_the_placeholder_showing_is_not_cleared(monkeypatch):
    """Same for a saved point: the placeholder is checked BEFORE the click,
    while nothing has touched the box yet."""
    runner = _runner(SAVED_POINT)
    order = []
    runner._portal_search_is_empty = lambda hwnd, point: order.append(("look", point)) or True
    runner._click_ref = lambda hwnd, x, y, **k: order.append(("click", (x, y)))
    pauses = []
    monkeypatch.setattr(portal_module.pacing, "action_pause", lambda: pauses.append(1))

    assert runner._focus_portal_search(1, threading.Event()) is True
    assert order == [("look", (470, 181)), ("click", (470, 181))]
    assert not any(e[0] == "tap" for e in runner.events)
    assert pauses == []


def test_the_placeholder_is_looked_for_around_a_saved_point(monkeypatch):
    """A saved point usually means the built-in search region does not fit
    this layout, so the look goes around the point -- mostly to its left,
    where the placeholder starts the bar."""
    runner = _runner(SAVED_POINT)
    del runner._portal_search_is_empty     # the real one
    regions = []
    monkeypatch.setattr(portal_module.vision, "find_image",
                        lambda hwnd, name, region=None, **k: regions.append((name, region)) or {"score": 0.95})

    assert runner._portal_search_is_empty(1, (470, 181)) is True
    left, right, half = PORTAL_SEARCH_PLACEHOLDER_BAND
    assert regions == [("portal_search", (470 - left, 181 - half, left + right, 2 * half))]


def test_the_placeholder_band_stays_inside_the_window(monkeypatch):
    runner = _runner(SAVED_POINT)
    del runner._portal_search_is_empty
    regions = []
    monkeypatch.setattr(portal_module.vision, "find_image",
                        lambda hwnd, name, region=None, **k: regions.append(region))

    assert runner._portal_search_is_empty(1, (20, 5)) is False
    x, y, w, h = regions[0]
    assert (x, y) == (0, 0)
    assert w > 0 and h > 0


def test_no_placeholder_crop_means_clearing_as_before(monkeypatch):
    runner = _runner(SAVED_POINT)
    del runner._portal_search_is_empty

    def raise_missing(*a, **k):
        raise portal_module.vision.TemplateNotFound("no such template")

    monkeypatch.setattr(portal_module.vision, "find_image", raise_missing)
    assert runner._portal_search_is_empty(1, (470, 181)) is False


def test_a_missing_search_box_fails_loudly_and_says_what_to_do():
    runner = _runner()
    runner._click_found_image = lambda *a, **k: None

    assert runner._focus_portal_search(1, threading.Event()) is False
    assert any("Macro Coordinates" in line for line in runner.logged)
    # Nothing typed into a field that was never focused.
    assert not any(e[0] in ("tap", "type", "combo") for e in runner.events)


def test_the_picker_goes_through_it(monkeypatch):
    """The picker's own search must use this, not a Ctrl+A of its own -- a
    second copy of the search is how this drifted apart in the first place
    (the retired Event > Portal kind had one)."""
    import inspect

    source = inspect.getsource(portal_module.PortalsOp._select_portal_on_picker)
    assert "_focus_portal_search" in source
    assert "VK_CONTROL" not in source


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
        return {"score": 0.96, "cx": 700, "cy": 250}, "portal_card"

    monkeypatch.setattr(portal_module.vision, "wait_for_image_any", fake_wait_any)

    match, name = runner._find_portal_card(1, threading.Event(), ("portal_card",))
    assert match is not None
    assert regions == [(533, 208, 343, 88)], "found on the first pass, no widening"
    assert not any("outside the searched list area" in line for line in runner.logged)
