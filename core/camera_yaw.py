"""Measures how far the Roblox camera's YAW is rotated away from the angle a
walk path was recorded at, so a route of timed W/A/S/D presses can be
replayed against the same world directions it was recorded against.

Why this exists: movement in Roblox is camera-relative -- W walks wherever
the camera looks. The initial camera yaw on spawning into a map comes from
the character's facing, and that varies between entries into the SAME map
(spawn pad orientation, another player shoving the character on the pad, a
spawn animation still running). core.camera's setup drags straight DOWN,
which pins the pitch top-down but never touches the yaw, so that spawn
variance survives the setup untouched and rotates the entire recorded route
with it -- reported as "sometimes the map is visibly turned ~30 degrees and
the macro walks off in the wrong direction".

The measurement only works because of what core.camera already does: with
the pitch pinned to its floor and the zoom held out, the viewport is
effectively a flat top-down view of the map, so a yaw difference shows up
as a plain ROTATION of the on-screen image. Comparing a live frame against
a reference frame captured at recording time therefore reduces to "by how
many degrees is this picture turned".

Method is a brute-force rotation sweep rather than a frequency-domain trick
(log-polar/Fourier-Mellin): the HUD does NOT rotate with the camera and
would dominate a whole-frame spectrum, pinning every estimate to 0. A sweep
lets us restrict the comparison to a HUD-free center crop, absorbs the fact
that the camera orbits the CHARACTER (not the screen center) as plain
translation that matchTemplate searches over anyway, and reports a score we
can threshold on instead of an answer we would have to trust blindly.
"""
import os
import time

import cv2

from . import constants
from . import keys
from . import paths as paths_mod
from . import vision
from .image_io import read_image

# Reference frames live beside the recordings they belong to -- a reference
# is only meaningful together with the path it was captured for. Writable
# APP_DIR, like Paths/ itself (see core.paths), never BUNDLE_DIR.
REFS_DIR = os.path.join(constants.APP_DIR, "Paths", "camera_refs")

# The slice of the viewport the comparison runs on, in reference space
# (1152x756, see core.config). Centered on the viewport center, which under
# the pinned top-down camera is where the character sits, and deliberately
# short of every edge: the Roblox topbar, the AE unit HUD along the bottom
# and the side panels are all SCREEN-fixed, so including any of them would
# feed the matcher a large patch that looks identical at every candidate
# angle and flatten the score peak this is trying to find.
WORLD_REGION = (276, 128, 600, 500)

# The center patch of the reference that gets matched INTO the live frame.
# Smaller than WORLD_REGION on purpose: the leftover margin is the search
# room matchTemplate needs to also absorb the character having spawned a
# little off from where it stood when the reference was taken.
_TEMPLATE_INSET = 0.62

# Sweep bounds. Spawn yaw variance reported in the wild is well inside +-60;
# going wider costs time and invites a false peak on a map that happens to
# be roughly rotationally symmetric.
_COARSE_LIMIT = 60.0
_COARSE_STEP = 3.0
_FINE_SPAN = 4.0
_FINE_STEP = 0.5

# Working scale for the coarse pass. The rotation of a whole map view is a
# large-scale feature -- halving the resolution costs nothing in angular
# accuracy at 3-degree steps and makes the 41-angle sweep cheap.
_COARSE_SCALE = 0.5

# Below this the estimate must not be acted on: a wrong act/stage, an
# occluded view (cutscene, loading) or a frame grabbed before the map
# finished rendering all score like this against a valid reference.
MIN_CONFIDENCE = 0.45


def ref_path(name: str) -> str:
    """Where the reference frame for a given path/map label is stored."""
    return os.path.join(REFS_DIR, f"{paths_mod._safe_name(name)}.png")


def has_reference(name: str) -> bool:
    return os.path.isfile(ref_path(name))


def capture_world_gray(hwnd: int):
    """The HUD-free center crop of the current frame, in reference space.

    Returns None when the window couldn't be captured at all, so callers can
    tell "no picture" apart from "picture that didn't match".
    """
    gray = vision.capture_game_gray(hwnd, WORLD_REGION)
    if gray is None or gray.size == 0:
        return None
    return gray


def save_reference(hwnd: int, name: str):
    """Capture the current view as the reference angle for `name`.

    Call this right after core.camera's setup has run, at the same point in
    the sequence the live measurement will later run at -- a reference is
    only valid for the exact pitch/zoom that produced it.
    """
    gray = capture_world_gray(hwnd)
    if gray is None:
        return None
    os.makedirs(REFS_DIR, exist_ok=True)
    ok, encoded = cv2.imencode(".png", gray)
    if not ok:
        return None
    target = ref_path(name)
    # Same reason core.image_io decodes bytes instead of handing OpenCV a
    # filename: cv2's path handling breaks on non-ASCII Windows paths.
    with open(target, "wb") as handle:
        handle.write(encoded.tobytes())
    return target


