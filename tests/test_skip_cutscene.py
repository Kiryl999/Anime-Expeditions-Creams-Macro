"""A won round with a secret-unit reveal, in Portals and Raid tasks.

Some portal and raid rounds can drop a secret unit once won. Its reveal plays
a cutscene; Skip Cutscene ends it, and all that is left is a lone Game
Results button. That opens the Victory screen. A raid's is handled like any
other; a portal's has Select Portal, which picks the next portal -- or, on
the last repeat, the round is left as from any result screen. Which portals
and raid maps can drop one is not known, so every Portals and Raid task
watches for the button: a look every SKIP_CUTSCENE_LOOK_INTERVAL. It replaced
the "Click anywhere to close" watch Spirit City and Snowy Castle Act 3 had.
"""
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import core.runner as runner_module
from core.runner import MacroRunner
from core.runner_constants import (GAME_RESULTS_GRACE, GAME_RESULTS_IMAGE, MATCH_RESULT_POLL_INTERVAL,
                                   PORTAL_OFFER_IMAGE, SKIP_CUTSCENE_IMAGE, SKIP_CUTSCENE_LOOK_INTERVAL)

_SEEN = {"score": 0.95, "cx": 576, "cy": 600}
_SKIP = {"score": 0.95, "cx": 1060, "cy": 40}
_RESULTS = {"score": 0.95, "cx": 576, "cy": 380}
_VICTORY = {"score": 0.95, "cx": 576, "cy": 150}


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def _macro_runner(monkeypatch):
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    runner.logged = []
    runner.events = []
    runner._log = lambda message: runner.logged.append(message)
    runner._set_status = lambda **_k: None
    runner._debug_save = lambda *a, **k: None
    monkeypatch.setattr(runner_module.wm, "activate_window",
                        lambda hwnd: runner.events.append(("focus",)) or True)
    monkeypatch.setattr(runner_module.wm, "get_window_rect_screen", lambda hwnd: (0, 0, 1152, 756))
    monkeypatch.setattr(runner_module.vision, "click_match",
                        lambda mouse, hwnd, match, **k: runner.events.append(("click", match, k)))
    return runner


# ---------------------------------------------------------------------------
# Which tasks watch for it
# ---------------------------------------------------------------------------

def test_every_portals_task_watches_for_it():
    assert MacroRunner._wants_skip_cutscene_watch({"mode": "portals", "map": "summer"})


@pytest.mark.parametrize("task", [
    {"mode": "raid", "map": "Spirit City", "stage": "3"},
    {"mode": "raid", "map": "Snowy Castle", "stage": "3"},
    {"mode": "raid", "map": "Snowy Castle", "stage": "1"},
    {"mode": "raid", "map": "A Raid Still To Come", "stage": "2"},
])
def test_every_raid_task_watches_for_it_whatever_the_map_or_act(task):
    assert MacroRunner._wants_skip_cutscene_watch(task)


@pytest.mark.parametrize("task", [
    {"mode": "story", "stage": "3"},
    {"mode": "monster_clash", "map": "Monster Clash"},
    {"mode": "boss_rush", "map": "District 7"},
    {},
])
def test_nothing_else_pays_for_the_search(task):
    assert not MacroRunner._wants_skip_cutscene_watch(task)


def test_the_click_anywhere_watch_is_gone():
    """Raid Act 3's "Click anywhere to close" watch is replaced, not kept
    alongside: its click on a cutscene would land somewhere on the round."""
    import inspect

    assert not hasattr(MacroRunner, "_click_close_popup_if_found")
    assert not hasattr(MacroRunner, "_wants_close_popup_watch")
    assert "click_anywhere_to_close" not in inspect.getsource(MacroRunner._wait_for_match_result)


# ---------------------------------------------------------------------------
# Clicking it
# ---------------------------------------------------------------------------

def test_no_button_means_no_click(monkeypatch):
    runner = _macro_runner(monkeypatch)
    monkeypatch.setattr(runner_module.vision, "find_image", lambda hwnd, name, **k: None)

    assert runner._click_skip_cutscene_if_found(1) is False
    assert runner.events == []


def test_the_button_is_clicked_once_with_focus_and_hover_in(monkeypatch):
    runner = _macro_runner(monkeypatch)
    monkeypatch.setattr(runner_module.vision, "find_image",
                        lambda hwnd, name, **k: _SEEN if name == SKIP_CUTSCENE_IMAGE else None)

    assert runner._click_skip_cutscene_if_found(1) is True
    assert runner.events == [("focus",), ("click", _SEEN, {"shuffle": True})]


