"""Taking the middle portal from the post-round offer.

A won portal round offers three new portals for ~20s and picks one at random
when the timer runs out. The offer opens BEFORE the Victory screen, so it has
to be caught from inside the match poll loop -- looking after the result finds
nothing left to choose.

Deliberately the same shape as Expedition's "select upgrade card" handling
(runner._dismiss_reward_card_if_found): one image that is only up during the
choice, then a middle-of-screen click, which is the middle card.
"""
import threading

import pytest

import core.runner as runner_module
from core.runner import MacroRunner
from core.runner_constants import DEFAULT_COORDS, PORTAL_OFFER_IMAGE


def _runner(monkeypatch, frames):
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
    return runner


# ---------------------------------------------------------------------------
# Which tasks watch for it
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("task", [
    {"mode": "portals", "map": "summer"},
    {"mode": "event", "stage": "portal"},
])
def test_both_portal_lead_ins_watch_for_the_offer(task):
    """The Inventory Portals mode and the Summer event's Portal kind both run
    portals, so both get offered new ones."""
    assert MacroRunner._wants_portal_offer_watch(task)


@pytest.mark.parametrize("task", [
    {"mode": "event", "stage": "infinite"},   # the event's OTHER kind
    {"mode": "story", "stage": "3"},
    {"mode": "raid", "map": "Snowy Castle", "stage": "3"},
    {"mode": "expedition"},
    {},
])
def test_nothing_else_pays_for_the_search(task):
    assert not MacroRunner._wants_portal_offer_watch(task)


# ---------------------------------------------------------------------------
# Taking it
# ---------------------------------------------------------------------------

def test_no_offer_means_no_click(monkeypatch):
    runner = _runner(monkeypatch, [None])

    assert runner._take_portal_offer_if_found(1) is False
    assert runner.events == []


def test_the_middle_of_the_screen_is_clicked(monkeypatch):
    """The middle of the screen IS the middle card -- the same trick
    Expedition uses to take an upgrade card."""
    runner = _runner(monkeypatch, [{"score": 0.95, "cx": 576, "cy": 200}])

    assert runner._take_portal_offer_if_found(1) is True
    points = [(e[1], e[2]) for e in runner.events if e[0] == "shuffle"]
    assert points == [(DEFAULT_COORDS["screen_middle_x"], DEFAULT_COORDS["screen_middle_y"])]
    # NOT the matched image's own centre -- that is the heading, not a card.
    assert (576, 200) not in points


def test_focus_is_taken_before_the_click(monkeypatch):
    """Same lesson as the close panel: a click the game never receives looks
    exactly like a click that did nothing."""
    runner = _runner(monkeypatch, [{"score": 0.95, "cx": 576, "cy": 200}])

    runner._take_portal_offer_if_found(1)

    assert runner.events[0][0] == "focus"


def test_a_missing_crop_is_not_an_error(monkeypatch):
    """No crop ships for this. A missing one has to leave the run alone --
    the offer simply times out and picks at random, as it did before."""
    def raise_missing(*a, **k):
        raise runner_module.vision.TemplateNotFound("no such template")

    runner = _runner(monkeypatch, [])
    monkeypatch.setattr(runner_module.vision, "find_image", raise_missing)

    assert runner._take_portal_offer_if_found(1) is False
    assert runner.events == []


def test_the_offer_image_has_a_folder_to_put_a_crop_in():
    from pathlib import Path

    folder = Path(__file__).resolve().parent.parent / "Assets" / "ui" / PORTAL_OFFER_IMAGE
    assert folder.is_dir(), f"{PORTAL_OFFER_IMAGE} needs a folder for its crop"
