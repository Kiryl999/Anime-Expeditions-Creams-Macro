"""Puts the Roblox camera into the standard macro viewpoint: tilt it straight
down by way of first person -- hold I to zoom all the way in, move the mouse
down, hold O to zoom back out along that angle -- then hold O for 2s more so
the zoom-out reaches max.

Shared by Settings > Debug > "Camera Setup" (main.Api.debug_camera_setup,
on demand) and the macro run's Pre Start step (core.runner, automatically
before every match) -- both need the exact same sequence, so it lives here
once instead of twice.
"""
import time

from . import window as wm

# The tilt's three steps, half a second each. I held past the moment first
# person is reached changes nothing, so ZOOM_IN_HOLD only has to be long
# enough to get there; ZOOM_OUT_HOLD is how far out the tilt on its own
# leaves the camera.
ZOOM_IN_HOLD = 0.5
LOOK_DOWN_TIME = 0.5
ZOOM_OUT_HOLD = 0.5
# The look-down: LOOK_DOWN_STEPS relative moves of LOOK_DOWN_PX, spread over
# LOOK_DOWN_TIME. 800px in all turns the camera far past its pitch floor at
# any usual sensitivity -- past the floor the extra movement is a no-op, so
# the overshoot is free -- while each frame only carries the cursor a few
# dozen pixels before Roblox pulls it back to the middle.
LOOK_DOWN_STEPS = 25
LOOK_DOWN_PX = 32


def _hold_key(keyboard, vk: int, seconds: float) -> None:
    # Released in a finally: a key left physically down would keep the
    # camera zooming or turning for the rest of the run.
    keyboard.key_down(vk)
    try:
        time.sleep(max(0.0, seconds))
    finally:
        keyboard.key_up(vk)


def tilt_camera_top_down(mouse, keyboard, hwnd) -> None:
    """Point the Roblox camera straight down. Leaves it zoomed out only as
    far as ZOOM_OUT_HOLD of O takes it from first person.

    Caller owns the focus dance. No mouse button is held at any point: in
    first person Roblox locks the cursor to the middle of the screen and
    turns the camera with plain mouse movement, so looking down needs no
    right-click drag -- the drag whose button came up outside the game
    over Remote Desktop. The pitch stops at its floor, and zooming back out
    keeps it.
    """
    left, top, right, bottom = wm.get_window_rect_screen(hwnd)
    cx, cy = (left + right) // 2, (top + bottom) // 2
    mouse.move_to(cx, cy)
    time.sleep(0.15)
    mouse.nudge()  # a real move event, so the game registers the cursor over it
    time.sleep(0.05)

    _hold_key(keyboard, ord("I"), ZOOM_IN_HOLD)

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
            time.sleep(LOOK_DOWN_TIME / LOOK_DOWN_STEPS)
        time.sleep(0.1)
    finally:
        # Both no matter what happened above. The clip goes first, so a
        # failing O can't leave the cursor caged in the game window for the
        # rest of the session. And O always runs: a game left in first
        # person keeps the cursor locked to the middle of the screen, and
        # every later click of the run would land there.
        wm.release_cursor_clip()
        _hold_key(keyboard, ord("O"), ZOOM_OUT_HOLD)
    time.sleep(0.15)


def run_camera_setup(mouse, keyboard, hwnd, hold_ms: float = 2000) -> None:
    """Tilt top-down, then hold O for the standard maximum zoom-out."""
    tilt_camera_top_down(mouse, keyboard, hwnd)
    _hold_key(keyboard, ord("O"), hold_ms / 1000)


def run_camera_rotate_hold(mouse, keyboard, hwnd, hold_ms: float = 2500, o_tap_ms: float = 0) -> None:
    """The same top-down tilt as run_camera_setup, but followed by holding
    the LEFT ARROW key for hold_ms (a camera rotate) instead of the O
    zoom-hold -- then, if o_tap_ms > 0, a short O press for that long (a
    small zoom step, not the full 2s zoom-out). This is EXPEDITION's Pre
    Start camera setup (730ms rotate + 100ms O -- the standard sequence
    doesn't frame Expedition maps right, see core.runner's _run_prestart);
    Settings > Debug > "Camera Setup 3" runs the rotate part on demand with
    any hold time for tuning. Same held-input-released-in-finally safety as
    run_camera_setup above."""
    from . import keys

    tilt_camera_top_down(mouse, keyboard, hwnd)
    _hold_key(keyboard, keys.VK_LEFT, hold_ms / 1000)

    if o_tap_ms > 0:
        time.sleep(0.1)
        _hold_key(keyboard, ord("O"), o_tap_ms / 1000)
