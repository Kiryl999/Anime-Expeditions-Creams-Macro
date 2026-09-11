import threading
from unittest.mock import Mock, call
import pytest

from core import runner as runner_module
from core.runner import MacroRunner
from core.diagnostics import FailureCategory, RecoveryAction, FailureReport, create_failure_report

@pytest.fixture
def runner():
    mock_mouse = Mock()
    mock_keyboard = Mock()
    mock_log = Mock()
    r = MacroRunner(mouse=mock_mouse, keyboard=mock_keyboard, log=mock_log)
    r._stop_event = threading.Event()
    r._attempt_rejoin = Mock()
    r._recover_to_lobby = Mock()
    return r

def test_handle_structured_failure_retry_step(runner):
    report = create_failure_report(
        code="TEST_ERR_01",
        phase="VISUAL_CHECK",
        retryable=True,
        category=FailureCategory.TRANSIENT_VISUAL,
        user_message="Timeout on UI",
        user_action="Clicking button",
        recovery_action=RecoveryAction.RETRY_STEP
    )
    result = runner._handle_structured_failure(report)
    assert result is True

def test_handle_structured_failure_return_to_lobby_disconnect(runner):
    report = create_failure_report(
        code="ROBLOX_DISCONNECTED",
        phase="MATCH_LOOP",
        retryable=False,
        category=FailureCategory.GAME_STATE,
        user_message="Roblox disconnected",
        user_action="Waiting for match",
        recovery_action=RecoveryAction.RETURN_TO_LOBBY
    )
    hwnd = Mock()
    result = runner._handle_structured_failure(report, hwnd=hwnd)
    assert result is False
    runner._attempt_rejoin.assert_called_once_with(hwnd, runner._stop_event)
    runner._recover_to_lobby.assert_not_called()

def test_handle_structured_failure_return_to_lobby_ui_timeout(runner):
    report = create_failure_report(
        code="TEST_ERR_03",
        phase="LOBBY_NAV",
        retryable=False,
        category=FailureCategory.TRANSIENT_VISUAL,
        user_message="Menu did not load",
        user_action="Navigating",
        recovery_action=RecoveryAction.RETURN_TO_LOBBY
    )
    hwnd = Mock()
    result = runner._handle_structured_failure(report, hwnd=hwnd)
    assert result is False
    runner._recover_to_lobby.assert_called_once_with(hwnd, runner._stop_event)

def test_handle_structured_failure_stop_runner(runner):
    report = create_failure_report(
        code="TEST_ERR_04",
        phase="RUNNER_LOOP",
        retryable=False,
        category=FailureCategory.INTERNAL,
        user_message="Fatal error",
        user_action="Unknown state",
        recovery_action=RecoveryAction.STOP_RUNNER
    )
    assert not runner._stop_event.is_set()
    result = runner._handle_structured_failure(report)
    assert result is False
    assert runner._stop_event.is_set()

def test_recovery_halts_when_retry_threshold_reached(runner):
    # Testing that a bounded retry loop will properly halt when limit is reached
    # simulating a loop that uses _handle_structured_failure
    max_retries = 3
    retries = 0
    hwnd = Mock()

    report = create_failure_report(
        code="TEST_ERR_05",
        phase="LOAD_TEAM",
        retryable=True,
        category=FailureCategory.TRANSIENT_VISUAL,
        user_message="Timeout loading team",
        user_action="load_team",
        recovery_action=RecoveryAction.RETRY_STEP
    )

    success = False
    for attempt in range(max_retries):
        retries += 1
        # simulating a failure and check
        if runner._handle_structured_failure(report, hwnd=hwnd):
            continue

    assert retries == max_retries
    assert not success


def test_guarded_phase_logs_exception_and_recovers_to_lobby(runner):
    def fail():
        raise RuntimeError("simulated vision failure")

    completed, result = runner._run_guarded_phase(
        "Auto Bounty", 123, runner._stop_event, fail)

    assert completed is False
    assert result is None
    runner._recover_to_lobby.assert_called_once_with(123, runner._stop_event)
    assert any(
        "Unexpected error during Auto Bounty: RuntimeError: simulated vision failure"
        in call_args.args[0]
        for call_args in runner._log.call_args_list
    )


