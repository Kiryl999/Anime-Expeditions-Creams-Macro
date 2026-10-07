"""Taking the middle portal from the post-round offer -- and what follows it.

A won portal round ends on three new portals, offered for ~20s, and the game
picks one at random when the timer runs out. So the offer is caught from
inside the match poll loop. Deliberately the same shape as Expedition's
"select upgrade card" handling (runner._dismiss_reward_card_if_found): one
image that is only up during the choice, then a middle-of-screen click, which
is the middle card.

Since the game's October 2026 update nothing else follows the offer: no
Victory screen, no Select Portal. The taken portal's round comes up by
itself, waiting on Start Game -- so taking the offer IS the win, and that
round is the next repeat.
"""
import threading
from unittest.mock import MagicMock

import pytest

import core.runner as runner_module
import core.runner_portals as portals_module
from core.runner import MacroRunner
from core.runner_constants import (DEFAULT_COORDS, PORTAL_NEXT_ROUND_TIMEOUT,
                                   PORTAL_OFFER_IMAGE)


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

def test_the_portals_mode_watches_for_the_offer():
    """The Portals mode runs portals, so it gets offered new ones."""
    assert MacroRunner._wants_portal_offer_watch({"mode": "portals", "map": "summer"})


@pytest.mark.parametrize("task", [
    {"mode": "event", "stage": "infinite"},
    {"mode": "event", "stage": "portal"},     # retired; moved to Portals on load
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


# ---------------------------------------------------------------------------
# The offer ends the round
# ---------------------------------------------------------------------------

_SEEN = {"score": 0.95, "cx": 576, "cy": 200}


def _macro_runner():
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    runner.logged = []
    runner._log = lambda message: runner.logged.append(message)
    runner._set_status = lambda **_k: None
    return runner


def test_taking_the_offer_is_the_win(monkeypatch):
    """Nothing after the offer is ever read as Victory -- without this the
    round would be polled for one until the 30-minute match timeout. Victory
    is "on screen" too here, so a loop that still went looking for it would
    return without taking the portal and fail the click assertion."""
    runner = _macro_runner()
    runner._checkpoint = lambda _stop: False
    runner._tick_loop_phases = lambda *_a, **_k: None
    monkeypatch.setattr(runner_module.time, "sleep", lambda _s: None)
    monkeypatch.setattr(runner_module.vision, "find_image",
                        lambda hwnd, name, **k: _SEEN if name in (PORTAL_OFFER_IMAGE, "victory") else None)
    monkeypatch.setattr(runner_module.wm, "activate_window", lambda hwnd: True)
    monkeypatch.setattr(runner_module.wm, "get_window_rect_screen", lambda hwnd: (0, 0, 1152, 756))

    result = runner._wait_for_match_result(1, threading.Event(), task={"mode": "portals", "map": "summer"})

    assert result == "win"
    runner._mouse.shuffle_click.assert_called_once_with(
        DEFAULT_COORDS["screen_middle_x"], DEFAULT_COORDS["screen_middle_y"])


# ---------------------------------------------------------------------------
# A won portal round has no result screen
# ---------------------------------------------------------------------------

class _NowThread:
    """threading.Thread that runs its target on start(), so the background
    reporting can be looked at right after the call."""

    def __init__(self, target, args=(), daemon=None):
        self._target, self._args = target, args

    def start(self):
        self._target(*self._args)


def _result_runner(monkeypatch):
    runner = _macro_runner()
    runner.reported = []
    runner.carried_on = []
    runner._finish_match_result_background = lambda *args: runner.reported.append(args)
    runner._carry_on_after_portal_win = (
        lambda hwnd, stop, keep_playing: runner.carried_on.append(keep_playing) or True)
    runner._capture_result_screenshot = MagicMock(side_effect=AssertionError("no result screen to capture"))
    runner._click_and_verify_gone = MagicMock(side_effect=AssertionError("no result screen to click"))
    runner._dismiss_reward_card_if_found = MagicMock(side_effect=AssertionError("no result screen"))
    monkeypatch.setattr(runner_module.threading, "Thread", _NowThread)
    monkeypatch.setattr(runner_module.time, "sleep",
                        MagicMock(side_effect=AssertionError("nothing to wait for")))
    return runner


_WEBHOOK = {"enabled": True, "url": "https://example.invalid/hook"}


def test_a_won_portal_round_is_reported_without_a_result_screen(monkeypatch):
    runner = _result_runner(monkeypatch)
    task = {"mode": "portals", "map": "summer"}

    assert runner._handle_match_result(1, threading.Event(), task, "win", "3m 2s", _WEBHOOK, repeat=True) is True

    assert runner.reported == [("win", "summer", "3m 2s", task, _WEBHOOK, None)]
    assert runner.carried_on == [True], "the next round is played, not left"


@pytest.mark.parametrize("repeat, play_mode, keep_playing", [
    (True, "solo", True),
    (False, "solo", False),          # last repeat, or the lobby is wanted between repeats
    (True, "matchmaking", False),    # matchmaking never repeats in place
])
def test_the_next_round_is_played_only_when_the_task_repeats_in_place(monkeypatch, repeat, play_mode,
                                                                       keep_playing):
    runner = _result_runner(monkeypatch)
    task = {"mode": "portals", "map": "summer", "play_mode": play_mode}

    runner._handle_match_result(1, threading.Event(), task, "win", "3m", None, repeat=repeat)

    assert runner.carried_on == [keep_playing]


def test_a_lost_portal_round_still_goes_through_its_result_screen(monkeypatch):
    runner = _result_runner(monkeypatch)
    monkeypatch.setattr(runner_module.time, "sleep", lambda _s: None)
    runner._dismiss_reward_card_if_found = lambda hwnd: False
    clicked = []
    runner._click_and_verify_gone = lambda hwnd, stop, name, timeout, **k: clicked.append(name) or True
    runner._wait_for_image_gone = lambda *a, **k: True
    monkeypatch.setattr(runner_module.wm, "get_window_rect_screen", lambda hwnd: (0, 0, 1152, 756))

    runner._handle_match_result(1, threading.Event(), {"mode": "portals"}, "loss", "1m", None, repeat=True)

    assert runner.carried_on == []
    assert clicked == ["repeat_stage"]


# ---------------------------------------------------------------------------
# Waiting for the round the taken portal starts
# ---------------------------------------------------------------------------

class _Clock:
    def __init__(self):
        self.now = 1000.0

    def time(self):
        return self.now


def _round_runner(monkeypatch, start_game_after=None, offer_polls=0):
    """start_game_after: from which poll on Start Game shows (None: never).
    offer_polls: for how many polls the offer is still up."""
    runner = _macro_runner()
    clock = _Clock()
    runner.polls = 0
    runner.offers_taken = 0
    runner.screenshots = []
    monkeypatch.setattr(portals_module.time, "time", clock.time)

    def sleep(seconds, _stop=None):
        clock.now += seconds
        runner.polls += 1

    def start_game(hwnd, *_a, **_k):
        if start_game_after is not None and runner.polls >= start_game_after:
            return "nav_start_game", _SEEN
        return None, None

    def offer(hwnd):
        if runner.polls <= offer_polls:
            runner.offers_taken += 1
            return True
        return False

    runner._interruptible_sleep = sleep
    runner._find_start_game_button = start_game
    runner._take_portal_offer_if_found = offer
    runner._save_debug_screenshot_unconditional = lambda hwnd, name: runner.screenshots.append(name)
    return runner


def test_the_next_round_is_there_once_its_start_game_shows(monkeypatch):
    runner = _round_runner(monkeypatch, start_game_after=3)

    assert runner._wait_for_next_portal_round(1, threading.Event()) is True
    assert runner.polls == 3


def test_an_offer_still_up_gets_the_middle_portal_again(monkeypatch):
    """A click the game never got would leave the pick to the timer, which
    takes one at random."""
    runner = _round_runner(monkeypatch, start_game_after=4, offer_polls=2)

    assert runner._wait_for_next_portal_round(1, threading.Event()) is True
    assert runner.offers_taken == 2


def test_a_round_that_never_comes_gives_up_with_a_screenshot(monkeypatch):
    runner = _round_runner(monkeypatch, start_game_after=None)

    assert runner._wait_for_next_portal_round(1, threading.Event()) is False
    assert runner.screenshots == ["portal_next_round_timeout"]
    assert runner.polls * runner_module.PORTAL_NEXT_ROUND_POLL_INTERVAL >= PORTAL_NEXT_ROUND_TIMEOUT


def test_a_stop_ends_the_wait(monkeypatch):
    runner = _round_runner(monkeypatch, start_game_after=None)
    stop = threading.Event()
    stop.set()

    assert runner._wait_for_next_portal_round(1, stop) is False
    assert runner.screenshots == []


def test_with_repeats_left_the_next_round_is_simply_played():
    runner = _macro_runner()
    runner._wait_for_next_portal_round = lambda hwnd, stop: True
    runner._leave_match_to_lobby = MagicMock(side_effect=AssertionError("must not leave"))

    assert runner._carry_on_after_portal_win(1, threading.Event(), keep_playing=True) is True


def test_when_the_task_is_done_the_next_round_is_left_for_the_lobby():
    """There is no result screen with Leave Stage anymore -- the round the
    offer started is left with the in-match To Lobby instead."""
    runner = _macro_runner()
    order = []
    runner._wait_for_next_portal_round = lambda hwnd, stop: order.append("wait") or True
    runner._leave_match_to_lobby = lambda hwnd, stop, reason: order.append("leave") or True

    assert runner._carry_on_after_portal_win(1, threading.Event(), keep_playing=False) is True
    assert order == ["wait", "leave"]


def test_no_next_round_is_a_failure_whatever_was_wanted():
    runner = _macro_runner()
    runner._wait_for_next_portal_round = lambda hwnd, stop: False
    runner._leave_match_to_lobby = MagicMock(side_effect=AssertionError("nothing to leave"))

    assert runner._carry_on_after_portal_win(1, threading.Event(), keep_playing=True) is False
    assert runner._carry_on_after_portal_win(1, threading.Event(), keep_playing=False) is False
