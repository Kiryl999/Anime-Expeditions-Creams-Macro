"""Monster Clash: the Events menu's Battle Event, run as a Task Builder mode.

Events > Monster Clash > Play Event > Play - Choose Stage > Select Stage >
Start, then the usual Pre Start and battle. Now and then a cleared map spawns
a helicopter instead of the Victory screen -- only the Game Results button
shows. About 15s later E boards it, and the second map it flies to starts
empty: Pre Start again, Start Game, fight. The first map's result screen has
Repeat Stage; the helicopter's map has only Leave, so after it the next repeat
goes in through the Events menu again.
"""
import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core import runner as runner_module
from core import runner_monster_clash
from core.runner import MacroRunner
from core.runner_constants import (GAME_RESULTS_IMAGE, MONSTER_CLASH_ENTRY_IMAGES,
                                   MONSTER_CLASH_HELICOPTER_BOARD_AFTER,
                                   MONSTER_CLASH_HELICOPTER_BOARD_ATTEMPTS,
                                   MONSTER_CLASH_HELICOPTER_CONFIRM)

ROOT = Path(__file__).resolve().parent.parent
_SEEN = {"score": 0.97, "cx": 576, "cy": 600, "x": 520, "y": 585, "w": 112, "h": 30}


def _macro_runner():
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    runner.logged = []
    runner._log = lambda message, *_a, **_k: runner.logged.append(message)
    runner._set_status = lambda **_k: None
    return runner


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


# ---------------------------------------------------------------------------
# A task of its own
# ---------------------------------------------------------------------------

def test_a_monster_clash_task_plays_a_whole_run_as_its_match():
    runner = _macro_runner()
    seen = []
    runner._play_monster_clash_run = lambda hwnd, stop, task, walks, first_repeat=True, webhook=None: (
        seen.append(first_repeat) or "win")
    runner._start_game_or_reset_via_settings = MagicMock(side_effect=AssertionError("not for Monster Clash"))

    result = runner._play_one_match(1, threading.Event(), {"mode": "monster_clash"}, {}, first_repeat=True)

    assert result == "win"
    assert seen == [True]


def test_monster_clash_always_starts_solo():
    runner = _macro_runner()
    runner._monster_clash_preflight = lambda task: True
    entered = []
    runner._run_task_setup = lambda hwnd, stop, task, *a, **k: entered.append(task) or False
    runner._recover_to_lobby = lambda hwnd, stop: False

    runner._run_task(1, threading.Event(),
                     {"mode": "monster_clash", "map": "Monster Clash", "play_mode": "matchmaking"},
                     1, 1, {}, 1, 1, {}, None)

    assert entered and entered[0]["play_mode"] == "solo"


def test_a_task_without_its_crops_never_leaves_the_lobby():
    runner = _macro_runner()
    runner._monster_clash_preflight = lambda task: False
    runner._run_task_setup = MagicMock(side_effect=AssertionError("must not navigate"))

    assert runner._run_task(1, threading.Event(), {"mode": "monster_clash", "map": "Monster Clash"},
                            1, 1, {}, 1, 1, {}, None) is True


def test_the_preflight_names_the_crops_still_missing(monkeypatch):
    runner = _macro_runner()
    have = {"nav_event", GAME_RESULTS_IMAGE, "monster_clash"}
    monkeypatch.setattr(runner_monster_clash.vision, "template_variant_paths",
                        lambda name, *_a: [f"{name}.png"] if name in have else [])

    assert runner._monster_clash_preflight({}) is False
    assert "monster_clash_play_event" in runner.logged[-1]
    assert "monster_clash_choose_stage" in runner.logged[-1]

    have.update(MONSTER_CLASH_ENTRY_IMAGES)
    assert runner._monster_clash_preflight({}) is True


# ---------------------------------------------------------------------------
# Getting in
# ---------------------------------------------------------------------------

