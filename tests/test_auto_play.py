"""The game's Auto Play, switched on and kept on by the macro.

The button TOGGLES, so everything here is about clicking it only when it is
really off, and never twice for one switch: over Remote Desktop a second click
landed while the label was still catching up with the first and switched Auto
Play straight back off. And it has to be quick -- Start Game waits on it.
"""
import inspect
import threading
from pathlib import Path
from unittest.mock import MagicMock

import cv2
import pytest

from core import runner_auto_play
from core import templates
from core import vision
from core.runner import MacroRunner
from core.runner_constants import (
    AUTO_PLAY_FIND_TIMEOUT, AUTO_PLAY_OFF_IMAGE, AUTO_PLAY_ON_IMAGE, AUTO_PLAY_START_CLICKS,
    AUTO_PLAY_VERIFY_SETTLE, AUTO_PLAY_WATCH_INTERVAL, AUTO_PLAY_WATCH_MAX_CLICKS,
)

ROOT = Path(__file__).resolve().parent.parent
BUTTON = {"score": 1.0, "cx": 1094, "cy": 469, "x": 1051, "y": 456, "w": 87, "h": 26}


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def _runner(monkeypatch, screen, enabled=True):
    """A runner whose Auto Play button reads screen(clicks so far, looks since
    the last click) -- "on", "off" or None. Clicks, log lines, screenshots and
    webhooks are recorded; every wait only moves a fake clock."""
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    clock = _Clock()
    runner.clock = clock
    runner.clicks = []
    runner.logged = []
    runner.screenshots = []
    runner.webhooks = []
    looks = {"since_click": 0}
    monkeypatch.setattr(runner_auto_play.time, "time", clock.time)
    monkeypatch.setattr(runner_auto_play.time, "sleep", clock.sleep)

    def click_match(_mouse, _hwnd, match, **_kwargs):
        runner.clicks.append((match["cx"], match["cy"]))
        looks["since_click"] = 0

    def read(_hwnd):
        looks["since_click"] += 1
        state = screen(len(runner.clicks), looks["since_click"])
        return (state, dict(BUTTON)) if state else (None, None)

    monkeypatch.setattr(runner_auto_play.vision, "click_match", click_match)
    runner._read_auto_play = read
    runner._auto_play_enabled = lambda _task: enabled
    runner._interruptible_sleep = lambda seconds, _stop: clock.sleep(seconds)
    runner._log = runner.logged.append
    runner._set_status = lambda **_kwargs: None
    runner._save_debug_screenshot_unconditional = lambda _hwnd, name: runner.screenshots.append(name)
    runner._send_event_webhook = lambda _webhook, _task, title, *_args: runner.webhooks.append(title)
    return runner


def _before_start(runner, stop=None):
    return runner._auto_play_before_start(123, stop or threading.Event(), {"macro": "auto_playing"}, {})


# ---------------------------------------------------------------------------
# Before Start Game
# ---------------------------------------------------------------------------

def test_already_on_starts_right_away(monkeypatch):
    """A portal's next round keeps Auto Play on -- one look, no click."""
    runner = _runner(monkeypatch, lambda _clicked, _look: "on")

    assert _before_start(runner) is True
    assert runner.clicks == []
    assert runner.clock.now == 1000.0, "no waiting when it is already on"


def test_off_is_clicked_once_and_the_round_starts_as_soon_as_it_reads_on(monkeypatch):
    runner = _runner(monkeypatch, lambda clicked, _look: "on" if clicked else "off")

    assert _before_start(runner) is True
    assert runner.clicks == [(BUTTON["cx"], BUTTON["cy"])]
    assert runner.clock.now - 1000.0 <= 1.0, "switching it on must not hold the round up"


def test_a_label_that_lags_behind_the_click_is_not_clicked_again(monkeypatch):
    """The live report: still "Auto Play" for a moment after a click that
    took. A second click then switches it straight back off."""
    runner = _runner(monkeypatch, lambda clicked, look: "on" if clicked and look > 6 else "off")

    assert _before_start(runner) is True
    assert len(runner.clicks) == 1


def test_a_click_that_did_not_take_is_clicked_again(monkeypatch):
    runner = _runner(monkeypatch, lambda clicked, _look: "on" if clicked >= 2 else "off")

    assert _before_start(runner) is True
    assert len(runner.clicks) == 2
    assert runner.screenshots == [] and runner.webhooks == []