def load_reference(name: str):
    img = read_image(ref_path(name), cv2.IMREAD_GRAYSCALE)
    if img is None or img.size == 0:
        return None
    if img.ndim == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return img


def _rotate(img, angle_deg: float):
    """Rotate about the image center. Positive angle = counter-clockwise,
    matching cv2's own convention so the sign never has to be re-derived."""
    h, w = img.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), angle_deg, 1.0)
    return cv2.warpAffine(img, matrix, (w, h), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REPLICATE)


def _center_crop(img, inset: float):
    h, w = img.shape[:2]
    cw, ch = int(w * inset), int(h * inset)
    x, y = (w - cw) // 2, (h - ch) // 2
    return img[y:y + ch, x:x + cw]


def _score_at(haystack, template, angle_deg: float) -> float:
    """How well the reference template fits the live frame once the LIVE
    frame is turned back by `angle_deg`.

    Rotating the haystack rather than the template is what keeps this
    honest: a rotated rectangular template drags invalid corner pixels into
    the correlation and biases the score toward 0 degrees, the one angle at
    which no such corners exist.
    """
    rotated = _rotate(haystack, angle_deg)
    match = vision.best_match_in_gray(rotated, template)
    return match["score"] if match else -1.0


def estimate_rotation(ref_gray, cur_gray) -> dict:
    """How far the live view is rotated away from the reference view.

    Returns {"ok": bool, "angle": degrees, "score": 0..1}. `angle` is the
    rotation that has to be applied to the LIVE frame to bring it back onto
    the reference (positive = counter-clockwise, cv2 convention).

    Coarse sweep at half resolution to find the peak, then a fine sweep at
    full resolution around it -- a flat scan at 0.5-degree steps over the
    whole range would be several times the work for the same answer.
    """
    if ref_gray is None or cur_gray is None:
        return {"ok": False, "angle": 0.0, "score": 0.0}
    if ref_gray.shape[:2] != cur_gray.shape[:2]:
        ref_gray = cv2.resize(ref_gray, (cur_gray.shape[1], cur_gray.shape[0]),
                              interpolation=cv2.INTER_AREA)

    small_ref = cv2.resize(ref_gray, None, fx=_COARSE_SCALE, fy=_COARSE_SCALE,
                           interpolation=cv2.INTER_AREA)
    small_cur = cv2.resize(cur_gray, None, fx=_COARSE_SCALE, fy=_COARSE_SCALE,
                           interpolation=cv2.INTER_AREA)
    small_template = _center_crop(small_ref, _TEMPLATE_INSET)

    best_angle, best_score = 0.0, -1.0
    steps = int(round(_COARSE_LIMIT / _COARSE_STEP))
    for i in range(-steps, steps + 1):
        angle = i * _COARSE_STEP
        score = _score_at(small_cur, small_template, angle)
        if score > best_score:
            best_angle, best_score = angle, score

    template = _center_crop(ref_gray, _TEMPLATE_INSET)
    fine_steps = int(round(_FINE_SPAN / _FINE_STEP))
    refined_angle, refined_score = best_angle, -1.0
    for i in range(-fine_steps, fine_steps + 1):
        angle = best_angle + i * _FINE_STEP
        score = _score_at(cur_gray, template, angle)
        if score > refined_score:
            refined_angle, refined_score = angle, score

    return {"ok": refined_score >= MIN_CONFIDENCE,
            "angle": float(refined_angle),
            "score": float(refined_score)}


def measure(hwnd: int, name: str) -> dict:
    """Measure the live camera against the stored reference for `name`.

    The failure reasons stay distinguishable on purpose: "no reference yet"
    is a setup step the caller can perform, "couldn't capture" is a broken
    window, and a low score is a real measurement that simply must not be
    acted on.
    """
    ref = load_reference(name)
    if ref is None:
        return {"ok": False, "reason": "no_reference", "angle": 0.0, "score": 0.0}
    cur = capture_world_gray(hwnd)
    if cur is None:
        return {"ok": False, "reason": "no_capture", "angle": 0.0, "score": 0.0}
    result = estimate_rotation(ref, cur)
    if not result["ok"]:
        result["reason"] = "low_confidence"
    return result


# ---------------------------------------------------------------------------
# Correction
#
# Roblox turns the camera with the arrow keys at a rate that is neither
# documented nor constant (it moves with the client's frame rate), which is
# exactly why core.camera's Expedition sequence holds Left for a fixed 730ms
# and still lands somewhere slightly different every time. So nothing here
# assumes a degrees-per-second figure: the loop presses, measures what that
# press actually achieved, and derives the rate from it. An unknown and
# drifting rate stops mattering once the loop is closed.
# ---------------------------------------------------------------------------

# Good enough to walk a recorded route on: half a step of the coarse sweep,
# and well under the ~30 degrees that makes a route visibly wrong.
TOLERANCE_DEG = 2.5

