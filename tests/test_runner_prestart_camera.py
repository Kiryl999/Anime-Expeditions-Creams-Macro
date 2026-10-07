import threading
from unittest.mock import MagicMock

import pytest

from core import runner as runner_module
from core.runner import MacroRunner


def _runner():
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    # Isolate _run_prestart to just the camera-setup step under test --
    # Team Loadout/prestart blocks are exercised by their own test files.
    runner._apply_team_loadout = lambda *_a, **_kw: True
    runner._run_prestart_blocks = lambda *_a, **_kw: None
    return runner


def test_camera_settle_runs_before_the_drag(monkeypatch):
    calls = []
    monkeypatch.setattr(runner_module.time, "sleep", lambda _s: None)
    monkeypatch.setattr(
        runner_module.camera, "run_camera_setup",
        lambda *_a, **_kw: calls.append("camera"))

    runner = _runner()
    real_sleep = runner._interruptible_sleep

    def spy_sleep(seconds, stop_event=None):
        calls.append(("settle", seconds))
        return real_sleep(seconds, stop_event)

    runner._interruptible_sleep = spy_sleep

    assert runner._run_prestart(123, threading.Event(), {"mode": "story"}, {}) is True
    assert calls == [("settle", runner_module.CAMERA_SETUP_SETTLE), "camera"]


def test_stop_during_camera_settle_skips_the_drag_immediately(monkeypatch):
    """The settle must stay interruptible -- F2/Stop landing during it must
    not block for the full settle duration nor still run the camera drag."""
    calls = []
    monkeypatch.setattr(
        runner_module.camera, "run_camera_setup",
        lambda *_a, **_kw: calls.append("camera"))

    runner = _runner()
    stop_event = threading.Event()
    stop_event.set()

    assert runner._run_prestart(123, stop_event, {"mode": "story"}, {}) is False
    assert calls == [], "camera setup must not run once Stop has already landed"


def _template_with(monkeypatch, blocks):
    from core import templates as tpl
    monkeypatch.setattr(tpl, "load_template", lambda name: {"name": name, "blocks": blocks})


def _spy_settles(runner, calls):
    def spy_sleep(seconds, stop_event=None):
        calls.append(("settle", seconds))
    runner._interruptible_sleep = spy_sleep


def test_camera_setup_switched_off_in_the_template_is_skipped(monkeypatch):
    """Macro Manager > Pre Start > Camera Setup: Off. No drag at all, and the
    map still gets the same settle a repeat gets before the first block."""
    calls = []
    monkeypatch.setattr(
        runner_module.camera, "run_camera_setup",
        lambda *_a, **_kw: calls.append("camera"))
    _template_with(monkeypatch, {"camera": False, "prestart": [], "battle": []})

    runner = _runner()
    _spy_settles(runner, calls)

    assert runner._run_prestart(123, threading.Event(), {"mode": "story", "macro": "auto"}, {}) is True
    assert calls == [("settle", runner_module.REPEAT_ENTRY_SETTLE)]


def test_camera_setup_off_skips_the_expedition_sequence_too(monkeypatch):
    calls = []
    monkeypatch.setattr(
        runner_module.camera, "run_camera_rotate_hold",
        lambda *_a, **_kw: calls.append("camera"))
    _template_with(monkeypatch, {"camera": False, "prestart": [], "battle": []})

    runner = _runner()
    _spy_settles(runner, calls)

    assert runner._run_prestart(123, threading.Event(), {"mode": "expedition", "macro": "auto"}, {}) is True
    assert "camera" not in calls


def test_templates_without_the_switch_keep_their_camera_setup(monkeypatch):
    """Every template saved before the switch existed has no "camera" key --
    those must keep running the camera setup exactly as before."""
    calls = []
    monkeypatch.setattr(
        runner_module.camera, "run_camera_setup",
        lambda *_a, **_kw: calls.append("camera"))
    _template_with(monkeypatch, {"prestart": [], "battle": []})

    runner = _runner()
    _spy_settles(runner, calls)

    assert runner._run_prestart(123, threading.Event(), {"mode": "story", "macro": "old"}, {}) is True
    assert calls == [("settle", runner_module.CAMERA_SETUP_SETTLE), "camera"]


def test_only_an_explicit_false_switches_the_camera_off():
    runner = _runner()
    from core import templates as tpl
    cases = {
        "missing key": {"prestart": []},
        "on": {"camera": True},
        "legacy list template": [],
        "garbage": {"camera": "off"},
    }
    original = tpl.load_template
    try:
        for label, blocks in cases.items():
            tpl.load_template = lambda name, b=blocks: {"name": name, "blocks": b}
            assert runner._camera_setup_enabled({"macro": "x"}) is True, label
        tpl.load_template = lambda name: {"name": name, "blocks": {"camera": False}}
        assert runner._camera_setup_enabled({"macro": "x"}) is False
        assert runner._camera_setup_enabled({}) is True, "a task with no macro keeps the camera"
    finally:
        tpl.load_template = original


# Settings > Debug > Camera Setup Timing: a slow setup (Remote Desktop) needs
# longer holds, and whatever was set has to reach every camera the run uses.

_SLOW = runner_module.camera.CameraTiming(zoom_in_ms=1500, full_zoom_out_ms=3000)


def test_a_new_runner_uses_the_default_timing():
    assert _runner()._camera_timing == runner_module.camera.CameraTiming()


@pytest.mark.parametrize("mode, sequence", [("story", "run_camera_setup"),
                                            ("expedition", "run_camera_rotate_hold")])
def test_the_set_timing_reaches_the_pre_start_camera(monkeypatch, mode, sequence):
    used = []
    monkeypatch.setattr(runner_module.time, "sleep", lambda _s: None)
    monkeypatch.setattr(runner_module.camera, sequence, lambda *_a, **kw: used.append(kw.get("timing")))

    runner = _runner()
    runner._interruptible_sleep = lambda *_a, **_kw: None
    runner._camera_timing = _SLOW

    assert runner._run_prestart(123, threading.Event(), {"mode": mode}, {}) is True
    assert used == [_SLOW]