def test_bounty_exception_does_not_prevent_challenge_or_queue(monkeypatch, runner):
    monkeypatch.setattr(runner_module.wm, "is_window", lambda _hwnd: True)
    monkeypatch.setattr(runner_module.wm, "show_window", lambda _hwnd: None)
    monkeypatch.setattr(runner_module.wm, "activate_window", lambda _hwnd: True)
    monkeypatch.setattr(runner_module.wm, "is_process_elevated", lambda _hwnd: False)
    monkeypatch.setattr(runner_module.wm, "is_self_elevated", lambda: False)
    monkeypatch.setattr(runner_module.vision, "find_image", lambda *_args, **_kwargs: None)
    runner._run_bounties = Mock(side_effect=RuntimeError("capture failed"))
    runner._bounty_settings = Mock(return_value={"enabled": True})
    runner._run_challenges = Mock()
    runner._crafting_wants_in = Mock(return_value=False)
    runner._recover_to_lobby.return_value = True

    runner._run(
        lambda: 123, lambda: [], runner._stop_event,
        coords={}, default_walk_paths={}, webhook={})

    runner._recover_to_lobby.assert_called_once_with(123, runner._stop_event)
    runner._run_challenges.assert_called_once()
    assert any(
        "Auto Bounty pass finished and the Task Queue is empty"
        in call_args.args[0]
        for call_args in runner._log.call_args_list
    )


def test_single_task_exception_skips_task_instead_of_stopping_runner(
        monkeypatch, runner):
    monkeypatch.setattr(runner_module.wm, "is_window", lambda _hwnd: True)
    monkeypatch.setattr(runner_module.wm, "show_window", lambda _hwnd: None)
    monkeypatch.setattr(runner_module.wm, "activate_window", lambda _hwnd: True)
    monkeypatch.setattr(runner_module.wm, "is_process_elevated", lambda _hwnd: False)
    monkeypatch.setattr(runner_module.wm, "is_self_elevated", lambda: False)
    monkeypatch.setattr(runner_module.vision, "find_image", lambda *_args, **_kwargs: None)
    runner._run_bounties = Mock(return_value=False)
    runner._run_challenges = Mock()
    runner._crafting_wants_in = Mock(return_value=False)
    runner._run_task = Mock(side_effect=RuntimeError("task crashed"))
    runner._recover_to_lobby.return_value = True
    queue_reads = iter([[{"mode": "event", "map": "Event", "repeat": 1}], []])

    runner._run(
        lambda: 123, lambda: next(queue_reads), runner._stop_event,
        coords={}, default_walk_paths={}, webhook={})

    runner._recover_to_lobby.assert_called_once_with(123, runner._stop_event)
    assert any(
        "Unexpected error during task 1/1: RuntimeError: task crashed"
        in call_args.args[0]
        for call_args in runner._log.call_args_list
    )


def _prepare_run_environment(monkeypatch, runner):
    monkeypatch.setattr(runner_module.wm, "is_window", lambda _hwnd: True)
    monkeypatch.setattr(runner_module.wm, "show_window", lambda _hwnd: None)
    monkeypatch.setattr(runner_module.wm, "activate_window", lambda _hwnd: True)
    monkeypatch.setattr(runner_module.wm, "is_process_elevated", lambda _hwnd: False)
    monkeypatch.setattr(runner_module.wm, "is_self_elevated", lambda: False)
    monkeypatch.setattr(runner_module.vision, "find_image", lambda *_args, **_kwargs: None)
    runner._bounty_settings = Mock(return_value={"enabled": True})
    runner._recover_to_lobby.return_value = True


