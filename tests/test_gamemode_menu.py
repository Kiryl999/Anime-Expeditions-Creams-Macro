"""Telling the gamemode menu opened after a Play click.

Its Back button (nav_back) used to be the only sign. Seen live over Remote
Desktop: the menu was visibly open, nav_back did not match -- a fresh crop
did not help -- and the run took it for a Play click that never registered.
The re-click then found no Play and gave the whole entry up ("nav_play
vanished"), the recovery's Back spam found nothing to click either, and the
lobby check, with Play still hidden behind the menu, rejoined Roblox. The
Regular Challenge then came round again and did the same.

So any Play-menu card counts as the menu too, Play gone after its click
counts as a click that took, and a lobby hidden by the menu says so before
the rejoin.
"""
import threading
from unittest.mock import MagicMock

import core.runner as runner_module
from core.runner import MacroRunner
from core.runner_constants import (CHALLENGE_IMAGE_NAMES, GAMEMODE_CARD_IMAGE_NAMES, GAMEMODE_CARD_REGION,
                                   NAV_PLAY_IMAGE_NAMES, PLAY_CLICK_RETRY_ATTEMPTS, RAID_IMAGE_NAMES,
                                   STORY_IMAGE_NAMES)

_CARD = {"score": 0.93, "cx": 700, "cy": 300, "x": 650, "y": 280, "w": 100, "h": 40}
_BACK = {"score": 0.95, "cx": 80, "cy": 700, "x": 40, "y": 685, "w": 80, "h": 30}
_PLAY = {"score": 0.92, "cx": 100, "cy": 400, "x": 60, "y": 385, "w": 80, "h": 30}


def _runner():
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    runner.logged = []
    runner.screenshots = []
    runner._log = lambda message, *_a, **_k: runner.logged.append(message)
    runner._set_status = lambda **_k: None
    runner._save_debug_screenshot_unconditional = (
        lambda hwnd, name: runner.screenshots.append(name) or f"debug/{name}.png")
    return runner


def test_every_play_menu_card_counts_as_the_menu():
    for names in (STORY_IMAGE_NAMES, RAID_IMAGE_NAMES, CHALLENGE_IMAGE_NAMES):
        assert set(names) <= set(GAMEMODE_CARD_IMAGE_NAMES)


# ---------------------------------------------------------------------------
# Waiting for the menu
# ---------------------------------------------------------------------------

def test_a_menu_card_shows_the_menu_open_when_nav_back_does_not_match(monkeypatch):
    runner = _runner()
    searched = []

    def find_any(hwnd, names, region=None, **_k):
        searched.append((tuple(names), region))
        return _CARD, "challenge"

    monkeypatch.setattr(runner_module.vision, "find_image", lambda hwnd, name, **k: None)
    monkeypatch.setattr(runner_module.vision, "find_image_any", find_any)

    assert runner._wait_for_gamemode_menu(1, threading.Event(), 10.0) is _CARD
    # Boxed to the cards panel, like the card search itself -- the left
    # viewport has party buttons that must not count.
    assert searched == [(GAMEMODE_CARD_IMAGE_NAMES, GAMEMODE_CARD_REGION)]
    assert any('found the "challenge" card' in line for line in runner.logged)


def test_nav_back_still_counts_on_its_own(monkeypatch):
    runner = _runner()
    monkeypatch.setattr(runner_module.vision, "find_image",
                        lambda hwnd, name, **k: _BACK if name == "nav_back" else None)
    runner._find_gamemode_menu_card = MagicMock(side_effect=AssertionError("nav_back was enough"))

    assert runner._wait_for_gamemode_menu(1, threading.Event(), 10.0) is _BACK


def test_missing_card_crops_leave_the_card_check_quiet(monkeypatch):
    def missing(*_a, **_k):
        raise runner_module.vision.TemplateNotFound("no card crops")

    runner = _runner()
    monkeypatch.setattr(runner_module.vision, "find_image_any", missing)

    assert runner._find_gamemode_menu_card(1) == (None, None)


