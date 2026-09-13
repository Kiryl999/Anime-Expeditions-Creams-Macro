import threading
from unittest.mock import MagicMock

import pytest

from core import runner as runner_module
from core.runner import MacroRunner


def _runner():
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    runner._set_status = MagicMock()
    return runner


@pytest.mark.parametrize(
    "task, expected",
    [
        ({"mode": "story", "stage": "Infinite", "infinite_wave_limit": 50}, 50),
        ({"mode": "story", "stage": "Infinite"}, 20),
        ({"mode": "story", "stage": "Infinite", "infinite_wave_limit": "bad"}, 20),
        ({"mode": "story", "stage": "Infinite", "infinite_wave_limit": 0}, 20),
        ({"mode": "story", "stage": "5", "infinite_wave_limit": 50}, None),
        ({"mode": "raid", "stage": "Infinite", "infinite_wave_limit": 50}, None),
        # Event > Infinite & Fishing uses the same wave-limit exit as Story > Infinite.
        ({"mode": "event", "stage": "infinite", "infinite_wave_limit": 40}, 40),
        ({"mode": "event", "stage": "infinite"}, 20),
        ({"mode": "event", "stage": "infinite", "infinite_wave_limit": "bad"}, 20),
        ({"mode": "event", "stage": "infinite", "infinite_wave_limit": 0}, 20),
        # Portal Mode (and any legacy event stage) is not an Infinite run.
        ({"mode": "event", "stage": "portal", "infinite_wave_limit": 40}, None),
        ({"mode": "event", "stage": "1", "infinite_wave_limit": 40}, None),
    ],
)
def test_infinite_wave_limit_only_applies_to_infinite_stages(task, expected):
    assert MacroRunner._infinite_wave_limit(task) == expected


def test_wave_limit_finishes_selected_wave_then_requires_a_confirming_read(monkeypatch):
    runner = _runner()
    readings = iter(((20, None), (21, None), (21, None)))
    left = []
    state = {}

    monkeypatch.setattr(
        runner_module.vision, "capture_window_region_bgr", lambda *_args: object())
    monkeypatch.setattr(runner_module.wave_module, "read_wave", lambda _image: next(readings))
    monkeypatch.setattr(
        runner, "_leave_infinite_at_wave_limit",
        lambda _hwnd, _stop, limit: left.append(limit) or True)

    for _ in range(3):
        state["next_check"] = 0
        result = runner._check_infinite_wave_limit(123, threading.Event(), 20, state)

    assert result == "wave_limit"
    assert left == [20]


def test_finite_wave_badge_cannot_trigger_infinite_exit(monkeypatch):
    runner = _runner()
    state = {}
    left = []

    monkeypatch.setattr(
        runner_module.vision, "capture_window_region_bgr", lambda *_args: object())
    monkeypatch.setattr(runner_module.wave_module, "read_wave", lambda _image: (21, 30))
    monkeypatch.setattr(
        runner, "_leave_infinite_at_wave_limit",
        lambda *_args: left.append(True) or True)

    for _ in range(3):
        state["next_check"] = 0
        assert runner._check_infinite_wave_limit(
            123, threading.Event(), 20, state) is None

    assert left == []


def test_impossible_unlimited_reads_cannot_confirm_the_exit_wave(monkeypatch):
    runner = _runner()
    readings = iter(((1414, None), (46, None), (46, None)))
    left = []
    state = {}

    monkeypatch.setattr(
        runner_module.vision, "capture_window_region_bgr", lambda *_args: object())
    monkeypatch.setattr(runner_module.wave_module, "read_wave", lambda _image: next(readings))
    monkeypatch.setattr(
        runner, "_leave_infinite_at_wave_limit",
        lambda _hwnd, _stop, limit: left.append(limit) or True)

    for _ in range(3):
        state["next_check"] = 0
        result = runner._check_infinite_wave_limit(
            123, threading.Event(), 45, state)

    assert result == "wave_limit"
    assert left == [45]


def test_confirmed_later_wave_substitutes_after_target_wave_was_seen(monkeypatch):
    runner = _runner()
    state = {}
    left = []
    readings = iter(((45, None), (47, None), (47, None)))

    monkeypatch.setattr(
        runner_module.vision, "capture_window_region_bgr", lambda *_args: object())
    monkeypatch.setattr(
        runner_module.wave_module, "read_wave", lambda _image: next(readings))
    monkeypatch.setattr(
        runner, "_leave_infinite_at_wave_limit",
        lambda _hwnd, _stop, limit: left.append(limit) or True)

    for _ in range(3):
        state["next_check"] = 0
        result = runner._check_infinite_wave_limit(
            123, threading.Event(), 45, state)

    assert result == "wave_limit"
    assert left == [45]