# First press when no rate is known yet. Long enough to produce a change the
# sweep can measure against its own 0.5-degree resolution, short enough not
# to spin the camera somewhere the reference can no longer be recognized.
_PROBE_MS = 150.0
_MIN_PROBE_CHANGE_DEG = 2.0
_MAX_PROBE_MS = 600.0

# A correction press is capped so one bad rate estimate cannot send the
# camera spinning past the point where the next measurement still matches.
_MAX_PULSE_MS = 900.0
_MIN_PULSE_MS = 25.0

MAX_ITERATIONS = 6

# Carried between calls purely as a SEED for the probe -- every alignment
# still re-derives the rate from its own first press, since frame rate (and
# with it the rate) changes between sessions and even between maps.
_last_rate = None


def _pulse(keyboard, signed_ms: float, sleep_fn) -> None:
    """Hold Left (positive) or Right (negative) for |signed_ms|.

    Released in a finally for the same reason core.camera guards its drag:
    an arrow key left physically down would keep the camera rotating for the
    rest of the run, turning one bad alignment into a broken session.
    """
    vk = keys.VK_LEFT if signed_ms >= 0 else keys.VK_RIGHT
    hold = min(_MAX_PULSE_MS, max(_MIN_PULSE_MS, abs(signed_ms)))
    keyboard.key_down(vk)
    try:
        sleep_fn(hold / 1000.0)
    finally:
        keyboard.key_up(vk)
    # The camera keeps easing for a beat after the key comes up; measuring
    # through that tail would attribute the overshoot to the next press.
    sleep_fn(0.25)


def align(keyboard, hwnd, name, log=None, sleep_fn=None,
          tolerance: float = TOLERANCE_DEG, max_iters: int = MAX_ITERATIONS) -> dict:
    """Rotate the camera back onto the angle `name`'s reference was taken at.

    Returns {"ok", "angle", "score", "iterations", "reason"} where `angle` is
    the residual after the last correction. `ok` is False whenever the camera
    could not be trusted to be aligned -- a caller should then treat the walk
    as unsafe rather than run it anyway, since an unaligned route is worse
    than no route.

    `sleep_fn` lets the runner pass its own interruptible sleep so a Stop
    press doesn't have to wait out the loop.
    """
    global _last_rate
    sleep_fn = sleep_fn or time.sleep

    def _say(message):
        if log:
            log(message)

    result = measure(hwnd, name)
    if not result["ok"]:
        _say(f"[Camera] Yaw check failed ({result.get('reason')}) -- leaving the camera alone.")
        return {**result, "iterations": 0}
    if abs(result["angle"]) <= tolerance:
        _say(f"[Camera] Yaw already within {tolerance:.1f} deg "
             f"({result['angle']:+.1f} deg, score {result['score']:.2f}).")
        return {**result, "iterations": 0}

    _say(f"[Camera] Yaw off by {result['angle']:+.1f} deg "
         f"(score {result['score']:.2f}) -- correcting.")

    rate = _last_rate  # degrees of measured change per second of Left held
    probe_ms = _PROBE_MS
    for iteration in range(1, max_iters + 1):
        before = result["angle"]
        if rate:
            # -before/rate is the hold that would zero the residual; the
            # sign of that value picks Left vs Right in _pulse.
            signed_ms = -(before / rate) * 1000.0
        else:
            signed_ms = probe_ms

        _pulse(keyboard, signed_ms, sleep_fn)
        result = measure(hwnd, name)
        if not result["ok"]:
            _say(f"[Camera] Lost the reference mid-correction ({result.get('reason')}) "
                 "-- stopping before this makes it worse.")
            return {**result, "iterations": iteration}

        change = result["angle"] - before
        held_s = min(_MAX_PULSE_MS, max(_MIN_PULSE_MS, abs(signed_ms))) / 1000.0
        held_s = held_s if signed_ms >= 0 else -held_s
        if abs(change) >= _MIN_PROBE_CHANGE_DEG and held_s:
            rate = change / held_s
            _last_rate = rate
        elif rate is None:
            # The probe was too short to register. Lengthen it rather than
            # dividing by a change that is mostly measurement noise.
            probe_ms = min(_MAX_PROBE_MS, probe_ms * 2)
            if probe_ms >= _MAX_PROBE_MS and abs(change) < _MIN_PROBE_CHANGE_DEG:
                _say("[Camera] Arrow keys aren't moving the camera -- is Roblox focused?")
                return {**result, "ok": False, "reason": "no_response",
                        "iterations": iteration}

        if abs(result["angle"]) <= tolerance:
            _say(f"[Camera] Yaw aligned after {iteration} correction(s): "
                 f"{result['angle']:+.1f} deg (score {result['score']:.2f}).")
            return {**result, "iterations": iteration}

    _say(f"[Camera] Yaw still {result['angle']:+.1f} deg off after {max_iters} "
         "corrections -- giving up.")
    return {**result, "ok": False, "reason": "not_converged", "iterations": max_iters}
