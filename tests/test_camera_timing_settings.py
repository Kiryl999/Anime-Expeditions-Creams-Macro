"""Settings > Debug > Camera Setup Timing, from settings.json to the camera.

Roblox zooms a step per frame, so a setup at low FPS (Remote Desktop) needs
longer holds than the defaults. The four times are settings, and every camera
setup the macro runs has to get them: the run's Pre Start and Gold Shop
(through runner.start) and the Camera Setup buttons under Settings > Debug.
"""
from unittest.mock import MagicMock

import main
from core.camera import CameraTiming

_SAVED = {"camera_zoom_in_ms": 1500, "camera_look_down_ms": 800,
          "camera_zoom_out_ms": 700, "camera_full_zoom_out_ms": 3000}
_SLOW = CameraTiming(zoom_in_ms=1500, look_down_ms=800, zoom_out_ms=700, full_zoom_out_ms=3000)


def _api(monkeypatch, saved):
    monkeypatch.setattr(main.cfg, "load", lambda: dict(saved))
    return object.__new__(main.Api)


def test_the_settings_screen_shows_the_defaults_until_something_is_saved(monkeypatch):
    settings = _api(monkeypatch, {}).get_settings()

    assert {k: settings[k] for k in _SAVED} == CameraTiming().as_settings()


def test_the_settings_screen_shows_what_was_saved(monkeypatch):
    settings = _api(monkeypatch, _SAVED).get_settings()

    assert {k: settings[k] for k in _SAVED} == _SAVED


def test_a_run_starts_with_the_saved_timing(monkeypatch):
    api = _api(monkeypatch, _SAVED)
    api.run_preflight_check = lambda: {"has_blocker": False}
    api.reset_run_status = lambda *_a: None
    api.get_default_walk_paths = lambda: {}
    api.get_webhook_settings = lambda: {}
    api.runner = MagicMock()

    api.start_macro()

    assert api.runner.start.call_args.kwargs["camera_timing"] == _SLOW


class _NowThread:
    """threading.Thread that runs its target on start()."""

    def __init__(self, target, daemon=None):
        self._target = target

    def start(self):
        self._target()


def test_the_camera_setup_buttons_use_the_saved_timing(monkeypatch):
    api = _api(monkeypatch, _SAVED)
    api.game_hwnd = 123
    api.mouse = api.keyboard = None
    api.push_log = lambda _message: None
    used = []
    monkeypatch.setattr(main.wm, "is_window", lambda _hwnd: True)
    monkeypatch.setattr(main.wm, "show_window", lambda _hwnd: None)
    monkeypatch.setattr(main.wm, "activate_window", lambda _hwnd: True)
    monkeypatch.setattr(main.threading, "Thread", _NowThread)
    for sequence in ("run_camera_setup", "run_camera_rotate_hold"):
        monkeypatch.setattr(f"core.camera.{sequence}",
                            lambda *_a, sequence=sequence, **kw: used.append((sequence, kw.get("timing"))))

    assert api.debug_camera_setup() == {"ok": True}
    assert api.debug_camera_setup_2(4000) == {"ok": True}
    assert api.debug_camera_setup_3(730) == {"ok": True}

    assert used == [("run_camera_setup", _SLOW), ("run_camera_setup", _SLOW),
                    ("run_camera_rotate_hold", _SLOW)]