def _entry_runner(monkeypatch, missing=None):
    runner = _macro_runner()
    runner.clicked = []
    runner.backs = 0
    runner._ensure_lobby = lambda *_a: True
    runner._checkpoint = lambda _stop: False

    def click(_hwnd, name, *_a, **_k):
        runner.clicked.append(name)
        return None if name == missing else _SEEN

    def back(*_a):
        runner.backs += 1

    runner._click_found_image = click
    runner._spam_back_until_gone = back
    monkeypatch.setattr(runner_monster_clash.time, "sleep", lambda _s: None)
    return runner


def test_monster_clash_is_reached_through_the_events_menu(monkeypatch):
    runner = _entry_runner(monkeypatch)

    assert runner._reach_monster_clash_stage(1, threading.Event()) is True
    assert runner.clicked == ["nav_event", "monster_clash", "monster_clash_play_event",
                              "monster_clash_choose_stage"]


def test_a_screen_that_never_shows_backs_out_to_the_lobby(monkeypatch):
    runner = _entry_runner(monkeypatch, missing="monster_clash_play_event")

    assert runner._reach_monster_clash_stage(1, threading.Event()) is False
    assert runner.clicked[-1] == "monster_clash_play_event"
    assert runner.backs == 1


def test_select_stage_and_start_follow_the_choose_stage_click():
    runner = _macro_runner()
    runner._run_monster_clash_setup = lambda *_a: True
    runner._enter_selected_stage = lambda hwnd, stop, task, mode, coords, webhook=None: mode

    task = {"mode": "monster_clash", "map": "Monster Clash", "play_mode": "solo"}
    assert runner._run_task_setup(1, threading.Event(), task, "monster_clash", "Monster Clash",
                                  {}, 1, 1) == "monster_clash"


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def _run_runner(results, boarded=True):
    runner = _macro_runner()
    runner.prestarts = []
    runner.starts = 0
    runner.boards = 0
    results = iter(results)

    def prestart(_hwnd, _stop, task, _walks, first_repeat, *a, **k):
        runner.prestarts.append((task.get("macro"), first_repeat))
        return True

    def press(*_a, **_k):
        runner.starts += 1
        return True

    def board(*_a):
        runner.boards += 1
        return boarded

    runner._run_prestart = prestart
    runner._press_start_game = press
    runner._begin_battle = lambda _task: []
    runner._checkpoint = lambda _stop: False
    runner._wait_for_match_result = lambda *a, **k: next(results)
    runner._board_monster_clash_helicopter = board
    runner._find_start_game_button = lambda *_a, **_k: ("nav_start_game", _SEEN)
    return runner


_TASK = {"mode": "monster_clash", "map": "Monster Clash", "macro": "Map", "helicopter_macro": "Heli"}


def test_a_run_without_a_helicopter_is_the_one_map():
    runner = _run_runner(["win"])

    assert runner._play_monster_clash_run(1, threading.Event(), _TASK, {}, first_repeat=True) == "win"
    assert runner.prestarts == [("Map", True)]
    assert runner.boards == 0


def test_a_helicopter_takes_the_run_to_a_second_map_placed_with_its_own_macro():
    runner = _run_runner(["helicopter", "win"])

    assert runner._play_monster_clash_run(1, threading.Event(), _TASK, {}, first_repeat=True) == "win"
    assert runner.boards == 1
    # A new map: its Pre Start runs in full (camera, Team Loadout, Once blocks).
    assert runner.prestarts == [("Map", True), ("Heli", True)]
    assert runner.starts == 2


def test_same_as_above_places_the_second_map_with_the_first_macro():
    runner = _run_runner(["helicopter", "loss"])

    assert runner._play_monster_clash_run(
        1, threading.Event(), dict(_TASK, helicopter_macro=""), {}, first_repeat=True) == "loss"
    assert runner.prestarts == [("Map", True), ("Map", True)]


def test_a_helicopter_that_cannot_be_boarded_abandons_the_run():
    runner = _run_runner(["helicopter"], boarded=False)

    assert runner._play_monster_clash_run(1, threading.Event(), _TASK, {}, first_repeat=True) is None
    assert runner.prestarts == [("Map", True)]