def test_later_wave_cannot_exit_without_observing_target_wave(monkeypatch):
    runner = _runner()
    state = {}
    left = []

    monkeypatch.setattr(
        runner_module.vision, "capture_window_region_bgr", lambda *_args: object())
    monkeypatch.setattr(runner_module.wave_module, "read_wave", lambda _image: (55, None))
    monkeypatch.setattr(
        runner, "_leave_infinite_at_wave_limit",
        lambda *_args: left.append(True) or True)

    for _ in range(3):
        state["next_check"] = 0
        assert runner._check_infinite_wave_limit(
            123, threading.Event(), 45, state) is None

    assert left == []


def test_infinite_limit_is_checked_before_battle_blocks():
    runner = _runner()
    runner._check_infinite_wave_limit = MagicMock(return_value="wave_limit")
    runner._run_battle_blocks_tick = MagicMock()

    result = runner._wait_for_match_result(
        123,
        threading.Event(),
        battle_blocks=[{"type": "upgrade_unit"}],
        task={
            "mode": "story",
            "stage": "Infinite",
            "infinite_wave_limit": 45,
        },
    )

    assert result == "wave_limit"
    runner._run_battle_blocks_tick.assert_not_called()


def test_failed_leave_reports_failure_to_match_loop(monkeypatch):
    runner = _runner()
    state = {"confirmations": 1, "confirmation_wave": 11}

    monkeypatch.setattr(
        runner_module.vision, "capture_window_region_bgr", lambda *_args: object())
    monkeypatch.setattr(runner_module.wave_module, "read_wave", lambda _image: (11, None))
    monkeypatch.setattr(runner, "_leave_infinite_at_wave_limit", lambda *_args: False)

    assert runner._check_infinite_wave_limit(
        123, threading.Event(), 10, state) == "failed"


# ---------------------------------------------------------------------------
# Tidal Siege: restart in place at the limit instead of leaving
# ---------------------------------------------------------------------------

def _at_exit_wave(monkeypatch):
    """A wave-limit state one confirming read away from the wave-10 exit."""
    monkeypatch.setattr(
        runner_module.vision, "capture_window_region_bgr", lambda *_args: object())
    monkeypatch.setattr(runner_module.wave_module, "read_wave", lambda _image: (11, None))
    return {"confirmations": 1, "confirmation_wave": 11}


def _nothing_due(runner):
    runner._challenge_has_ready_stage = lambda: False
    runner._crafting_wants_in = lambda *_a, **_k: False
    runner._fuel_wants_in = lambda: False
    runner._auto_shop_wants_in = lambda: False
    runner._memory_refresh_due = lambda: False


def test_tidal_siege_restarts_in_place_instead_of_leaving(monkeypatch):
    runner = _runner()
    state = _at_exit_wave(monkeypatch)
    _nothing_due(runner)
    runner._infinite_restart_ok = True
    runner._restart_infinite_at_wave_limit = MagicMock(return_value=True)
    runner._leave_infinite_at_wave_limit = MagicMock(return_value=True)

    assert runner._check_infinite_wave_limit(123, threading.Event(), 10, state) == "restarted"
    runner._restart_infinite_at_wave_limit.assert_called_once()
    runner._leave_infinite_at_wave_limit.assert_not_called()


def test_a_restart_that_does_not_go_through_falls_back_to_leaving(monkeypatch):
    runner = _runner()
    state = _at_exit_wave(monkeypatch)
    _nothing_due(runner)
    runner._infinite_restart_ok = True
    runner._restart_infinite_at_wave_limit = MagicMock(return_value=False)
    runner._leave_infinite_at_wave_limit = MagicMock(return_value=True)

    assert runner._check_infinite_wave_limit(123, threading.Event(), 10, state) == "wave_limit"
    runner._leave_infinite_at_wave_limit.assert_called_once()


@pytest.mark.parametrize("due", [
    "_challenge_has_ready_stage", "_crafting_wants_in", "_fuel_wants_in",
    "_auto_shop_wants_in", "_memory_refresh_due",
])
def test_anything_waiting_for_the_lobby_takes_the_old_exit(monkeypatch, due):
    """Those all run from the lobby between repeats -- a run that only ever
    restarted would never get to them."""
    runner = _runner()
    state = _at_exit_wave(monkeypatch)
    _nothing_due(runner)
    setattr(runner, due, lambda *_a, **_k: True)
    runner._infinite_restart_ok = True
    runner._restart_infinite_at_wave_limit = MagicMock(return_value=True)
    runner._leave_infinite_at_wave_limit = MagicMock(return_value=True)

    assert runner._check_infinite_wave_limit(123, threading.Event(), 10, state) == "wave_limit"
    runner._restart_infinite_at_wave_limit.assert_not_called()