# ---------------------------------------------------------------------------
# After the Play click
# ---------------------------------------------------------------------------

def _gamemode_runner(monkeypatch, play_visible):
    """A Play click whose menu is never recognized; Play itself is still on
    screen (play_visible) or gone."""
    runner = _runner()
    runner.play_clicks = 0
    runner.cards_searched = []
    runner._wait_for_gamemode_menu = lambda hwnd, stop, timeout: None
    runner._dismiss_lobby_overlay = lambda hwnd: False
    runner._dismiss_party_overlay = lambda hwnd, stop: True
    runner._debug_save = lambda *a, **k: None

    def click_play(hwnd, stop):
        runner.play_clicks += 1
        return True

    def find_card(hwnd, stop, names, label):
        runner.cards_searched.append(label)
        return _CARD, names[0]

    runner._click_play = click_play
    runner._find_gamemode_card = find_card
    runner._click_gamemode_target = lambda hwnd, stop, label, click: True
    monkeypatch.setattr(runner_module.vision, "find_image_any",
                        lambda hwnd, names, **k: (_PLAY, "nav_play") if play_visible and
                        tuple(names) == NAV_PLAY_IMAGE_NAMES else (None, None))
    return runner


def test_play_gone_after_its_click_goes_on_to_the_card(monkeypatch):
    """The case seen live: no re-click into an open menu, no "vanished"."""
    runner = _gamemode_runner(monkeypatch, play_visible=False)

    assert runner._click_gamemode(1, threading.Event(), "challenge") is True
    assert runner.play_clicks == 0, "Play is not clicked again"
    assert runner.cards_searched == ["Challenge"]
    assert runner.screenshots == ["gamemode_menu_no_back"]
    assert any("Play is gone" in line and "nav_back" in line for line in runner.logged)


def test_play_still_there_is_clicked_again(monkeypatch):
    """A click that really did not register still gets its retries."""
    runner = _gamemode_runner(monkeypatch, play_visible=True)

    assert runner._click_gamemode(1, threading.Event(), "challenge") is False
    assert runner.play_clicks == PLAY_CLICK_RETRY_ATTEMPTS - 1
    assert runner.cards_searched == []
    assert runner.screenshots == ["gamemode_menu_timeout"]


# ---------------------------------------------------------------------------
# A lobby hidden by the menu
# ---------------------------------------------------------------------------

def test_a_lobby_hidden_by_the_menu_says_so_before_the_rejoin(monkeypatch):
    runner = _runner()
    rejoins = []
    monkeypatch.setattr(runner_module.vision, "wait_for_image_any", lambda *a, **k: (None, None))
    runner._clear_lobby_blocker = lambda hwnd: False
    runner._find_gamemode_menu_card = lambda hwnd: (_CARD, "challenge")
    runner._attempt_rejoin = lambda hwnd, stop: rejoins.append(hwnd) or True

    assert runner._ensure_lobby(1, threading.Event()) is True
    # Without its Back button the menu has no other way out.
    assert rejoins == [1]
    assert runner.screenshots == ["lobby_hidden_by_gamemode_menu"]
    assert any("Not a disconnect" in line and "nav_back" in line for line in runner.logged)


def test_no_menu_is_still_a_silent_disconnect(monkeypatch):
    runner = _runner()
    rejoins = []
    monkeypatch.setattr(runner_module.vision, "wait_for_image_any", lambda *a, **k: (None, None))
    runner._clear_lobby_blocker = lambda hwnd: False
    runner._find_gamemode_menu_card = lambda hwnd: (None, None)
    runner._attempt_rejoin = lambda hwnd, stop: rejoins.append(hwnd) or True

    runner._ensure_lobby(1, threading.Event())

    assert rejoins == [1]
    assert runner.screenshots == []
    assert any("silent disconnect" in line for line in runner.logged)