@pytest.mark.parametrize("failed_phase", ["bounty", "challenge", "crafting"])
def test_resource_phase_exception_still_reaches_task_queue(
        monkeypatch, runner, failed_phase):
    _prepare_run_environment(monkeypatch, runner)
    calls = []

    def phase(name, result=None):
        def run(*_args, **_kwargs):
            calls.append(name)
            if failed_phase == name:
                raise RuntimeError(f"{name} failed")
            return result
        return run

    runner._run_bounties = Mock(side_effect=phase("bounty", False))
    runner._run_challenges = Mock(side_effect=phase("challenge"))
    runner._run_crafting = Mock(side_effect=phase("crafting"))
    runner._crafting_wants_in = Mock(side_effect=[True, False])
    runner._run_task = Mock(side_effect=phase("task", True))
    queue_reads = iter([[{"mode": "event", "map": "Event", "repeat": 1}], []])

    runner._run(
        lambda: 123, lambda: next(queue_reads), runner._stop_event,
        coords={}, default_walk_paths={}, webhook={})

    assert "task" in calls
    runner._recover_to_lobby.assert_called_once_with(123, runner._stop_event)
    phase_labels = {
        "bounty": "Auto Bounty",
        "challenge": "Challenge",
        "crafting": "Auto Crafting",
    }
    assert any(
        f"Unexpected error during {phase_labels[failed_phase]}"
        in call_args.args[0]
        for call_args in runner._log.call_args_list
    )


def test_recovery_exception_is_logged_without_blocking_later_phases(
        monkeypatch, runner):
    _prepare_run_environment(monkeypatch, runner)
    runner._run_bounties = Mock(side_effect=RuntimeError("bounty failed"))
    runner._recover_to_lobby.side_effect = RuntimeError("recovery failed")
    runner._run_challenges = Mock()
    runner._crafting_wants_in = Mock(return_value=False)
    runner._run_task = Mock(return_value=True)
    queue_reads = iter([[{"mode": "event", "map": "Event", "repeat": 1}], []])

    runner._run(
        lambda: 123, lambda: next(queue_reads), runner._stop_event,
        coords={}, default_walk_paths={}, webhook={})

    runner._run_challenges.assert_called_once()
    runner._run_task.assert_called_once()
    assert any(
        "Unexpected error during Auto Bounty lobby recovery"
        in call_args.args[0]
        for call_args in runner._log.call_args_list
    )


def test_open_deep_link_uses_startfile_when_available(monkeypatch):
    opened = []
    monkeypatch.setattr(runner_module.os, "startfile", opened.append, raising=False)
    monkeypatch.setattr(
        runner_module.webbrowser,
        "open",
        lambda _url: pytest.fail("browser fallback should not run on Windows"),
    )

    runner_module._open_deep_link("roblox://test")

    assert opened == ["roblox://test"]


def test_open_deep_link_uses_browser_fallback_without_startfile(monkeypatch):
    opened = []
    monkeypatch.delattr(runner_module.os, "startfile", raising=False)
    monkeypatch.setattr(
        runner_module.webbrowser,
        "open",
        lambda url: opened.append(url) or True,
    )

    runner_module._open_deep_link("roblox://test")

    assert opened == ["roblox://test"]


