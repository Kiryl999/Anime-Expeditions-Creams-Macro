"""PortalsOp: the mode-agnostic portal lead-in (lobby -> Inventory -> Portals
tab -> search -> tier -> activate), driven by the PORTAL_SEARCHES regions."""

import threading

import pytest

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
    runner._save_debug_screenshot_unconditional = lambda hwnd, name: None
    runner._mouse = type("Mouse", (), {})()
    runner._click_found_image = (
        lambda hwnd, name, timeout, stop, **k: runner.clicked.append(("image", name)) or (
            {"score": 0.99} if name != "missing" else None))
    # portal_activate is the one confirm here that goes through the verified
    # click instead (a dropped click there is invisible downstream) -- it
    # records the same way so the ordering assertions still read the same.
    runner._click_and_verify_gone = (
        lambda hwnd, stop, name, timeout, **k: runner.clicked.append(("image", name)) or name != "missing")
    kb = type("Kb", (), {})()
    kb.combo = lambda *a, **k: runner.clicked.append(("combo", a))
    kb.tap = lambda vk, **k: runner.clicked.append(("tap", vk))
    kb.type_text = lambda text, **k: runner.typed.append(text)
    runner._keyboard = kb
    # No portal NAME on screen unless a test says so -- "summer" ships a name
    # crop, and without this every summer test would screenshot the desktop.
    runner._find_portal_name = lambda hwnd, stop, name_image, timeout: None
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
                        lambda *a, **k: ({"score": 0.97, "cx": 500, "cy": 250}, "portal_card"))
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
    name. portal_card stays last as the generic card every portal falls back to."""
    runner = _runner()
    searched = []

    def fake_wait_any(hwnd, names, **kwargs):
        searched.extend(names)
        return {"score": 0.97, "cx": 12, "cy": 34}, names[-1]

    monkeypatch.setattr(portal_module.vision, "wait_for_image_any", fake_wait_any)
    monkeypatch.setattr(portal_module.vision, "click_match", lambda *a, **k: None)
    assert runner._select_portal_on_picker(1, threading.Event(), "Winter Rift") is True
    assert searched == ["winter_rift_portal", "winter_rift", "portal_card"]
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
        return {"score": 0.96, "cx": 800, "cy": 250}, "portal_card"

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


# ---------------------------------------------------------------------------
# A generic card never skips the search
# ---------------------------------------------------------------------------

def test_a_card_already_on_screen_does_not_skip_the_search(monkeypatch):
    """The portals look alike in the picker -- only the name on the card
    differs -- so a portal card that is already listed may be ANY portal.
    Skipping the search for it clicked whichever one sat at the front and
    never typed the name at all. No generic card is looked for until the
    name has been typed -- not even when a name crop exists, if the name
    itself is not on screen."""
    runner = _runner()
    typed_at_each_look = []

    def fake_wait_any(hwnd, names, **kwargs):
        typed_at_each_look.append(list(runner.typed))
        return {"score": 0.98, "cx": 290, "cy": 255}, "portal_card"

    monkeypatch.setattr(portal_module.vision, "wait_for_image_any", fake_wait_any)
    monkeypatch.setattr(portal_module.vision, "find_image_any",
                        lambda *a, **k: pytest.fail("looked for a card before searching"))
    monkeypatch.setattr(portal_module.vision, "click_match", lambda *a, **k: None)

    assert runner._select_portal_on_picker(1, threading.Event(), "summer") is True
    assert runner.typed == ["summer"]
    assert typed_at_each_look and all(t == ["summer"] for t in typed_at_each_look)


# ---------------------------------------------------------------------------
# The name shortcut: a crop of the name on the card
# ---------------------------------------------------------------------------

def _name_crops(monkeypatch, *names):
    """Pretend exactly these name-crop folders exist on disk."""
    real = portal_module.vision.template_variant_paths
    monkeypatch.setattr(
        portal_module.vision, "template_variant_paths",
        lambda name, *a, **k: [f"{name}.png"] if name in names else (
            [] if name.startswith("portal_name_") else real(name, *a, **k)))


@pytest.mark.parametrize("query, folder", [
    ("summer", "portal_name_summer"),
    ("Summer Portal", "portal_name_summer"),       # same portal, same crop
    ("Winter Rift", "portal_name_winter_rift"),
    ("teleportal", "portal_name_teleportal"),     # only a whole trailing word goes
    ("portal", None),                             # nothing left to name it by
    ("  ", None),
])
def test_the_name_crop_folder_follows_the_portal_name(query, folder):
    assert portal_module._portal_name_image(query) == folder


def test_a_listed_portal_is_clicked_by_its_name_without_searching(monkeypatch):
    """The point of the shortcut: the search box, the typing and the wait
    for the filter are the slow part of every pick, and a portal whose NAME
    is already on the list needs none of them."""
    runner = _runner()
    _name_crops(monkeypatch, "portal_name_summer")
    looked = []
    runner._find_portal_name = (
        lambda hwnd, stop, name_image, timeout: looked.append((name_image, timeout))
        or {"score": 0.98, "cx": 400, "cy": 255})
    monkeypatch.setattr(portal_module.vision, "wait_for_image_any",
                        lambda *a, **k: pytest.fail("fell back to the generic card search"))
    clicked = []
    monkeypatch.setattr(portal_module.vision, "click_match",
                        lambda mouse, hwnd, match: clicked.append((match["cx"], match["cy"])))

    assert runner._select_portal_on_picker(1, threading.Event(), "summer") is True
    assert looked == [("portal_name_summer", portal_module.PORTAL_NAME_PEEK_TIMEOUT)]
    assert runner.typed == []
    assert ("image", "portal_search") not in runner.clicked
    assert not any(c[0] == "tap" for c in runner.clicked)
    assert clicked == [(400, 255)]
    assert ("image", "portal_activate") in runner.clicked
    assert any("without searching" in line for line in runner.logged)


def test_an_unlisted_name_is_searched_and_then_taken_by_its_name(monkeypatch):
    """Not listed yet: search as always. Once typed, the name is taken the
    moment the filtered card shows -- it cannot be a different portal -- so
    there is no fixed wait for the filter first, and the generic crops are
    never needed."""
    runner = _runner()
    _name_crops(monkeypatch, "portal_name_summer")
    looks = []

    def fake_find_name(hwnd, stop, name_image, timeout):
        looks.append((list(runner.typed), timeout))
        return {"score": 0.97, "cx": 420, "cy": 250} if runner.typed else None

    runner._find_portal_name = fake_find_name
    slept = []
    runner._interruptible_sleep = lambda seconds, *a, **k: slept.append(seconds)
    monkeypatch.setattr(portal_module.vision, "wait_for_image_any",
                        lambda *a, **k: pytest.fail("fell back to the generic card search"))
    clicked = []
    monkeypatch.setattr(portal_module.vision, "click_match",
                        lambda mouse, hwnd, match: clicked.append(match["cx"]))

    assert runner._select_portal_on_picker(1, threading.Event(), "summer") is True
    assert looks == [([], portal_module.PORTAL_NAME_PEEK_TIMEOUT),
                     (["summer"], portal_module.SETTLE_DELAY)]
    assert clicked == [420]
    # The only settle left is the one after the card click.
    assert slept == [portal_module.SETTLE_DELAY]


def test_a_name_crop_that_does_not_match_still_ends_in_the_generic_search(monkeypatch):
    """A crop cut on another setup may never match. The pick must not get
    worse for it: after the search the generic crops still find the card,
    and the log says the name crop missed so it can be redone."""
    runner = _runner()
    _name_crops(monkeypatch, "portal_name_summer")
    monkeypatch.setattr(portal_module.vision, "wait_for_image_any",
                        lambda *a, **k: ({"score": 0.96, "cx": 500, "cy": 250}, "portal_card"))
    clicked = []
    monkeypatch.setattr(portal_module.vision, "click_match",
                        lambda mouse, hwnd, match: clicked.append(match["cx"]))

    assert runner._select_portal_on_picker(1, threading.Event(), "summer") is True
    assert runner.typed == ["summer"]
    assert clicked == [500]
    assert any('"portal_name_summer" did not match it' in line for line in runner.logged)


def test_without_a_name_crop_nothing_is_looked_for_before_typing(monkeypatch):
    """No crop of the name, no shortcut -- and the search line says how to
    get one, since that is the only place a user learns it exists."""
    runner = _runner()
    _name_crops(monkeypatch)  # none
    runner._find_portal_name = lambda *a, **k: pytest.fail("looked for a name with no crop of it")
    monkeypatch.setattr(portal_module.vision, "wait_for_image_any",
                        lambda *a, **k: ({"score": 0.96, "cx": 500, "cy": 250}, "portal_card"))
    monkeypatch.setattr(portal_module.vision, "click_match", lambda *a, **k: None)

    assert runner._select_portal_on_picker(1, threading.Event(), "infernal") is True
    assert runner.typed == ["infernal"]
    assert any('"portal_name_infernal"' in line and "Image Manager" in line
               for line in runner.logged)


def test_the_name_is_only_looked_for_inside_the_card_list(monkeypatch):
    """Never widened to the whole window like the generic card search: the
    name is looked for before the list is filtered, and the post-victory
    picker sits over the result screen -- a "Summer Portal" anywhere else
    must not be clicked. The settle re-looks stay in the same box."""
    runner = _runner()
    del runner._find_portal_name          # the real one
    seen = {}

    def fake_wait(hwnd, name, **kwargs):
        seen["wait"] = (name, kwargs.get("region"), kwargs.get("timeout"))
        return {"score": 0.98, "cx": 400, "cy": 280}

    def fake_settle(hwnd, names, stop, first=None, region=None):
        seen["settle"] = (names, region)
        return first

    monkeypatch.setattr(portal_module.vision, "wait_for_image", fake_wait)
    runner._settled_match_any = fake_settle

    match = runner._find_portal_name(1, threading.Event(), "portal_name_summer", 0.8)

    box = runner._portal_list_region()
    assert seen["wait"] == ("portal_name_summer", box, 0.8)
    assert seen["settle"] == (("portal_name_summer",), box)
    # Clicked on the art above the name, not on the text.
    assert (match["cx"], match["cy"]) == (400, 280 - portal_module.PORTAL_NAME_CLICK_RISE)


def test_the_name_click_uses_where_the_card_settled(monkeypatch):
    """A picker still sliding in hands back a stale first spot; the click
    goes where the name held still."""
    runner = _runner()
    del runner._find_portal_name
    monkeypatch.setattr(portal_module.vision, "wait_for_image",
                        lambda *a, **k: {"score": 0.98, "cx": 300, "cy": 280})
    runner._settled_match_any = (
        lambda hwnd, names, stop, first=None, region=None: {"score": 0.98, "cx": 360, "cy": 282})

    match = runner._find_portal_name(1, threading.Event(), "portal_name_summer", 0.8)

    assert (match["cx"], match["cy"]) == (360, 282 - portal_module.PORTAL_NAME_CLICK_RISE)


def test_no_name_on_the_list_or_no_crop_on_disk_is_simply_none(monkeypatch):
    runner = _runner()
    del runner._find_portal_name
    monkeypatch.setattr(portal_module.vision, "wait_for_image", lambda *a, **k: None)
    assert runner._find_portal_name(1, threading.Event(), "portal_name_summer", 0.8) is None

    def raise_missing(*a, **k):
        raise portal_module.vision.TemplateNotFound("no such template")

    monkeypatch.setattr(portal_module.vision, "wait_for_image", raise_missing)
    assert runner._find_portal_name(1, threading.Event(), "portal_name_summer", 0.8) is None
