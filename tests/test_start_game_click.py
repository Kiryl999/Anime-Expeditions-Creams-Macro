import threading
from unittest.mock import MagicMock

from core import runner as runner_module
from core.runner import MacroRunner
from core.runner_constants import START_GAME_CLICK_RETRY_ATTEMPTS


class _Clock:
    def __init__(self):
        self.now = 0.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def _button(cx=576, cy=220):
    return {"score": 1.0, "cx": cx, "cy": cy, "x": cx - 60, "y": cy - 10, "w": 120, "h": 20}


def _start_game_runner(monkeypatch, screen, clicks):
    """A runner whose Start Game is whatever screen(clicks so far, looks
    since the last click) returns -- a match, or None when it isn't on
    screen. Every click is recorded with its position, and every wait only
    moves a fake clock."""
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    clock = _Clock()
    looks = {"since_click": 0}
    monkeypatch.setattr(runner_module.time, "time", clock.time)
    monkeypatch.setattr(runner_module.time, "sleep", clock.sleep)
    monkeypatch.setattr(runner_module.wm, "activate_window", lambda _hwnd: True)

    def click_match(_mouse, _hwnd, match, **_kwargs):
        clicks.append((match["cx"], match["cy"]))
        looks["since_click"] = 0

    monkeypatch.setattr(runner_module.vision, "click_match", click_match)
    runner._interruptible_sleep = lambda seconds, _stop: clock.sleep(seconds)
    runner._wait_out_start_game_warning = lambda *_args: None
    runner._debug_save = lambda *_args: None
    runner._save_debug_screenshot_unconditional = lambda *_args: None
    runner._send_event_webhook = lambda *_args, **_kwargs: None

    def find_start_game_button(_hwnd, _stop=None, _timeout=0):
        looks["since_click"] += 1
        match = screen(len(clicks), looks["since_click"])
        return ("nav_start_game", match) if match else (None, None)

    runner._find_start_game_button = find_start_game_button
    return runner


def _press(runner):
    return runner._press_start_game(123, threading.Event(), {"map": "Summer Portal"}, {})


def test_a_start_game_that_lingers_after_a_click_that_took_is_not_clicked_again(monkeypatch):
    """Over Remote Desktop the button was still on screen a second after the
    click. The re-click landed on the HUD where it had been -- the portal
    round's Auto Play -- and switched it straight back off."""
    clicks = []
    # On screen for four more looks (~1.2s) after the click, then gone.
    runner = _start_game_runner(
        monkeypatch, lambda clicked, look: _button() if not clicked or look <= 4 else None, clicks)

    assert _press(runner) is True
    assert clicks == [(576, 220)]


def test_a_start_game_click_that_did_not_register_is_clicked_again(monkeypatch):
    clicks = []
    # Holds its spot through the whole watch; the second click takes.
    runner = _start_game_runner(monkeypatch, lambda clicked, _look: _button() if clicked < 2 else None, clicks)

    assert _press(runner) is True
    assert clicks == [(576, 220), (576, 220)]


def test_start_game_is_clicked_where_it_is_now(monkeypatch):
    clicks = []

    def screen(clicked, look):
        if clicked:
            return None
        return _button() if look == 1 else _button(cy=240)

    runner = _start_game_runner(monkeypatch, screen, clicks)

    _press(runner)

    assert clicks == [(576, 240)]


def test_a_start_game_gone_before_the_click_is_not_clicked(monkeypatch):
    """Clicking its old spot would hit whatever the HUD has there."""
    clicks = []
    runner = _start_game_runner(monkeypatch, lambda _clicked, look: _button() if look == 1 else None, clicks)

    assert _press(runner) is True
    assert clicks == []


def test_a_start_game_still_moving_when_the_watch_ends_is_not_clicked_again(monkeypatch):
    """Sliding away, not waiting for a click."""
    clicks = []
    runner = _start_game_runner(
        monkeypatch, lambda clicked, look: _button(cx=576 + (20 * look if clicked else 0)), clicks)

    assert _press(runner) is True
    assert clicks == [(576, 220)]


def test_one_dropped_look_does_not_count_as_gone(monkeypatch):
    clicks = []

    def screen(clicked, look):
        if clicked >= 2 or (clicked and look == 2):
            return None
        return _button()

    runner = _start_game_runner(monkeypatch, screen, clicks)

    _press(runner)

    assert len(clicks) == 2


def test_a_stuck_start_game_gets_its_last_click_and_a_warning(monkeypatch):
    clicks = []
    runner = _start_game_runner(monkeypatch, lambda _clicked, _look: _button(), clicks)
    stuck = []
    runner._save_debug_screenshot_unconditional = lambda _hwnd, name: stuck.append(name)

    assert _press(runner) is True
    assert len(clicks) == START_GAME_CLICK_RETRY_ATTEMPTS
    assert stuck == ["start_game_click_stuck"]