def test_failed_rejoin_stays_pending_and_does_not_launch_again(monkeypatch):
    class _Clock:
        def __init__(self):
            self.now = 0.0

        def time(self):
            return self.now

        def sleep(self, seconds):
            self.now += seconds

    runner = MacroRunner(Mock(), Mock(), Mock())
    clock = _Clock()
    stop_event = threading.Event()
    screenshot = Mock(return_value="rejoin_timeout.png")
    monkeypatch.setattr(runner_module, "REJOIN_TIMEOUT", 5.0)
    monkeypatch.setattr(runner_module, "REJOIN_POLL_INTERVAL", 1.0)

    monkeypatch.setattr(runner_module.time, "time", clock.time)
    monkeypatch.setattr(runner_module.time, "sleep", clock.sleep)
    monkeypatch.setattr(runner_module.wm, "list_roblox_windows", lambda: [])
    monkeypatch.setattr(runner_module.wm, "is_window", lambda _hwnd: True)
    events = []
    monkeypatch.setattr(runner_module.wm, "close_roblox_process",
                        lambda hwnd: events.append(("close", hwnd)))
    def find_lobby_after_existing_launch(*_args, **_kwargs):
        # 7.0: the rejoin closes the stuck client first (1s settle sleep),
        # so the first pass's 5s timeout budget ends at t=6.0 -- the lobby
        # must only appear AFTER that, on the second (pending) pass.
        if clock.now >= 7.0:
            return ({"score": 1.0}, "nav_play")
        return (None, None)

    monkeypatch.setattr(runner_module.vision, "find_image_any", find_lobby_after_existing_launch)
    monkeypatch.setattr(
        runner_module.os,
        "startfile",
        lambda url: events.append(("launch", url)),
        raising=False,
    )
    runner._hwnd_getter = lambda: 123
    runner._save_debug_screenshot_unconditional = screenshot

    assert runner._attempt_rejoin(123, stop_event) is False
    assert not stop_event.is_set()
    # The stuck client was closed BEFORE the fresh one was launched -- the
    # deep link must never be asked to reconnect a wedged session.
    assert events == [("close", 123), ("launch", runner_module.REJOIN_DEEPLINK)]
    assert runner.is_rejoin_pending()
    screenshot.assert_called_once_with(123, "rejoin_timeout")
    assert any(
        "no second deep link will be opened" in call_args.args[0]
        for call_args in runner._log.call_args_list
    )

    # A later recovery pass waits on the same launcher (the fresh client is
    # already booting -- no second close, no second launch). Once it exposes
    # the lobby, the run can continue and the pending guard clears.
    assert runner._attempt_rejoin(123, stop_event) is True
    assert events == [("close", 123), ("launch", runner_module.REJOIN_DEEPLINK)]
    assert not runner.is_rejoin_pending()
    assert runner._current_hwnd == 123


def test_rejoin_skips_close_when_other_windows_block_launch(monkeypatch):
    # The stuck client must NOT be killed when the multi-instance guard
    # refuses to launch -- that would take out the user's only remaining
    # client (the alt) with nothing to relaunch it.
    runner = MacroRunner(Mock(), Mock(), Mock())
    stop_event = threading.Event()
    launches = []
    closed_clients = []
    monkeypatch.setattr(runner_module.wm, "list_roblox_windows",
                        lambda: [{"hwnd": 999, "pid": 1, "title": "alt"}])
    monkeypatch.setattr(runner_module.wm, "is_window", lambda _hwnd: True)
    monkeypatch.setattr(runner_module.wm, "close_roblox_process",
                        lambda hwnd: closed_clients.append(hwnd))
    monkeypatch.setattr(
        runner_module.os,
        "startfile",
        lambda url: launches.append(url),
        raising=False,
    )
    runner._hwnd_getter = lambda: 123

    assert runner._attempt_rejoin(123, stop_event) is False
    assert closed_clients == []
    assert launches == []
    assert not runner.is_rejoin_pending()


def test_rejoin_lock_blocks_concurrent_launcher(monkeypatch):
    runner = MacroRunner(Mock(), Mock(), Mock())
    stop_event = threading.Event()
    launches = []
    monkeypatch.setattr(
        runner_module.os,
        "startfile",
        lambda url: launches.append(url),
        raising=False,
    )

    assert runner._rejoin_lock.acquire(blocking=False)
    try:
        assert runner._attempt_rejoin(123, stop_event) is False
    finally:
        runner._rejoin_lock.release()

    assert not stop_event.is_set()
    assert launches == []
    assert any(
        "already in progress" in call_args.args[0]
        for call_args in runner._log.call_args_list
    )


def test_watchdog_rejoin_claim_is_single_use():
    runner = MacroRunner(Mock(), Mock(), Mock())

    assert runner.claim_rejoin_launch() is True
    assert runner.is_rejoin_pending()
    assert runner.claim_rejoin_launch() is False

    runner.cancel_rejoin_launch()
    assert not runner.is_rejoin_pending()
    assert runner.claim_rejoin_launch() is True
    runner.cancel_rejoin_launch()


