"""Portal mode: inventory entry, and the 3-card pick after a won run.

Portal is the one mode whose navigation is reached from the INVENTORY rather
than Play or the lobby Event button, and the only one with a hard real-time
deadline in it -- the game takes the 3 portal cards away again ~15s after a
win. Both are covered here the way tests/test_event_acts.py covers the Event
Acts: by monkeypatching the vision/window layer and asserting on the ORDER of
image clicks and on where the card click actually lands.
"""
import re
import threading
from pathlib import Path

import main
import core.runner as runner_module
import core.runner_portal as portal_module
from core.runner import MacroRunner
from core import runner_constants as rc

APP_JS = Path(__file__).resolve().parent.parent / "ui" / "app.js"


def _runner(**overrides):
    """A MacroRunner with just the collaborators the portal paths touch."""
    runner = object.__new__(MacroRunner)
    runner.logs = []
    runner._log = runner.logs.append
    runner._set_status = lambda **kwargs: None
    runner._checkpoint = lambda stop_event: False
    runner._ensure_lobby = lambda hwnd, stop_event: True
    runner._spam_back_until_gone = lambda hwnd, stop_event: None
    runner._coords = {}
    for key, value in overrides.items():
        setattr(runner, key, value)
    return runner


# ---------------------------------------------------------------- constants

def test_portal_images_and_order_stay_in_sync():
    """_reach_portal_activated looks a portal up in PORTAL_IMAGES; the Task
    Builder offers PORTAL_ORDER. A portal in one but not the other is either
    an offered choice with no card to click or a card nobody can pick -- same
    guard the Event Acts and Tournament types have."""
    assert set(rc.PORTAL_IMAGES) == set(rc.PORTAL_ORDER)


def test_every_portal_has_at_least_one_candidate_crop():
    for name, images in rc.PORTAL_IMAGES.items():
        candidates = (images,) if isinstance(images, str) else images
        assert candidates, f"{name} has no reference crop names"
        assert all(isinstance(n, str) and n for n in candidates), f"{name} has a bad crop name"


def test_task_builder_portals_match_the_runner_constants():
    """TASK_DATA.portal.maps in ui/app.js is what writes a task's `map`, and
    the runner looks that exact string up in PORTAL_IMAGES to know which card
    to click -- so a portal offered in the UI but missing from the constants
    would fail navigation at run time."""
    src = APP_JS.read_text(encoding="utf-8")
    block = re.search(r"\n  portal:\s*\{.*?maps:\s*\[(.*?)\]", src, re.S)
    assert block, "couldn't find TASK_DATA.portal.maps in ui/app.js"
    ui_portals = [a or b for a, b in re.findall(r"'([^']+)'|\"([^\"]+)\"", block.group(1))]
    assert ui_portals == rc.PORTAL_ORDER


def test_portal_card_coordinates_exist_on_both_sides_and_default_to_auto():
    """DEFAULT_COORDS (what the runner reads) and MACRO_COORD_DEFAULTS (what
    Settings serves and resets to) are hand-mirrored -- a key in one but not
    the other is either invisible in the UI or dropped on reset."""
    keys = [f"portal_card_{i}_{axis}" for i in (1, 2, 3) for axis in ("x", "y")]
    for key in keys:
        assert key in rc.DEFAULT_COORDS, f"{key} missing from DEFAULT_COORDS"
        assert key in main.MACRO_COORD_DEFAULTS, f"{key} missing from MACRO_COORD_DEFAULTS"
        # Auto, not a guessed pixel: the pick has one 15s window and no retry.
        assert rc.DEFAULT_COORDS[key] is None
        assert main.MACRO_COORD_DEFAULTS[key] is None


def test_portal_card_coordinates_can_be_cleared_back_to_auto(monkeypatch):
    state = {}
    monkeypatch.setattr(main.cfg, "load", lambda: dict(state))

    def update(patch):
        state.update(patch)
        return dict(state)

    monkeypatch.setattr(main.cfg, "update", update)
    api = object.__new__(main.Api)

    api.set_macro_coords({"portal_card_2_x": 576, "portal_card_2_y": 400})
    assert api.get_macro_coords()["portal_card_2_x"] == 576
    assert api.clear_macro_coord("portal_card_2")["ok"] is True
    coords = api.get_macro_coords()
    assert coords["portal_card_2_x"] is None
    assert coords["portal_card_2_y"] is None