def test_restart_is_off_unless_the_task_loop_allows_it(monkeypatch):
    """Auto Bounty plays Infinite too and relies on the exit, and so does a
    task's last repeat -- only _run_task switches the restart on."""
    runner = _runner()
    state = _at_exit_wave(monkeypatch)
    _nothing_due(runner)
    runner._restart_infinite_at_wave_limit = MagicMock(return_value=True)
    runner._leave_infinite_at_wave_limit = MagicMock(return_value=True)

    assert runner._infinite_restart_ok is False
    assert runner._check_infinite_wave_limit(123, threading.Event(), 10, state) == "wave_limit"
    runner._restart_infinite_at_wave_limit.assert_not_called()


def test_a_restart_ends_the_match_poll_like_the_exit_does():
    runner = _runner()
    runner._check_infinite_wave_limit = MagicMock(return_value="restarted")

    result = runner._wait_for_match_result(
        123, threading.Event(),
        task={"mode": "event", "stage": "infinite", "infinite_wave_limit": 20})

    assert result == "restarted"


_RESTART = {"name": "restart", "score": 0.97, "cx": 1, "cy": 1}
_CONFIRM = {"name": "confirm", "score": 0.96, "cx": 2, "cy": 2}


def _restart_runner(monkeypatch, on_screen, start_game_back=True):
    """``on_screen`` maps an image name to what wait_for_image returns for it
    on successive calls (the last entry repeats)."""
    runner = _runner()
    clicked, found = [], []
    runner._release_quick_place_shift = MagicMock()
    runner._interruptible_sleep = MagicMock()
    runner._close_settings_if_open = MagicMock()
    runner._save_debug_screenshot_unconditional = MagicMock(return_value=None)
    runner._best_match_score = MagicMock(return_value=0.81)
    runner._click_found_image = (
        lambda _hwnd, name, _timeout, _stop=None, **_k: found.append(name) or {"score": 0.99})

    def wait_for_image(_hwnd, name, timeout=None, stop_event=None, **_k):
        seq = on_screen.get(name) or [None]
        return seq.pop(0) if len(seq) > 1 else seq[0]

    monkeypatch.setattr(runner_module.vision, "wait_for_image", wait_for_image)
    monkeypatch.setattr(runner_module.vision, "click_match",
                        lambda _mouse, _hwnd, match: clicked.append(match["name"]))
    runner._find_start_game_button = lambda *_a, **_k: (
        ("nav_start_game", {"score": 1.0}) if start_game_back else (None, None))
    return runner, clicked, found


def test_restart_goes_gear_then_restart_then_confirm_and_waits_for_start_game(monkeypatch):
    runner, clicked, found = _restart_runner(
        monkeypatch, {"restart_btn": [_RESTART], "restart_confirm": [_CONFIRM]})

    assert runner._restart_infinite_at_wave_limit(123, threading.Event(), 20) is True
    assert found == ["nav_settings"]
    assert clicked == ["restart", "confirm"]
    runner._keyboard.type_text.assert_not_called()


def test_restart_searches_settings_when_the_button_is_not_in_view(monkeypatch):
    runner, clicked, found = _restart_runner(
        monkeypatch, {"restart_btn": [None, _RESTART], "restart_confirm": [_CONFIRM]})

    assert runner._restart_infinite_at_wave_limit(123, threading.Event(), 20) is True
    assert found == ["nav_settings", "nav_search"]
    runner._keyboard.type_text.assert_called_once_with("restart game")
    assert clicked == ["restart", "confirm"]


def test_restart_without_a_confirmation_still_counts_once_start_game_is_back(monkeypatch):
    runner, clicked, _ = _restart_runner(monkeypatch, {"restart_btn": [_RESTART]})

    assert runner._restart_infinite_at_wave_limit(123, threading.Event(), 20) is True
    assert clicked == ["restart"]