def test_stale_rejoin_claim_expires_so_the_watchdog_can_relaunch(monkeypatch):
    """A handoff that never delivered must not gate reopens forever.

    ``_rejoin_pending`` was only ever cleared on a rejoin that REACHED the
    lobby, so a link that could never succeed (fired while the connection
    was down, launcher died) left is_rejoin_pending() true for the rest of
    the session -- and main.py's dock watchdog gates its auto-reopen on
    exactly that, so an unattended run sat on a closed Roblox forever.
    """
    runner = MacroRunner(Mock(), Mock(), Mock())
    now = [1000.0]
    monkeypatch.setattr(runner_module.time, "time", lambda: now[0])

    assert runner.claim_rejoin_launch() is True
    now[0] += runner_module.REJOIN_PENDING_TTL - 1
    assert runner.is_rejoin_pending(), "a still-fresh handoff is waited on, not raced"
    assert runner.claim_rejoin_launch() is False

    now[0] += 2  # now past the TTL
    assert not runner.is_rejoin_pending()
    assert runner.claim_rejoin_launch() is True, "the watchdog gets to try again"


def test_rejoin_relaunches_after_the_pending_handoff_goes_stale(monkeypatch):
    """The runner's own rejoin path heals the same way: past the TTL it
    closes the wedged client and opens a FRESH link instead of polling a
    launcher that is never going to produce a lobby."""
    runner = MacroRunner(Mock(), Mock(), Mock())
    stop_event = threading.Event()
    now = [1000.0]
    monkeypatch.setattr(runner_module, "REJOIN_TIMEOUT", 0.0)  # don't poll, just decide
    monkeypatch.setattr(runner_module.time, "time", lambda: now[0])
    monkeypatch.setattr(runner_module.time, "sleep", lambda _s: None)
    monkeypatch.setattr(runner_module.wm, "list_roblox_windows", lambda: [])
    monkeypatch.setattr(runner_module.wm, "is_window", lambda _hwnd: True)
    monkeypatch.setattr(runner_module.vision, "find_image_any", lambda *_a, **_k: (None, None))
    launches = []
    monkeypatch.setattr(runner_module.wm, "close_roblox_process", lambda hwnd: launches.append(("close", hwnd)))
    monkeypatch.setattr(runner_module.os, "startfile",
                        lambda url: launches.append(("launch", url)), raising=False)
    runner._hwnd_getter = lambda: 123
    runner._save_debug_screenshot_unconditional = Mock(return_value=None)

    assert runner._attempt_rejoin(123, stop_event) is False
    assert launches == [("close", 123), ("launch", runner_module.REJOIN_DEEPLINK)]

    # Still within the TTL: keep waiting on the existing launcher.
    now[0] += runner_module.REJOIN_PENDING_TTL - 1
    assert runner._attempt_rejoin(123, stop_event) is False
    assert len(launches) == 2, "no competing launch while the handoff is fresh"

    # Past it: the handoff is dead, so a fresh client is launched.
    now[0] += 2
    assert runner._attempt_rejoin(123, stop_event) is False
    assert launches == [("close", 123), ("launch", runner_module.REJOIN_DEEPLINK),
                        ("close", 123), ("launch", runner_module.REJOIN_DEEPLINK)]
    assert any("treating it as dead" in logged.args[0]
               for logged in runner._log.call_args_list)


