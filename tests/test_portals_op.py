"""PortalsOp: the mode-agnostic portal lead-in (lobby -> Inventory -> Portals
tab -> search -> tier -> activate), driven by the PORTAL_SEARCHES regions."""

import threading

import core.runner as runner_module
import core.runner_portals as portal_module
from core.runner import MacroRunner
from core.runner_constants import DEFAULT_COORDS


def _runner():
    runner = object.__new__(MacroRunner)
    runner.clicked = []
    runner.backs = []
    runner.typed = []
    runner.logged = []
    runner._ensure_lobby = lambda hwnd, stop: True
    runner._checkpoint = lambda stop: False
    runner._set_status = lambda **kw: None
    runner._log = lambda message: runner.logged.append(message)
    runner._spam_back_until_gone = lambda hwnd, stop: runner.backs.append(hwnd)
    runner._click_ref = lambda hwnd, x, y, **k: runner.clicked.append(("ref", x, y))
    # A real MacroRunner always has this; the fixture skips __init__.
    runner._coords = dict(DEFAULT_COORDS)
    runner._interruptible_sleep = lambda *a, **k: None
    runner._mouse = type("Mouse", (), {})()
    runner._click_found_image = (
        lambda hwnd, name, timeout, stop, **k: runner.clicked.append(("image", name)) or (
            {"score": 0.99} if name != "missing" else None))
    kb = type("Kb", (), {})()
    kb.combo = lambda *a, **k: runner.clicked.append(("combo", a))
    kb.tap = lambda vk, **k: runner.clicked.append(("tap", vk))
    kb.type_text = lambda text, **k: runner.typed.append(text)
    runner._keyboard = kb
    return runner


def test_run_portal_selection_from_inventory_lead_in(monkeypatch):
    runner = _runner()
    picked = []
    runner._select_portal_on_picker = lambda hwnd, stop, query: picked.append(query) or True
    monkeypatch.setattr(portal_module.time, "sleep", lambda s: None)
    assert runner._run_portal_selection_from_inventory(1, threading.Event()) is True
    images = [call[1] for call in runner.clicked if call[0] == "image"]
    assert images == ["nav_inv", "normal_portals_nav"]
    assert picked == ["summer"]


def test_run_portal_selection_from_inventory_backs_out_when_inventory_missing(monkeypatch):
    runner = _runner()
    runner._click_found_image = (
        lambda hwnd, name, timeout, stop, **k: runner.clicked.append(("image", name)) or (
            None if name == "nav_inv" else {"score": 0.99}))
    monkeypatch.setattr(portal_module.time, "sleep", lambda s: None)
    assert runner._run_portal_selection_from_inventory(1, threading.Event()) is False
    assert runner.backs == [1]


def test_select_portal_on_picker_searches_and_activates(monkeypatch):
    runner = _runner()
    monkeypatch.setattr(portal_module.vision, "wait_for_image_any",
                        lambda *a, **k: ({"score": 0.97, "cx": 500, "cy": 250}, "summer_portal"))
    clicked = []
    monkeypatch.setattr(portal_module.vision, "click_match", lambda mouse, hwnd, match: clicked.append(match["cx"]))
    assert runner._select_portal_on_picker(1, threading.Event(), "summer") is True
    assert not any(c[0] == "combo" for c in runner.clicked)  # never Ctrl -- moves the Roblox camera
    assert runner.typed == ["summer"]
    assert clicked == [500]                                   # the found portal card
    assert ("image", "portal_activate") in runner.clicked     # confirm


def test_select_portal_on_picker_looks_for_crops_named_after_the_query(monkeypatch):
    """The Portal Name is not just what gets typed -- it names the card crop to
    look for, so running a non-Summer portal is just adding a crop under that
    name. summer_portal stays last as the shipped fallback."""
    runner = _runner()
    searched = []

    def fake_wait_any(hwnd, names, **kwargs):
        searched.extend(names)
        return {"score": 0.97, "cx": 12, "cy": 34}, names[-1]

    monkeypatch.setattr(portal_module.vision, "wait_for_image_any", fake_wait_any)
    monkeypatch.setattr(portal_module.vision, "click_match", lambda *a, **k: None)
    assert runner._select_portal_on_picker(1, threading.Event(), "Winter Rift") is True
    assert searched == ["winter_rift_portal", "winter_rift", "summer_portal"]
    assert runner.typed == ["Winter Rift"]


def test_select_portal_on_picker_backs_out_when_card_missing(monkeypatch):
    """Not in the list region AND not anywhere on screen -- only then give up."""
    runner = _runner()
    looks = []

    def fake_wait_any(hwnd, names, **kwargs):
        looks.append(kwargs.get("region"))
        return None, None

    monkeypatch.setattr(portal_module.vision, "wait_for_image_any", fake_wait_any)
    assert runner._select_portal_on_picker(1, threading.Event(), "summer") is False
    assert runner.backs == [1]
    assert len(looks) == 2 and looks[0] is not None and looks[1] is None,         "region first, then the whole window"


def test_a_card_outside_the_list_region_is_still_found(monkeypatch):
    """The live failure: a picker sitting ~189px right of the shipped layout
    put every card past PORTAL_SEARCHES["portals"], so the region search found
    nothing while the card was plainly on screen. The region is a hint now."""
    runner = _runner()

    def fake_wait_any(hwnd, names, **kwargs):
        if kwargs.get("region") is not None:
            return None, None                      # not where the box expects
        return {"score": 0.96, "cx": 800, "cy": 250}, "summer_portal"

    monkeypatch.setattr(portal_module.vision, "wait_for_image_any", fake_wait_any)
    clicked = []
    monkeypatch.setattr(portal_module.vision, "click_match",
                        lambda mouse, hwnd, match: clicked.append(match["cx"]))

    assert runner._select_portal_on_picker(1, threading.Event(), "summer") is True
    assert clicked == [800]
    assert any("outside the searched list area" in line for line in runner.logged)


def test_select_portal_on_picker_backs_out_when_no_crop_exists_at_all(monkeypatch):
    """The search only raises when NOT ONE candidate has a crop on disk --
    that is a missing-asset problem, not a stop, so it logs and backs out."""
    runner = _runner()

    def raise_missing(*a, **k):
        raise portal_module.vision.TemplateNotFound("no such template")

    monkeypatch.setattr(portal_module.vision, "wait_for_image_any", raise_missing)
    assert runner._select_portal_on_picker(1, threading.Event(), "summer") is False
    assert runner.backs == [1]


def test_run_portal_selection_from_inventory_forwards_custom_query(monkeypatch):
    runner = _runner()
    picked = []
    runner._select_portal_on_picker = lambda hwnd, stop, query: picked.append(query) or True
    monkeypatch.setattr(portal_module.time, "sleep", lambda s: None)
    assert runner._run_portal_selection_from_inventory(1, threading.Event(), query="sakura") is True
    assert picked == ["sakura"]


def test_select_portal_post_victory_uses_the_query(monkeypatch):
    runner = _runner()
    picked = []
    runner._select_portal_on_picker = lambda hwnd, stop, query: picked.append(query) or True
    monkeypatch.setattr(portal_module.time, "sleep", lambda s: None)
    assert runner._select_portal_post_victory(1, threading.Event(), "sakura") is True
    # Clicked the Victory screen's Select Portal, then the agnostic picker
    # with the task's query.
    assert ("image", "select_new_portal") in runner.clicked
    assert picked == ["sakura"]