def test_a_run_that_went_on_by_helicopter_is_reported_as_one():
    runner = _run_runner(["helicopter", "win", "win"])

    runner._play_monster_clash_run(1, threading.Event(), _TASK, {}, first_repeat=True)
    assert runner._monster_clash_report_task(_TASK)["map"] == "Monster Clash (Helicopter)"
    assert _TASK["map"] == "Monster Clash", "the task itself keeps its name"

    # The next run starts over: no helicopter, no suffix.
    runner._play_monster_clash_run(1, threading.Event(), _TASK, {}, first_repeat=False)
    assert runner._monster_clash_report_task(_TASK)["map"] == "Monster Clash"


def test_other_modes_are_never_reported_as_a_helicopter_run():
    runner = _macro_runner()
    runner._monster_clash_took_helicopter = True
    task = {"mode": "story", "map": "Leaf Village"}

    assert runner._monster_clash_report_task(task) is task


# ---------------------------------------------------------------------------
# Boarding
# ---------------------------------------------------------------------------

def _board_runner(gone_after):
    """gone_after: after how many E presses the Game Results button is gone
    (None: never)."""
    runner = _macro_runner()
    runner.sleeps = []
    runner.screenshots = []
    runner._checkpoint = lambda _stop: False
    runner._interruptible_sleep = lambda seconds, _stop=None: runner.sleeps.append(seconds)
    runner._save_debug_screenshot_unconditional = lambda _hwnd, name: runner.screenshots.append(name)
    runner._monster_clash_game_results = lambda _hwnd: (
        None if gone_after is not None and runner._keyboard.tap.call_count >= gone_after else _SEEN)
    return runner


def test_e_boards_the_helicopter_once_it_takes_boarders(monkeypatch):
    monkeypatch.setattr(runner_monster_clash.wm, "activate_window", lambda _hwnd: True)
    runner = _board_runner(gone_after=1)

    assert runner._board_monster_clash_helicopter(1, threading.Event()) is True
    runner._keyboard.tap.assert_called_once_with(ord("E"))
    # About 15s after the button showed up -- it has been up for the confirm
    # time already when this starts.
    assert runner.sleeps[0] == pytest.approx(MONSTER_CLASH_HELICOPTER_BOARD_AFTER
                                             - MONSTER_CLASH_HELICOPTER_CONFIRM)


def test_e_is_pressed_again_while_game_results_stays(monkeypatch):
    monkeypatch.setattr(runner_monster_clash.wm, "activate_window", lambda _hwnd: True)
    runner = _board_runner(gone_after=2)

    assert runner._board_monster_clash_helicopter(1, threading.Event()) is True
    assert runner._keyboard.tap.call_count == 2


def test_boarding_gives_up_after_its_attempts(monkeypatch):
    monkeypatch.setattr(runner_monster_clash.wm, "activate_window", lambda _hwnd: True)
    runner = _board_runner(gone_after=None)

    assert runner._board_monster_clash_helicopter(1, threading.Event()) is False
    assert runner._keyboard.tap.call_count == MONSTER_CLASH_HELICOPTER_BOARD_ATTEMPTS
    assert runner.screenshots == ["monster_clash_helicopter_not_boarded"]


# ---------------------------------------------------------------------------
# Telling the helicopter from a result screen
# ---------------------------------------------------------------------------

def _poll(monkeypatch, on_screen, watch_helicopter=True):
    """Run the match poll loop with on_screen(tick) -> the set of crop names
    visible on that poll."""
    runner = _macro_runner()
    clock = _Clock()
    runner.tick = 0
    runner._checkpoint = lambda _stop: False
    runner._tick_loop_phases = lambda *_a, **_k: None

    def sleep(seconds):
        clock.sleep(seconds)
        runner.tick += 1

    monkeypatch.setattr(runner_module.time, "time", clock.time)
    monkeypatch.setattr(runner_module.time, "sleep", sleep)
    monkeypatch.setattr(runner_module.vision, "find_image",
                        lambda hwnd, name, **k: _SEEN if name in on_screen(runner.tick) else None)
    task = {"mode": "monster_clash", "map": "Monster Clash"}
    return runner._wait_for_match_result(1, threading.Event(), task=task, mode="monster_clash",
                                         watch_helicopter=watch_helicopter)