def test_an_unmatched_confirmation_leaves_a_screenshot_and_the_score(monkeypatch):
    """The first live run stopped here: the dialog was up, the old crop did
    not match it, and nothing said how close it got."""
    runner, _, _ = _restart_runner(monkeypatch, {"restart_btn": [_RESTART]},
                                   start_game_back=False)

    assert runner._restart_infinite_at_wave_limit(123, threading.Event(), 20) is False
    runner._save_debug_screenshot_unconditional.assert_any_call(123, "infinite_restart_no_confirm")
    logged = [c.args[0] for c in runner._log.call_args_list]
    assert any("restart_confirm" in line and "best match 0.81" in line for line in logged)


def test_restart_is_a_failure_until_start_game_comes_back(monkeypatch):
    runner, clicked, _ = _restart_runner(
        monkeypatch, {"restart_btn": [_RESTART], "restart_confirm": [_CONFIRM]},
        start_game_back=False)

    assert runner._restart_infinite_at_wave_limit(123, threading.Event(), 20) is False
    assert clicked == ["restart", "confirm"]


def test_no_restart_button_anywhere_closes_settings_and_fails(monkeypatch):
    runner, clicked, _ = _restart_runner(monkeypatch, {"restart_btn": [None, None]})

    assert runner._restart_infinite_at_wave_limit(123, threading.Event(), 20) is False
    assert clicked == []
    runner._close_settings_if_open.assert_called_once()


def _task_loop_runner(monkeypatch, results):
    """A real _run_task whose matches return ``results`` in turn. Records
    whether the restart was allowed for each repeat as it was played."""
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    runner._stop_event = threading.Event()
    allowed = []

    def play(*_args, **_kwargs):
        allowed.append(runner._infinite_restart_ok)
        return results.pop(0)

    runner._play_one_match = MagicMock(side_effect=play)
    runner._record_result = MagicMock()
    runner._run_task_setup = MagicMock(return_value=True)
    runner._handle_match_result = MagicMock(return_value=True)
    runner._wait_teleport_in = MagicMock(return_value=True)
    runner._checkpoint = MagicMock(return_value=False)
    runner._challenge_has_ready_stage = MagicMock(return_value=False)
    runner._crafting_wants_in = MagicMock(return_value=False)
    runner._fuel_wants_in = MagicMock(return_value=False)
    runner._auto_shop_wants_in = MagicMock(return_value=False)
    runner._current_hwnd = 123
    monkeypatch.setattr(runner_module.wm, "is_window", lambda _hwnd: True)
    return runner, allowed


def _run_task(runner, task):
    return runner._run_task(123, runner._stop_event, task, 1, 1, {}, None, None, {}, {})


def test_after_a_restart_the_next_repeat_only_presses_start_game(monkeypatch):
    runner, allowed = _task_loop_runner(monkeypatch, ["restarted", "win"])

    assert _run_task(runner, {"map": "Event", "mode": "event", "stage": "infinite", "repeat": 2}) is True

    calls = runner._play_one_match.call_args_list
    assert [c.kwargs["skip_prestart"] for c in calls] == [False, True]
    assert allowed == [True, False], "never on the last repeat -- it has to end in the lobby"
    runner._run_task_setup.assert_called_once()          # only the first entry
    runner._wait_teleport_in.assert_not_called()         # a restart stays in the stage
    assert runner._handle_match_result.call_count == 1   # the final result, not the restart


def test_a_restart_counts_as_a_win_on_the_scoreboard(monkeypatch):
    """No Victory screen follows a restart, so it has to be counted here or
    the Scoreboard sits still while the run works. Anything but "win" is
    booked as a loss by the Scoreboard, so the result must be exactly that."""
    runner, _ = _task_loop_runner(monkeypatch, ["restarted", "restarted", "win"])

    _run_task(runner, {"map": "Event", "mode": "event", "stage": "infinite", "repeat": 3})

    restart_records = [c for c in runner._record_result.call_args_list if c.args[0] == "win"]
    assert len(restart_records) == 2
    assert all(c.args[1] == "Event" for c in restart_records)


def test_a_scoreboard_failure_does_not_stop_the_run(monkeypatch):
    runner, _ = _task_loop_runner(monkeypatch, ["restarted", "win"])
    runner._record_result = MagicMock(side_effect=OSError("settings.json locked"))

    assert _run_task(runner, {"map": "Event", "mode": "event", "stage": "infinite", "repeat": 2}) is True
    assert runner._play_one_match.call_count == 2


def test_story_infinite_is_never_allowed_to_restart(monkeypatch):
    runner, allowed = _task_loop_runner(monkeypatch, ["wave_limit", "wave_limit"])

    _run_task(runner, {"map": "Forest", "mode": "story", "stage": "Infinite", "repeat": 2})

    assert allowed == [False, False]
