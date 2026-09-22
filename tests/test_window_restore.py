"""The macro window minimizing on its own, and the run dying with it.

Roblox is reparented as a child of the macro's own window (core/dock.py), so
a minimized panel is not cosmetic -- the game window goes with it, captures
read nothing and clicks land nowhere. Windows minimizes a whole session's
windows when a Remote Desktop client disconnects, which a brief network drop
counts as, and nothing else in the app notices: the dock is still intact, so
the watchdog's dock branch never runs again.

These pin the heal (Api.heal_minimized_window) and, just as importantly, the
cases it must keep its hands off.
"""
import main
from main import Api


class _Docker:
    def __init__(self, docked=True):
        self.docked = docked


class _Runner:
    def __init__(self, running=True):
        self._running = running

    def is_running(self):
        return self._running


def _api(monkeypatch, *, minimized=True, docked=True, running=True,
         wanted=False, restores=True):
    api = object.__new__(Api)
    api.docker = _Docker(docked)
    api.runner = _Runner(running)
    api.gui_hwnd = 4242
    api._window = None
    api._gui_minimize_wanted = wanted
    api._gui_restore_logged_at = 0.0
    api.logs = []
    api.push_log = lambda message: api.logs.append(message)

    state = {"minimized": minimized, "restore_calls": 0, "activated": 0}
    api.state = state
    monkeypatch.setattr(main.wm, "is_window", lambda _hwnd: True)
    monkeypatch.setattr(main.wm, "is_minimized", lambda _hwnd: state["minimized"])
    monkeypatch.setattr(main.wm, "activate_window",
                        lambda _hwnd: state.__setitem__("activated", state["activated"] + 1) or True)

    def restore(_hwnd):
        state["restore_calls"] += 1
        if restores:
            state["minimized"] = False
        return not state["minimized"]

    monkeypatch.setattr(main.wm, "restore_window", restore)
    monkeypatch.setattr(main.time, "sleep", lambda _s: None)
    monkeypatch.setattr(main.sys, "platform", "win32")
    return api


def test_a_minimize_during_a_run_is_undone(monkeypatch):
    api = _api(monkeypatch)
    assert api.heal_minimized_window() is True
    assert api.state["restore_calls"] == 1
    assert any("Remote Desktop" in line for line in api.logs)


def test_the_restore_does_not_steal_focus(monkeypatch):
    """It fires unattended, every couple of seconds. Pulling the foreground
    away from whatever else the user has open would be its own bug -- that is
    what the by-hand hotkey (Api.restore_window) is for."""
    api = _api(monkeypatch)
    api.heal_minimized_window()
    assert api.state["activated"] == 0


def test_an_idle_window_is_left_minimized(monkeypatch):
    """No run going: minimizing the panel is an ordinary thing to want."""
    api = _api(monkeypatch, running=False)
    assert api.heal_minimized_window() is False
    assert api.state["restore_calls"] == 0


def test_the_titlebar_minimize_button_is_left_alone(monkeypatch):
    """Our own Minimize has to keep working mid-run -- see minimize_window."""
    api = _api(monkeypatch, wanted=True)
    assert api.heal_minimized_window() is False
    assert api.state["restore_calls"] == 0


def test_a_hand_minimize_flag_clears_once_the_window_is_back(monkeypatch):
    """Otherwise one press of the titlebar button would disarm the heal for
    the rest of the session."""
    api = _api(monkeypatch, minimized=False, wanted=True)
    api.heal_minimized_window()
    assert api._gui_minimize_wanted is False


def test_nothing_happens_while_nothing_is_docked(monkeypatch):
    """No docked game means no child window to lose -- and the dock branch of
    the watchdog is still in charge of getting there."""
    api = _api(monkeypatch, docked=False)
    assert api.heal_minimized_window() is False
    assert api.state["restore_calls"] == 0


def test_a_restore_that_does_not_take_says_so(monkeypatch):
    api = _api(monkeypatch, restores=False)
    assert api.heal_minimized_window() is False
    assert any("Restore Window hotkey" in line for line in api.logs)


def test_repeated_failures_do_not_flood_the_log(monkeypatch):
    """The restore is retried every tick; only the LOG is throttled."""
    api = _api(monkeypatch, restores=False)
    for _ in range(5):
        api.heal_minimized_window()
    assert api.state["restore_calls"] == 5
    assert len([l for l in api.logs if "Remote Desktop" in l]) == 1


def test_the_restore_hotkey_is_registered_with_a_free_key():
    """F1-F7 are taken by the other actions; this must not collide with one."""
    assert main.HOTKEY_DEFAULTS["restore_window"] == "f8"
    others = [k for a, k in main.HOTKEY_DEFAULTS.items() if a != "restore_window" and k]
    assert "f8" not in others