def test_a_lone_game_results_button_is_the_helicopter(monkeypatch):
    assert _poll(monkeypatch, lambda tick: {GAME_RESULTS_IMAGE}) == "helicopter"


def test_victory_is_still_victory_with_game_results_up(monkeypatch):
    assert _poll(monkeypatch, lambda tick: {GAME_RESULTS_IMAGE, "victory"}) == "win"


def test_game_results_before_a_victory_slides_in_is_not_the_helicopter(monkeypatch):
    # Up for one poll, then the result panel arrives.
    assert _poll(monkeypatch, lambda tick: {GAME_RESULTS_IMAGE} if tick == 0
                 else {GAME_RESULTS_IMAGE, "victory"}) == "win"


def test_other_modes_never_read_game_results_as_a_helicopter(monkeypatch):
    assert _poll(monkeypatch, lambda tick: {GAME_RESULTS_IMAGE} if tick < 10
                 else {"victory"}, watch_helicopter=False) == "win"


# ---------------------------------------------------------------------------
# Repeat Stage -- or back to the lobby after the helicopter
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("task, in_place", [
    ({"mode": "story", "play_mode": "solo"}, True),
    ({"mode": "story", "play_mode": "matchmaking"}, False),
    ({"mode": "monster_clash", "play_mode": "solo"}, True),
])
def test_only_matchmaking_always_goes_back_through_the_lobby(task, in_place):
    assert MacroRunner._repeats_in_place(task) is in_place


@pytest.mark.parametrize("took_helicopter, in_place", [(False, True), (True, False)])
def test_the_next_run_goes_in_through_the_events_menu_only_after_the_helicopter(took_helicopter, in_place):
    runner = _macro_runner()
    runner._monster_clash_took_helicopter = took_helicopter

    assert runner._next_repeat_in_place(dict(_TASK, play_mode="solo")) is in_place
    # Another mode is never held to a Monster Clash run's helicopter.
    assert runner._next_repeat_in_place({"mode": "story", "play_mode": "solo"}) is True


def _result_screen_runner(monkeypatch, took_helicopter):
    runner = _macro_runner()
    runner._monster_clash_took_helicopter = took_helicopter
    runner.clicked = []
    runner._click_and_verify_gone = lambda hwnd, stop, name, timeout, **k: runner.clicked.append(name) or True
    runner._wait_for_image_gone = lambda *_a: True
    runner._click_return_to_lobby_if_found = lambda *_a: True
    runner._dismiss_reward_card_if_found = lambda _hwnd: False
    runner._clear_result_obtainment_modal = lambda *_a: True
    runner._finish_match_result_background = lambda *_a: None
    monkeypatch.setattr(runner_module.time, "sleep", lambda _s: None)
    monkeypatch.setattr(runner_module.wm, "get_window_rect_screen", lambda _hwnd: (0, 0, 1152, 756))
    return runner


@pytest.mark.parametrize("took_helicopter, button", [(False, "repeat_stage"), (True, "leave_stage")])
def test_a_run_repeats_the_stage_unless_the_helicopter_took_it_on(monkeypatch, took_helicopter, button):
    runner = _result_screen_runner(monkeypatch, took_helicopter)

    assert runner._handle_match_result(1, threading.Event(), dict(_TASK, play_mode="solo"), "win",
                                       "5m", None, repeat=True) is True
    # The helicopter's map has no Repeat Stage -- only Leave.
    assert runner.clicked == [button]


@pytest.mark.parametrize("took_helicopter, shown", [(True, "Monster Clash (Helicopter)"),
                                                    (False, "Monster Clash")])