# --------------------------------------------------------------- navigation

def test_reach_portal_activated_clicks_inventory_tab_portal_then_activate(monkeypatch):
    events = []
    runner = _runner()
    runner._click_found_image = lambda hwnd, name, timeout, stop_event: (
        events.append(name) or {"score": 0.99})
    monkeypatch.setattr(portal_module.time, "sleep", lambda seconds: None)

    assert runner._reach_portal_activated(
        hwnd=123, stop_event=threading.Event(), portal="Summer Portal") is True
    assert events == ["nav_inventory", "portal_tab", "portal_summer", "portal_activate"]


def test_reach_portal_activated_backs_out_when_a_step_is_missing(monkeypatch):
    clicked = []
    backs = []
    runner = _runner(_spam_back_until_gone=lambda hwnd, stop_event: backs.append(hwnd))
    runner._click_found_image = lambda hwnd, name, timeout, stop_event: (
        clicked.append(name) or ({"score": 0.99} if name == "nav_inventory" else None))
    monkeypatch.setattr(portal_module.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(portal_module.vision, "find_image", lambda hwnd, name: None)

    assert runner._reach_portal_activated(
        hwnd=456, stop_event=threading.Event(), portal="Summer Portal") is False
    assert clicked == ["nav_inventory", "portal_tab"]
    assert backs == [456]


def test_reach_portal_activated_closes_the_inventory_before_backing_out(monkeypatch):
    """The inventory is a modal with its own close glyph, not one of the
    nested screens nav_back walks out of -- leaving it open would put the
    next attempt's lobby check behind a panel that hides Play."""
    clicks = []
    runner = _runner(_mouse=type("Mouse", (), {"click": lambda self, x, y: None})())
    runner._click_found_image = lambda hwnd, name, timeout, stop_event: None
    monkeypatch.setattr(portal_module.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(portal_module.vision, "find_image",
                        lambda hwnd, name: {"score": 0.97} if name == "nav_closeui" else None)
    monkeypatch.setattr(portal_module.vision, "click_match",
                        lambda mouse, hwnd, match, **kwargs: clicks.append(match))

    assert runner._reach_portal_activated(
        hwnd=789, stop_event=threading.Event(), portal="Summer Portal") is False
    assert clicks == [{"score": 0.97}]


def test_reach_portal_activated_rejects_an_unknown_portal():
    runner = _runner()
    runner._click_found_image = lambda *args, **kwargs: _should_never_run()
    assert runner._reach_portal_activated(
        hwnd=1, stop_event=threading.Event(), portal="Winter Portal") is False
    assert any("Winter Portal" in line for line in runner.logs)


def _should_never_run(*args, **kwargs):  # pragma: no cover -- only runs if a guard breaks
    raise AssertionError("this path should never have been taken")


# ----------------------------------------------------------- the card pick
#
# The offer opens as the run ENDS -- before the Victory screen, not after it --
# so it is watched for from inside the match poll loop. These cover the pick
# itself; the test right at the bottom covers it actually being reached from
# that loop, which is the part that a "look after the result" implementation
# gets silently wrong.

def test_portal_cards_are_not_looked_for_without_the_readiness_crop(monkeypatch):
    """No portal_card_ready image means there's no way to tell the choice
    window apart from any other screen. Checked before any capture happens:
    this runs on every poll of every portal match."""
    runner = _runner()
    captured = []
    monkeypatch.setattr(portal_module.vision, "template_variant_paths", lambda name: [])
    monkeypatch.setattr(portal_module.vision, "find_image",
                        lambda *args, **kwargs: captured.append(args) or None)

    assert runner._portal_cards_available(123) is False
    assert captured == []


def test_portal_cards_available_searches_only_the_configured_region(monkeypatch):
    """The readiness crop is often a portal NAME, and the same name can show
    up in the HUD or on another card -- the region is what makes a match mean
    "the cards are up" rather than "that word is on screen somewhere"."""
    runner = _runner()
    runner._coords = {
        "portal_card_region_x": 200, "portal_card_region_y": 300,
        "portal_card_region_w": 750, "portal_card_region_h": 260,
    }
    seen = {}
    monkeypatch.setattr(portal_module.vision, "template_variant_paths", lambda name: ["x.png"])
    monkeypatch.setattr(portal_module.vision, "find_image",
                        lambda hwnd, name, region=None: seen.update(region=region) or {"score": 0.95})

    assert runner._portal_cards_available(123) is True
    assert seen["region"] == (200, 300, 750, 260)


def test_portal_card_region_needs_all_four_values(monkeypatch):
    """A half-filled box is treated as unset (whole screen) rather than
    guessed at -- a zero-width region would match nothing, silently."""
    runner = _runner()
    assert runner._portal_card_region() is None
    runner._coords = {"portal_card_region_x": 200, "portal_card_region_y": 300,
                      "portal_card_region_w": 750, "portal_card_region_h": None}
    assert runner._portal_card_region() is None
    runner._coords["portal_card_region_h"] = 0
    assert runner._portal_card_region() is None
    runner._coords["portal_card_region_h"] = 260
    assert runner._portal_card_region() == (200, 300, 750, 260)


def test_pick_portal_card_clicks_the_configured_point_and_confirms_it_closed(monkeypatch):
    clicks = []
    runner = _runner(_mouse=type("Mouse", (), {"click": lambda self, x, y: clicks.append((x, y))})())
    runner._coords = {"portal_card_2_x": 576, "portal_card_2_y": 400}
    gone = []
    runner._wait_for_image_gone = lambda hwnd, names, timeout, stop_event=None: (
        gone.append(names) or True)
    monkeypatch.setattr(portal_module.time, "sleep", lambda seconds: None)
    # Clicks are placed in SCREEN space: the window's top-left plus the
    # reference-space point, same as every other fixed click site.
    monkeypatch.setattr(portal_module.wm, "get_window_rect_screen", lambda hwnd: (30, 70, 0, 0))
    monkeypatch.setattr(portal_module.wm, "activate_window", lambda hwnd: True)

    assert runner._pick_portal_card(123, threading.Event(), choice="2") is True
    assert clicks == [(30 + 576, 70 + 400)]
    assert gone == [(rc.PORTAL_CARD_READY_IMAGE,)]


def test_pick_portal_card_fails_when_the_window_stays_open(monkeypatch):
    """A swallowed click looks exactly like a successful one until the offer
    times out on its own and the run continues into a portal it never chose --
    so the pick is confirmed, and a still-open window is a failure."""
    runner = _runner(_mouse=type("Mouse", (), {"click": lambda self, x, y: None})())
    runner._coords = {"portal_card_1_x": 320, "portal_card_1_y": 400}
    runner._wait_for_image_gone = lambda hwnd, names, timeout, stop_event=None: False
    monkeypatch.setattr(portal_module.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(portal_module.wm, "get_window_rect_screen", lambda hwnd: (0, 0, 0, 0))
    monkeypatch.setattr(portal_module.wm, "activate_window", lambda hwnd: True)

    assert runner._pick_portal_card(123, threading.Event()) is False


def test_pick_portal_card_fails_loudly_when_no_click_point_can_be_found(monkeypatch):
    """Cards on screen but nowhere to click is worth stopping on: clicking a
    guessed spot inside a 15s window with no second try is worse than saying
    which setting is missing."""
    runner = _runner(_mouse=type("Mouse", (), {"click": lambda self, x, y: None})())
    monkeypatch.setattr(portal_module.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(portal_module.vision, "find_image_all",
                        lambda hwnd, name, region=None: [])

    assert runner._pick_portal_card(123, threading.Event()) is False
    assert any("Macro Coordinates" in line for line in runner.logs)


def test_portal_card_point_prefers_the_saved_override():
    runner = _runner()
    runner._coords = {"portal_card_3_x": 832, "portal_card_3_y": 400}
    assert runner._portal_card_point(123, 3) == (832, 400)


def test_portal_card_point_falls_back_to_the_card_frames_left_to_right(monkeypatch):
    """With a portal_card_slot crop that matches all 3 frames, no coordinates
    need setting at all -- but find_image_all returns matches best-score
    first, so they have to be ordered by position before card 1 means the
    leftmost one."""
    runner = _runner()
    matches = [
        {"cx": 832, "cy": 402, "score": 0.99},
        {"cx": 320, "cy": 400, "score": 0.94},
        {"cx": 576, "cy": 401, "score": 0.97},
    ]
    monkeypatch.setattr(
        portal_module.vision, "find_image_all",
        lambda hwnd, name, region=None: matches if name == rc.PORTAL_CARD_SLOT_IMAGE else [])

    assert runner._portal_card_point(123, 1) == (320, 400)
    assert runner._portal_card_point(123, 2) == (576, 401)
    assert runner._portal_card_point(123, 3) == (832, 402)


def test_portal_card_point_ignores_a_readiness_crop_that_only_matches_once(monkeypatch):
    """A portal_card_ready cropped from a heading (not a card frame) matches
    once, and its centre is nowhere near any card -- deriving card 1 from it
    would click the heading. Better to have no point at all and say so."""
    runner = _runner()
    monkeypatch.setattr(
        portal_module.vision, "find_image_all",
        lambda hwnd, name, region=None: ([] if name == rc.PORTAL_CARD_SLOT_IMAGE
                                         else [{"cx": 576, "cy": 200, "score": 0.99}]))

    assert runner._portal_card_point(123, 1) is None


# ------------------------------------------- reached from the match loop

def _match_loop_runner(cards_on_poll):
    """A runner wired up for _wait_for_match_result with everything the poll
    loop touches stubbed out, so only the portal branch is under test."""
    runner = object.__new__(MacroRunner)
    runner.logs = []
    runner.picks = []
    runner.polls = [0]
    runner._log = runner.logs.append
    runner._set_status = lambda **kwargs: None
    runner._checkpoint = lambda stop_event: False
    runner._tick_loop_phases = lambda *args, **kwargs: None
    runner._dismiss_afk_chamber = lambda hwnd, clicked_at: clicked_at
    runner._battle_leave_requested = False
    runner._portal_card_attempted = False
    runner._portal_cards_available = lambda hwnd: runner.polls[0] == cards_on_poll
    runner._pick_portal_card = lambda hwnd, stop_event, choice=None: (
        runner.picks.append((runner.polls[0], choice)) or True)
    return runner


def _match_loop_vision(runner, victory_on_poll):
    """vision.find_image for the poll loop: nothing matches except Victory,
    and only from `victory_on_poll` on. Counts polls off the victory check,
    which every poll reaches."""
    def find_image(hwnd, name, *args, **kwargs):
        if name != "victory":
            return None
        runner.polls[0] += 1
        return {"score": 0.99} if runner.polls[0] >= victory_on_poll else None
    return find_image


def test_the_card_offer_is_taken_before_victory_is_ever_reported(monkeypatch):
    """The regression this guards: the cards open BEFORE the Victory screen
    and close themselves ~15s later, so a pick that waits for the result
    never sees them at all. Cards on poll 1, Victory only on poll 2."""
    runner = _match_loop_runner(cards_on_poll=0)
    monkeypatch.setattr(runner_module.vision, "find_image", _match_loop_vision(runner, 2))
    monkeypatch.setattr(runner_module.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(runner_module, "MATCH_RESULT_POLL_INTERVAL", 0)

    result = runner._wait_for_match_result(
        123, threading.Event(), mode="portal",
        task={"mode": "portal", "portal_card": "2"})

    assert result == "win"
    assert runner.picks == [(0, "2")], "the card should be taken on the poll it appears"
    assert runner._portal_card_attempted is True


def test_the_card_offer_is_only_attempted_once_per_match(monkeypatch):
    """The flag is set before the pick, not after it, so a failed pick (no
    click point, a swallowed click) is reported once instead of on every
    remaining poll of the match."""
    runner = _match_loop_runner(cards_on_poll=0)
    runner._portal_cards_available = lambda hwnd: True  # still up on every poll
    runner._pick_portal_card = lambda hwnd, stop_event, choice=None: (
        runner.picks.append(runner.polls[0]) or False)
    monkeypatch.setattr(runner_module.vision, "find_image", _match_loop_vision(runner, 4))
    monkeypatch.setattr(runner_module.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(runner_module, "MATCH_RESULT_POLL_INTERVAL", 0)

    assert runner._wait_for_match_result(
        123, threading.Event(), mode="portal", task={"mode": "portal"}) == "win"
    assert runner.picks == [0]


def test_other_modes_never_look_for_portal_cards(monkeypatch):
    runner = _match_loop_runner(cards_on_poll=0)
    runner._portal_cards_available = _should_never_run
    monkeypatch.setattr(runner_module.vision, "find_image", _match_loop_vision(runner, 1))
    monkeypatch.setattr(runner_module.time, "sleep", lambda seconds: None)

    assert runner._wait_for_match_result(
        123, threading.Event(), mode="story", task={"mode": "story"}) == "win"
    assert runner.picks == []