def test_an_empty_crop_folder_is_quiet(monkeypatch):
    def missing(*_a, **_k):
        raise runner_module.vision.TemplateNotFound("no image yet")

    runner = _macro_runner(monkeypatch)
    monkeypatch.setattr(runner_module.vision, "find_image", missing)

    assert runner._click_skip_cutscene_if_found(1) is False
    assert runner.events == [] and runner.logged == []


def test_the_crop_has_a_folder_to_put_it_in():
    folder = Path(__file__).resolve().parent.parent / "Assets" / "ui" / SKIP_CUTSCENE_IMAGE
    assert folder.is_dir(), f"{SKIP_CUTSCENE_IMAGE} needs a folder for its crop"


# ---------------------------------------------------------------------------
# The round's end
# ---------------------------------------------------------------------------

def _poll_runner(monkeypatch, cutscene_ticks=(), offer_tick=None, victory_tick=None,
                 results_after_skip=False):
    """A portal round, poll tick by poll tick (1-based):

    cutscene_ticks -- the ticks Skip Cutscene is on screen;
    offer_tick     -- from which tick the three-portal offer is up;
    victory_tick   -- from which tick Victory shows on its own;
    results_after_skip -- Game Results shows once the reveal is skipped, and
                      Victory from the tick after it is clicked.
    """
    runner = _macro_runner(monkeypatch)
    runner._checkpoint = lambda _stop: False
    runner._tick_loop_phases = lambda *_a, **_k: None
    clock = _Clock()
    monkeypatch.setattr(runner_module.time, "time", clock.time)
    monkeypatch.setattr(runner_module.time, "sleep", clock.sleep)

    def tick():
        return int((clock.now - 1000.0) // MATCH_RESULT_POLL_INTERVAL) + 1

    def clicked_at(match):
        return [e for e in runner.events if e[0] == "click" and e[1] is match]

    runner.tick = tick
    runner.results_clicked_on = None

    def find(hwnd, name, **_k):
        skipped = bool(clicked_at(_SKIP))
        if name == PORTAL_OFFER_IMAGE:
            return _SEEN if offer_tick is not None and tick() >= offer_tick else None
        if name == SKIP_CUTSCENE_IMAGE:
            return _SKIP if tick() in cutscene_ticks else None
        if name == GAME_RESULTS_IMAGE:
            if results_after_skip and skipped and runner.results_clicked_on is None:
                return _RESULTS
            return None
        if name == "victory":
            if victory_tick is not None and tick() >= victory_tick:
                return _VICTORY
            if runner.results_clicked_on is not None and tick() > runner.results_clicked_on:
                return _VICTORY
        return None

    def click(mouse, hwnd, match, **k):
        runner.events.append(("click", match, k))
        if match is _RESULTS:
            runner.results_clicked_on = tick()

    monkeypatch.setattr(runner_module.vision, "find_image", find)
    monkeypatch.setattr(runner_module.vision, "click_match", click)
    runner.clicks_on = lambda match: len(clicked_at(match))
    return runner


_PORTALS = {"mode": "portals", "map": "summer"}


def test_a_skipped_reveal_opens_the_victory_screen_through_game_results(monkeypatch):
    runner = _poll_runner(monkeypatch, cutscene_ticks={1}, results_after_skip=True)

    result = runner._wait_for_match_result(1, threading.Event(), task=_PORTALS)

    assert result == "win"
    assert runner._portal_victory_screen is True, "the result screen has Select Portal to deal with"
    assert runner.clicks_on(_SKIP) == 1
    assert runner.clicks_on(_RESULTS) == 1
    # Right away -- not after the grace that sits out the offer.
    assert runner.results_clicked_on * MATCH_RESULT_POLL_INTERVAL < GAME_RESULTS_GRACE
    assert any("Skip Cutscene" in line for line in runner.logged)


def test_a_raid_round_goes_from_the_skip_to_its_victory_screen(monkeypatch):
    """Same ending as a portal round's reveal, minus the portal: the Victory
    screen is then a raid's usual one, with Repeat Stage and Leave."""
    runner = _poll_runner(monkeypatch, cutscene_ticks={1}, results_after_skip=True)

    result = runner._wait_for_match_result(
        1, threading.Event(), task={"mode": "raid", "map": "Snowy Castle", "stage": "3"})

    assert result == "win"
    assert runner.clicks_on(_SKIP) == 1
    assert runner.clicks_on(_RESULTS) == 1
    assert runner._portal_victory_screen is False, "no Select Portal on a raid's Victory screen"


def test_an_offer_win_keeps_the_offer_path(monkeypatch):
    runner = _poll_runner(monkeypatch, offer_tick=2)

    assert runner._wait_for_match_result(1, threading.Event(), task=_PORTALS) == "win"
    assert runner._portal_victory_screen is False
    assert runner.clicks_on(_SKIP) == 0 and runner.clicks_on(_RESULTS) == 0


def test_victory_without_a_skip_keeps_the_offer_path(monkeypatch):
    """Only a skipped reveal says the round ended on the Victory screen; any
    other Victory in a portal round goes on as an offer win did."""
    runner = _poll_runner(monkeypatch, victory_tick=2)

    assert runner._wait_for_match_result(1, threading.Event(), task=_PORTALS) == "win"
    assert runner._portal_victory_screen is False


def test_the_watch_looks_only_every_few_seconds(monkeypatch):
    """A reveal still up on every tick is clicked once per look, not once per
    poll -- the watch costs a search only every SKIP_CUTSCENE_LOOK_INTERVAL."""
    ticks = 6
    runner = _poll_runner(monkeypatch, cutscene_ticks=set(range(1, ticks + 1)), offer_tick=ticks + 1)

    runner._wait_for_match_result(1, threading.Event(), task=_PORTALS)

    assert runner.clicks_on(_SKIP) == ticks * MATCH_RESULT_POLL_INTERVAL / SKIP_CUTSCENE_LOOK_INTERVAL


def test_other_modes_never_look_for_it(monkeypatch):
    runner = _poll_runner(monkeypatch, cutscene_ticks={1, 2}, victory_tick=3)

    result = runner._wait_for_match_result(1, threading.Event(), task={"mode": "story", "map": "Leaf Village"})

    assert result == "win"
    assert runner.clicks_on(_SKIP) == 0
    assert runner._portal_victory_screen is False


# ---------------------------------------------------------------------------
# The Victory screen after it
# ---------------------------------------------------------------------------

def _result_runner(monkeypatch, victory_screen, select_ok=True):
    runner = _macro_runner(monkeypatch)
    runner._portal_victory_screen = victory_screen
    runner.selected = []
    runner.clicked = []
    runner.carried_on = []
    runner._select_portal_post_victory = lambda hwnd, stop, query: runner.selected.append(query) or select_ok
    runner._carry_on_after_portal_win = (
        lambda hwnd, stop, keep_playing: runner.carried_on.append(keep_playing) or True)
    runner._click_and_verify_gone = lambda hwnd, stop, name, timeout, **k: runner.clicked.append(name) or True
    runner._click_return_to_lobby_if_found = lambda *_a: True
    runner._dismiss_reward_card_if_found = lambda _hwnd: False
    runner._clear_result_obtainment_modal = lambda *_a: True
    runner._capture_result_screenshot = lambda _hwnd: None
    runner._finish_match_result_background = lambda *_a: None
    monkeypatch.setattr(runner_module.time, "sleep", lambda _s: None)
    return runner


def test_select_portal_picks_the_tasks_portal_with_repeats_left(monkeypatch):
    runner = _result_runner(monkeypatch, victory_screen=True)

    assert runner._handle_match_result(1, threading.Event(), dict(_PORTALS, play_mode="solo"), "win",
                                       "4m", None, repeat=True) is True
    assert runner.selected == ["summer"]
    assert runner.clicked == [], "no Repeat Stage on a portal's Victory screen"
    assert runner.carried_on == [], "no offer to wait out -- that was the other ending"


def test_the_last_repeat_leaves_the_victory_screen(monkeypatch):
    runner = _result_runner(monkeypatch, victory_screen=True)

    assert runner._handle_match_result(1, threading.Event(), dict(_PORTALS, play_mode="solo"), "win",
                                       "4m", None, repeat=False) is True
    assert runner.selected == []
    assert runner.clicked == ["leave_stage"]
    assert runner.carried_on == []


def test_a_select_portal_that_fails_fails_the_repeat(monkeypatch):
    runner = _result_runner(monkeypatch, victory_screen=True, select_ok=False)

    assert runner._handle_match_result(1, threading.Event(), dict(_PORTALS, play_mode="solo"), "win",
                                       "4m", None, repeat=True) is False


def test_an_offer_win_still_carries_on_into_the_next_round(monkeypatch):
    runner = _result_runner(monkeypatch, victory_screen=False)

    assert runner._handle_match_result(1, threading.Event(), dict(_PORTALS, play_mode="solo"), "win",
                                       "4m", None, repeat=True) is True
    assert runner.carried_on == [True]
    assert runner.selected == [] and runner.clicked == []