def test_the_run_history_tells_a_helicopter_run_apart(monkeypatch, took_helicopter, shown):
    runner = _result_screen_runner(monkeypatch, took_helicopter)
    reported = []
    done = threading.Event()
    # Reporting runs on its own thread -- see _handle_match_result.
    runner._finish_match_result_background = lambda _result, map_name, _duration, task, *_a: (
        reported.append((map_name, task["map"])), done.set())

    runner._handle_match_result(1, threading.Event(), dict(_TASK, play_mode="solo"), "win",
                                "9m", None, repeat=False)

    assert done.wait(5)
    # The history row and the result webhook both get the name.
    assert reported == [(shown, shown)]


# ---------------------------------------------------------------------------
# The Task Builder and the shipped folders
# ---------------------------------------------------------------------------

def test_every_crop_of_the_way_in_ships():
    for name in MONSTER_CLASH_ENTRY_IMAGES:
        assert (ROOT / "Assets" / "ui" / name / f"{name}.png").is_file(), f"{name} has no crop"


def test_a_preset_warns_about_a_missing_helicopter_macro(monkeypatch):
    from core import task_presets
    from core import templates as tpl
    from main import Api

    monkeypatch.setattr(task_presets, "load_preset", lambda name: {"name": name, "found": True, "tasks": [
        {"mode": "monster_clash", "macro": "Map", "helicopter_macro": "Heli"},
    ]})
    monkeypatch.setattr(tpl, "list_templates", lambda: ["Map"])
    api = object.__new__(Api)
    api.push_log = lambda _message: None

    assert api.load_task_preset("Clash")["missing_macros"] == ["Heli"]


_EXTRACT = """
const fs = require('fs');
const src = fs.readFileSync(process.env.APP_JS, 'utf8');
function extract(name) {
  const s = src.indexOf('function ' + name + '(');
  if (s === -1) throw new Error(name + ' not found in ui/app.js');
  let d = 0, i = src.indexOf('{', s);
  for (; i < src.length; i++) {
    if (src[i] === '{') d++;
    else if (src[i] === '}' && --d === 0) return src.slice(s, i + 1);
  }
  throw new Error('unbalanced braces in ' + name);
}
const block = src.match(/  monster_clash: \\{[\\s\\S]*?\\n  \\},/);
if (!block) throw new Error('TASK_DATA.monster_clash not found in ui/app.js');
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_switching_a_task_to_monster_clash_makes_it_a_solo_run_with_two_macros(tmp_path):
    script = tmp_path / "t.js"
    script.write_text(_EXTRACT + """
const TASK_DATA = { story: { label: 'Story', maps: ['School Grounds'], stages: ['1'], difficulties: ['Normal'] } };
eval('TASK_DATA.monster_clash = {' + block[0].slice(block[0].indexOf('{') + 1, -1));
const DEFAULT_INFINITE_WAVE_LIMIT = 20;
let taskCards = [{ id: 't1', mode: 'story', map: 'School Grounds', stage: '1', difficulty: 'Normal',
                   repeat: 2, play_mode: 'matchmaking', macro: 'Map', helicopter_macro: 'Heli' }];
function findTask(id) { return taskCards.find(t => t.id === id); }
function updateQueueRowInPlace() {}
function renderTaskBuilder() {}
function saveTaskQueue() {}
eval(extract('setTaskProp'));
eval(extract('taskSummary'));
eval(extract('taskMacroNames'));
setTaskProp('t1', 'mode', 'monster_clash');
const t = taskCards[0];
console.log(JSON.stringify({ map: t.map, playMode: t.play_mode, summary: taskSummary(t),
                             macros: taskMacroNames(t) }));
""", encoding="utf-8")
    # Node writes UTF-8; read as the Windows code page, the "▸" is mangled.
    proc = subprocess.run(["node", str(script)], capture_output=True, encoding="utf-8", timeout=60,
                          env={**os.environ, "APP_JS": str(ROOT / "ui" / "app.js")})
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip().splitlines()[-1])

    assert out["map"] == "Monster Clash"
    assert out["playMode"] == "solo"
    assert out["summary"]["title"] == "Monster Clash"
    assert "Helicopter ▸ Heli" in out["summary"]["meta"]
    assert not re.search(r"\b(Solo|Matchmaking)\b", out["summary"]["meta"])
    assert out["macros"] == ["Map", "Heli"]