def _lobby_check_runner(monkeypatch, blockers, play_after_clear=True):
    """A real _ensure_lobby with Play missing on the first look.

    ``blockers`` maps an image name to what find_image returns for it, so a
    test can put the AFK Chamber or a portal picker on screen.
    """
    runner = MacroRunner(mouse=Mock(), keyboard=Mock(), log=Mock())
    runner._attempt_rejoin = Mock(return_value=False)
    waits = []
    clicked = []

    def wait_for_play(_hwnd, _names, timeout=None, stop_event=None, **_kwargs):
        waits.append(timeout)
        if len(waits) > 1 and play_after_clear:
            return ({"score": 1.0}, "nav_play")
        return (None, None)

    monkeypatch.setattr(runner_module.vision, "wait_for_image_any", wait_for_play)
    monkeypatch.setattr(runner_module.vision, "find_image",
                        lambda _hwnd, name, region=None, **_kwargs: blockers.get(name))
    monkeypatch.setattr(runner_module.vision, "click_match",
                        lambda _mouse, _hwnd, match: clicked.append(match))
    monkeypatch.setattr(runner_module.wm, "get_window_rect_screen", lambda _hwnd: (10, 20, 1152, 756))
    return runner, waits, clicked


def test_lobby_check_leaves_the_afk_chamber_instead_of_killing_roblox(monkeypatch):
    """The AFK Chamber hides Play exactly like a disconnect does, but it has
    an exit -- taking it keeps the session, a rejoin throws it away."""
    runner, waits, _ = _lobby_check_runner(
        monkeypatch, {"afk_chamber": {"cx": 576, "cy": 44, "score": 0.99}})

    assert runner._ensure_lobby(123, threading.Event()) is True
    exit_x, exit_y = runner_module.AFK_CHAMBER_EXIT_CLICK
    runner._mouse.click.assert_called_once_with(10 + exit_x, 20 + exit_y)
    assert waits == [runner_module.LOBBY_CHECK_TIMEOUT, runner_module.LOBBY_BLOCKER_CLEAR_TIMEOUT]
    runner._attempt_rejoin.assert_not_called()


def test_lobby_check_closes_a_leftover_portal_picker_instead_of_killing_roblox(monkeypatch):
    picker_x = {"cx": 906, "cy": 180, "score": 0.97}
    runner, _, clicked = _lobby_check_runner(monkeypatch, {"portal_picker_close": picker_x})

    assert runner._ensure_lobby(123, threading.Event()) is True
    assert clicked == [picker_x]
    runner._attempt_rejoin.assert_not_called()


def test_lobby_check_still_rejoins_when_nothing_is_in_the_way(monkeypatch):
    runner, waits, clicked = _lobby_check_runner(monkeypatch, {})

    runner._ensure_lobby(123, threading.Event())
    assert waits == [runner_module.LOBBY_CHECK_TIMEOUT], "no second look without a cleared blocker"
    assert clicked == []
    runner._attempt_rejoin.assert_called_once()


def test_lobby_check_rejoins_when_clearing_the_blocker_did_not_help(monkeypatch):
    runner, waits, _ = _lobby_check_runner(
        monkeypatch, {"portal_picker_close": {"cx": 906, "cy": 180, "score": 0.97}},
        play_after_clear=False)

    runner._ensure_lobby(123, threading.Event())
    assert len(waits) == 2
    runner._attempt_rejoin.assert_called_once()


def test_seeing_the_lobby_settles_a_pending_rejoin(monkeypatch):
    """The dock watchdog's reopen is never polled to completion by a runner
    rejoin, so without this the claim stayed up until REJOIN_PENDING_TTL and
    a real disconnect in that window could not relaunch."""
    runner = MacroRunner(mouse=Mock(), keyboard=Mock(), log=Mock())
    monkeypatch.setattr(runner_module.vision, "wait_for_image_any",
                        lambda *_a, **_k: ({"score": 1.0}, "nav_play"))
    assert runner.claim_rejoin_launch() is True

    assert runner._ensure_lobby(123, threading.Event()) is True
    assert not runner.is_rejoin_pending()


def test_live_hwnd_adopts_the_window_the_watchdog_redocked(monkeypatch):
    """A watchdog reopen docks Roblox under a new hwnd without the runner's
    own rejoin ever running -- the run has to follow it there instead of
    acting on the dead handle."""
    runner = MacroRunner(mouse=Mock(), keyboard=Mock(), log=Mock())
    alive = {222}
    monkeypatch.setattr(runner_module.wm, "is_window", lambda hwnd: hwnd in alive)
    runner._current_hwnd = 111  # the closed client
    runner._hwnd_getter = lambda: 222

    assert runner._live_hwnd(111) == 222
    assert runner._current_hwnd == 222