def test_never_on_starts_the_round_anyway_with_a_warning(monkeypatch):
    """A Start Game that hangs on Auto Play would cost more than one round
    without it."""
    runner = _runner(monkeypatch, lambda _clicked, _look: "off")

    assert _before_start(runner) is True
    assert len(runner.clicks) == AUTO_PLAY_START_CLICKS
    assert runner.screenshots == ["auto_play_not_on"]
    assert runner.webhooks == ["Auto Play Not On"]
    assert "starting the round anyway" in runner.logged[-1]


def test_a_button_that_never_shows_is_not_clicked_blind(monkeypatch):
    runner = _runner(monkeypatch, lambda _clicked, _look: None)

    assert _before_start(runner) is True
    assert runner.clicks == []
    assert runner.webhooks == ["Auto Play Not On"]
    assert runner.clock.now - 1000.0 <= AUTO_PLAY_FIND_TIMEOUT + 0.5


def test_off_for_a_single_look_is_not_clicked(monkeypatch):
    """Something may have just switched it on -- the label gets a moment."""
    runner = _runner(monkeypatch, lambda _clicked, look: "off" if look == 1 else "on")

    assert _before_start(runner) is True
    assert runner.clicks == []


def test_missing_crops_start_the_round_without_checking(monkeypatch):
    runner = _runner(monkeypatch, lambda _clicked, _look: "off")

    def missing(_hwnd):
        raise vision.TemplateNotFound("no auto_play_on crop.")

    runner._read_auto_play = missing

    assert _before_start(runner) is True
    assert runner.clicks == []
    assert any("auto_play_on" in line for line in runner.logged)


def test_switched_off_the_button_is_not_even_looked_at(monkeypatch):
    runner = _runner(monkeypatch, lambda _clicked, _look: "off", enabled=False)
    runner._read_auto_play = lambda _hwnd: pytest.fail("looked at Auto Play with the switch off")

    assert _before_start(runner) is True


def test_a_stop_ends_it(monkeypatch):
    stop = threading.Event()
    runner = _runner(monkeypatch, lambda _clicked, _look: stop.set() or "off")

    assert _before_start(runner, stop) is False
    assert runner.clicks == []


def test_start_game_waits_for_it():
    source = inspect.getsource(MacroRunner._press_start_game)
    assert source.index("_auto_play_before_start") < source.index("_find_start_game_button(")


# ---------------------------------------------------------------------------
# During the round
# ---------------------------------------------------------------------------

def _watch(monkeypatch, screen):
    runner = _runner(monkeypatch, screen)
    runner._reset_auto_play_watch()
    return runner


def _poll(runner, seconds=1.0):
    """One match poll tick, then the poll interval."""
    clicked = runner._tick_auto_play(123)
    runner.clock.now += seconds
    return clicked


def test_the_watch_waits_an_interval_after_the_start(monkeypatch):
    """Start Game was only pressed once Auto Play read on."""
    runner = _watch(monkeypatch, lambda _clicked, _look: pytest.fail("looked too early"))

    assert _poll(runner) is False


def test_on_is_left_alone(monkeypatch):
    runner = _watch(monkeypatch, lambda _clicked, _look: "on")
    runner.clock.now += AUTO_PLAY_WATCH_INTERVAL

    for _ in range(30):
        _poll(runner)

    assert runner.clicks == []


def test_off_goes_back_on_after_two_polls(monkeypatch):
    runner = _watch(monkeypatch, lambda clicked, _look: "on" if clicked else "off")
    runner.clock.now += AUTO_PLAY_WATCH_INTERVAL

    assert _poll(runner) is False, "one look is not enough to click a toggle"
    assert _poll(runner) is True
    assert len(runner.clicks) == 1


def test_after_a_click_the_label_gets_time_to_change(monkeypatch):
    runner = _watch(monkeypatch, lambda _clicked, _look: "off")
    runner.clock.now += AUTO_PLAY_WATCH_INTERVAL
    _poll(runner, 0.0)
    _poll(runner, 0.0)
    assert len(runner.clicks) == 1

    while runner.clock.now < runner._auto_play_watch["next_look"]:
        _poll(runner, 0.5)
    assert len(runner.clicks) == 1, "clicked again before the label could change"
    assert runner.clock.now >= 1000.0 + AUTO_PLAY_WATCH_INTERVAL + AUTO_PLAY_VERIFY_SETTLE


def test_clicks_that_never_take_stop_for_the_match(monkeypatch):
    runner = _watch(monkeypatch, lambda _clicked, _look: "off")
    runner.clock.now += AUTO_PLAY_WATCH_INTERVAL

    for _ in range(60):
        _poll(runner)

    assert len(runner.clicks) == AUTO_PLAY_WATCH_MAX_CLICKS
    assert runner._auto_play_watch["paused"] is True

    runner._reset_auto_play_watch()
    assert runner._auto_play_watch["paused"] is False, "the next match watches again"


