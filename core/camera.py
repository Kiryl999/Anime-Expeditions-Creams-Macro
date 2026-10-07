"""Puts the Roblox camera into the standard macro viewpoint: tilt it straight
down by way of first person -- hold I to zoom all the way in, move the mouse
down, hold O to zoom back out along that angle -- then hold O once more so
the zoom-out reaches max. How long each of those takes is a CameraTiming.

Shared by Settings > Debug > "Camera Setup" (main.Api.debug_camera_setup,
on demand) and the macro run's Pre Start step (core.runner, automatically
before every match) -- both need the exact same sequence, so it lives here
once instead of twice.
"""
import time
from dataclasses import dataclass, fields

from . import window as wm

# The look-down: LOOK_DOWN_STEPS relative moves of LOOK_DOWN_PX, spread over
# CameraTiming.look_down_ms. 800px in all turns the camera far past its pitch
# floor at any usual sensitivity -- past the floor the extra movement is a
# no-op, so the overshoot is free -- while each frame only carries the cursor
# a few dozen pixels before Roblox pulls it back to the middle.
LOOK_DOWN_STEPS = 25
LOOK_DOWN_PX = 32

# Bounds for the timings a user can type in. O any shorter than its floor
# can be missed outright, and a game left in first person keeps the cursor
# locked to the middle of the screen -- every later click of the run would
# land there.
TIMING_MAX_MS = 10000
TIMING_MIN_MS = {"zoom_out_ms": 100}


@dataclass(frozen=True)
class CameraTiming:
    """How long each step of the camera setup takes, in ms -- Settings >
    Debug > Camera Setup Timing, saved as camera_<field> in settings.json.

    The defaults are the sequence as tuned on a normal desktop. Roblox zooms
    a step per drawn frame rather than per second, so where it draws few
    frames (Remote Desktop) the same hold zooms less far and has to be held
    longer. I held past first person and O held past the full zoom-out
    change nothing, so for those two, longer only takes more time.
    """
    zoom_in_ms: float = 500         # I: all the way in, into first person
    look_down_ms: float = 500       # the mouse moving down in first person
    zoom_out_ms: float = 500        # O: back out of first person, looking down
    full_zoom_out_ms: float = 2000  # O again, the standard setup only: all the way out

    @classmethod
    def from_settings(cls, data: dict) -> "CameraTiming":
        """The timings saved in settings, each held to its bounds. A missing
        or unreadable one keeps its default."""
        values = {}
        for f in fields(cls):
            try:
                value = float(data.get(f"camera_{f.name}", f.default))
            except (TypeError, ValueError):
                value = f.default
            values[f.name] = min(TIMING_MAX_MS, max(TIMING_MIN_MS.get(f.name, 0), value))
        return cls(**values)

    def as_settings(self) -> dict:
        return {f"camera_{f.name}": getattr(self, f.name) for f in fields(self)}


def _hold_key(keyboard, vk: int, seconds: float) -> None:
    # Released in a finally: a key left physically down would keep the
    # camera zooming or turning for the rest of the run.
    keyboard.key_down(vk)
    try:
        time.sleep(max(0.0, seconds))
    finally:
        keyboard.key_up(vk)


def tilt_camera_top_down(mouse, keyboard, hwnd, timing: CameraTiming = None) -> None:
    """Point the Roblox camera straight down. Leaves it zoomed out only as
    far as timing.zoom_out_ms of O takes it from first person.

    Caller owns the focus dance. No mouse button is held at any point: in
    first person Roblox locks the cursor to the middle of the screen and
    turns the camera with plain mouse movement, so looking down needs no
    right-click drag -- the drag whose button came up outside the game
    over Remote Desktop. The pitch stops at its floor, and zooming back out
    keeps it.
    """
    timing = timing or CameraTiming()
    left, top, right, bottom = wm.get_window_rect_screen(hwnd)
    cx, cy = (left + right) // 2, (top + bottom) // 2
    mouse.move_to(cx, cy)
    time.sleep(0.15)
    mouse.nudge()  # a real move event, so the game registers the cursor over it
    time.sleep(0.05)

    _hold_key(keyboard, ord("I"), timing.zoom_in_ms / 1000)

    # Kept inside the game while it moves. Roblox's recenter is only once
    # per frame, so where frames are slow (Remote Desktop) several moves
    # land between two recenters. The camera itself reads the raw deltas,
    # which the clip doesn't touch.
    clip = (left, top, right, bottom)
    try:
        time.sleep(0.1)  # first person locks the cursor a frame or two late
        for _ in range(LOOK_DOWN_STEPS):
            # Re-set every step: a focus change, or the game itself, can
            # clear a clip at any time.
            wm.clip_cursor(clip)
            mouse.nudge(0, LOOK_DOWN_PX)
            time.sleep(timing.look_down_ms / 1000 / LOOK_DOWN_STEPS)
        time.sleep(0.1)
    finally:
        # Both no matter what happened above. The clip goes first, so a
        # failing O can't leave the cursor caged in the game window for the
        # rest of the session. And O always runs: a game left in first
        # person keeps the cursor locked to the middle of the screen, and
        # every later click of the run would land there.
        wm.release_cursor_clip()
        _hold_key(keyboard, ord("O"), timing.zoom_out_ms / 1000)
    time.sleep(0.15)


def run_camera_setup(mouse, keyboard, hwnd, hold_ms: float = None,
                     timing: CameraTiming = None) -> None:
    """Tilt top-down, then hold O for the standard maximum zoom-out: for
    timing.full_zoom_out_ms, or for hold_ms where Settings > Debug >
    "Camera Setup 2" tries another time."""
    timing = timing or CameraTiming()
    tilt_camera_top_down(mouse, keyboard, hwnd, timing)
    _hold_key(keyboard, ord("O"), (timing.full_zoom_out_ms if hold_ms is None else hold_ms) / 1000)


def run_camera_rotate_hold(mouse, keyboard, hwnd, hold_ms: float = 2500, o_tap_ms: float = 0,
                           timing: CameraTiming = None) -> None:
    """The same top-down tilt as run_camera_setup, but followed by holding
    the LEFT ARROW key for hold_ms (a camera rotate) instead of the O
    zoom-hold -- then, if o_tap_ms > 0, a short O press for that long (a
    small zoom step, not the full zoom-out). This is EXPEDITION's Pre Start
    camera setup (730ms rotate + 100ms O -- the standard sequence doesn't
    frame Expedition maps right, see core.runner's _run_prestart); Settings
    > Debug > "Camera Setup 3" runs the rotate part on demand with any hold
    time for tuning. Same held-input-released-in-finally safety as
    run_camera_setup above."""
    from . import keys

    tilt_camera_top_down(mouse, keyboard, hwnd, timing)
    _hold_key(keyboard, keys.VK_LEFT, hold_ms / 1000)

    if o_tap_ms > 0:
        time.sleep(0.1)
        _hold_key(keyboard, ord("O"), o_tap_ms / 1000)