def test_live_hwnd_keeps_a_tracked_window_that_is_still_alive(monkeypatch):
    runner = MacroRunner(mouse=Mock(), keyboard=Mock(), log=Mock())
    monkeypatch.setattr(runner_module.wm, "is_window", lambda _hwnd: True)
    runner._current_hwnd = 111
    runner._hwnd_getter = lambda: 222

    assert runner._live_hwnd(999) == 111


def test_live_hwnd_falls_back_to_the_callers_hwnd_when_nothing_is_docked(monkeypatch):
    runner = MacroRunner(mouse=Mock(), keyboard=Mock(), log=Mock())
    monkeypatch.setattr(runner_module.wm, "is_window", lambda _hwnd: False)
    runner._current_hwnd = 111
    runner._hwnd_getter = lambda: None

    assert runner._live_hwnd(999) == 999

def test_open_deep_link_reports_rejected_link(monkeypatch):
    monkeypatch.delattr(runner_module.os, "startfile", raising=False)
    monkeypatch.setattr(runner_module.webbrowser, "open", lambda _url: False)

    with pytest.raises(OSError, match="No application accepted"):
        runner_module._open_deep_link("roblox://test")

def test_stop_during_phase_failure_does_not_recover_or_continue(
        monkeypatch, runner):
    _prepare_run_environment(monkeypatch, runner)

    def fail_after_stop(*_args, **_kwargs):
        runner._stop_event.set()
        raise RuntimeError("stopped failure")

    runner._run_bounties = Mock(side_effect=fail_after_stop)
    runner._run_challenges = Mock()
    runner._crafting_wants_in = Mock(return_value=False)

    runner._run(
        lambda: 123, lambda: [], runner._stop_event,
        coords={}, default_walk_paths={}, webhook={})

    runner._recover_to_lobby.assert_not_called()
    runner._run_challenges.assert_not_called()


def test_crashed_task_does_not_block_later_tasks(monkeypatch, runner):
    _prepare_run_environment(monkeypatch, runner)
    runner._run_bounties = Mock(return_value=False)
    runner._run_challenges = Mock()
    runner._crafting_wants_in = Mock(return_value=False)
    completed_maps = []

    def run_task(_hwnd, _stop, task, *_args, **_kwargs):
        if task["map"] == "First":
            raise RuntimeError("first task failed")
        completed_maps.append(task["map"])
        return True

    runner._run_task = Mock(side_effect=run_task)
    queue_reads = iter([[
        {"mode": "story", "map": "First", "repeat": 1},
        {"mode": "story", "map": "Second", "repeat": 1},
    ], []])

    runner._run(
        lambda: 123, lambda: next(queue_reads), runner._stop_event,
        coords={}, default_walk_paths={}, webhook={})

    assert completed_maps == ["Second"]
    runner._recover_to_lobby.assert_called_once_with(123, runner._stop_event)


def test_crafting_readiness_exception_does_not_block_task_queue(
        monkeypatch, runner):
    _prepare_run_environment(monkeypatch, runner)
    runner._run_bounties = Mock(return_value=False)
    runner._run_challenges = Mock()
    runner._crafting_wants_in = Mock(
        side_effect=[ValueError("bad crafting counter"), False])
    runner._run_task = Mock(return_value=True)
    queue_reads = iter([[{"mode": "event", "map": "Event", "repeat": 1}], []])

    runner._run(
        lambda: 123, lambda: next(queue_reads), runner._stop_event,
        coords={}, default_walk_paths={}, webhook={})

    runner._run_task.assert_called_once()
    runner._recover_to_lobby.assert_called_once_with(123, runner._stop_event)
    assert any(
        "Unexpected error during Auto Crafting"
        in call_args.args[0]
        for call_args in runner._log.call_args_list
    )