def test_back_on_resets_the_click_count(monkeypatch):
    runner = _watch(monkeypatch, lambda clicked, look: "on" if clicked and look <= 1 else "off")
    runner.clock.now += AUTO_PLAY_WATCH_INTERVAL

    for _ in range(80):
        _poll(runner)

    assert len(runner.clicks) > AUTO_PLAY_WATCH_MAX_CLICKS, "each time it came back on, it may go off again"
    assert any("back on" in line for line in runner.logged)


def test_missing_crops_stop_the_watch_once(monkeypatch):
    runner = _watch(monkeypatch, lambda _clicked, _look: "off")

    def missing(_hwnd):
        raise vision.TemplateNotFound("no auto_play_off crop.")

    runner._read_auto_play = missing
    runner.clock.now += AUTO_PLAY_WATCH_INTERVAL

    for _ in range(10):
        _poll(runner)

    assert runner.clicks == []
    assert len(runner.logged) == 1


def test_the_watch_runs_only_on_a_tick_nothing_else_clicked():
    source = inspect.getsource(MacroRunner._wait_for_match_result)
    guard = source.index("if watch_auto_play and not clicked_something and not block_acted:")
    assert guard < source.index("_tick_auto_play(hwnd)") < source.index("_tick_fishing(hwnd, fishing_point")


def test_every_match_gets_a_fresh_watch():
    assert "_reset_auto_play_watch()" in inspect.getsource(MacroRunner._begin_battle)


# ---------------------------------------------------------------------------
# The switch and the crops
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("blocks, expected", [
    ({"auto_play": True}, True),
    ({"auto_play": False}, False),
    ({}, False),                       # saved before the switch existed
    ({"auto_play": "true"}, False),    # only a real true switches it on
    ([], False),                       # oldest template format
])
def test_the_switch_is_read_from_the_macro(monkeypatch, blocks, expected):
    monkeypatch.setattr(templates, "load_template", lambda _name: {"blocks": blocks})
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())

    assert runner._auto_play_enabled({"macro": "auto_playing"}) is expected
    assert runner._auto_play_enabled({}) is False


def test_the_macro_manager_saves_and_loads_the_switch():
    app_js = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
    assert "auto_play: creationAutoPlay" in app_js
    assert "creationAutoPlay = payload.auto_play === true;" in app_js
    assert "renderCameraSetupRow() + renderAutoPlayRow()" in app_js


@pytest.mark.parametrize("name", [AUTO_PLAY_ON_IMAGE, AUTO_PLAY_OFF_IMAGE])
def test_both_crops_ship(name):
    assert (ROOT / "Assets" / "ui" / name / f"{name}.png").is_file()


def _east_town_gray():
    """A real frame with the button OFF ("Auto Play") before Start Game."""
    return cv2.cvtColor(cv2.imread(str(ROOT / "Assets" / "map" / "Story" / "East Town.png")),
                        cv2.COLOR_BGR2GRAY)


def _read_frame(monkeypatch, frame):
    monkeypatch.setattr(vision, "_name_thresholds", {})
    monkeypatch.setattr(vision, "capture_game_gray", lambda _hwnd, region=None: frame)
    return MacroRunner(MagicMock(), MagicMock(), MagicMock())._read_auto_play(123)


def test_the_shipped_crops_read_off_as_off(monkeypatch):
    state, match = _read_frame(monkeypatch, _east_town_gray())

    assert state == "off"
    assert 1022 <= match["cx"] <= 1144 and 450 <= match["cy"] <= 480, "on the button"


def test_the_shipped_crops_read_on_as_on(monkeypatch):
    """"Auto Play" sits inside "Auto Playing", so the off crop scores high on
    the on button too -- the better score has to win."""
    frame = _east_town_gray()
    on_crop = cv2.cvtColor(cv2.imread(str(ROOT / "Assets" / "ui" / AUTO_PLAY_ON_IMAGE
                                          / f"{AUTO_PLAY_ON_IMAGE}.png")), cv2.COLOR_BGR2GRAY)
    h, w = on_crop.shape
    frame[451:451 + h, 1051:1051 + w] = on_crop

    state, _match = _read_frame(monkeypatch, frame)

    assert state == "on"


def test_no_button_reads_as_unknown(monkeypatch):
    frame = _east_town_gray()
    frame[430:500, 1000:1152] = 0

    assert _read_frame(monkeypatch, frame) == (None, None)
