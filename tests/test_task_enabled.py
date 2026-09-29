"""Switching a task off on the Task screen: it stays in the queue with all of
its settings, and the run skips it."""
import threading
from unittest.mock import Mock

import pytest

from core import runner as runner_module
from core.runner import MacroRunner


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.setattr(runner_module.wm, "is_window", lambda _hwnd: True)
    monkeypatch.setattr(runner_module.wm, "show_window", lambda _hwnd: None)
    monkeypatch.setattr(runner_module.wm, "activate_window", lambda _hwnd: True)
    monkeypatch.setattr(runner_module.wm, "is_process_elevated", lambda _hwnd: False)
    monkeypatch.setattr(runner_module.wm, "is_self_elevated", lambda: False)
    monkeypatch.setattr(runner_module.vision, "find_image", lambda *_a, **_k: None)
    r = MacroRunner(mouse=Mock(), keyboard=Mock(), log=Mock())
    r._stop_event = threading.Event()
    r._recover_to_lobby = Mock(return_value=True)
    r._bounty_settings = Mock(return_value={"enabled": False})
    r._challenge_has_ready_stage = Mock(return_value=False)
    r._run_crafting_if_due = Mock()
    r._run_fuel_refill_if_due = Mock()
    r._run_auto_shop_if_due = Mock()
    r._auto_shop_wants_in = Mock(return_value=False)
    r._run_task = Mock(return_value=True)
    return r


def _run(runner, *queue_passes):
    reads = iter(list(queue_passes) + [[]])
    runner._run(lambda: 123, lambda: next(reads), runner._stop_event,
                coords={}, default_walk_paths={}, webhook={})


def _said(runner):
    return " ".join(str(c.args[0]) for c in runner._log.call_args_list)


A = {"mode": "story", "map": "A", "repeat": 1}
B_OFF = {"mode": "story", "map": "B", "repeat": 1, "enabled": False}
C = {"mode": "story", "map": "C", "repeat": 1, "enabled": True}


def test_a_switched_off_task_is_skipped_and_the_rest_are_numbered_without_it(runner):
    _run(runner, [A, B_OFF, C])
    played = [(c.args[2]["map"], c.args[3], c.args[4]) for c in runner._run_task.call_args_list]
    assert played == [("A", 1, 2), ("C", 2, 2)]
    assert "2 task(s) queued, 1 switched off" in _said(runner)


def test_a_task_saved_before_the_switch_existed_still_plays(runner):
    _run(runner, [A])
    assert [c.args[2]["map"] for c in runner._run_task.call_args_list] == ["A"]


def test_a_queue_with_every_task_switched_off_goes_idle_and_says_why(runner):
    _run(runner, [B_OFF, dict(B_OFF, map="D")])
    runner._run_task.assert_not_called()
    assert "All 2 task(s) in the queue are switched off" in _said(runner)


def test_switching_a_task_back_on_between_passes_is_picked_up(runner):
    # The queue is re-read every pass, so a task switched on mid-run plays
    # from the next pass on.
    _run(runner, [A, B_OFF], [A, dict(B_OFF, enabled=True)])
    assert [c.args[2]["map"] for c in runner._run_task.call_args_list] == ["A", "A", "B"]


@pytest.mark.parametrize("value, plays", [
    (True, True), (None, True), ("yes", True), (False, False),
])
def test_only_an_explicit_off_skips_a_task(value, plays):
    task = {"mode": "story", "map": "X", "enabled": value}
    assert (MacroRunner._enabled_tasks([task]) == [task]) is plays
