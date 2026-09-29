import cv2
import numpy as np
import pytest

from core import camera_yaw
from core import keys


def _synthetic_map(seed=7, size=900):
    """A stand-in for the top-down map view: large blurred structure plus
    hard-edged blocks, so template matching has real features to lock onto
    rather than the flat gradients a plain noise image would give it."""
    rng = np.random.default_rng(seed)
    img = rng.random((size, size)).astype(np.float32)
    img = cv2.GaussianBlur(img, (0, 0), 9)
    img = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    for _ in range(25):
        x, y = rng.integers(80, size - 80, 2)
        cv2.rectangle(img, (int(x), int(y)),
                      (int(x) + int(rng.integers(20, 70)), int(y) + int(rng.integers(20, 70))),
                      int(rng.integers(0, 255)), -1)
    return img


def _view(img, angle_deg=0.0):
    """The WORLD_REGION-sized crop a camera turned by angle_deg would see."""
    h, w = img.shape[:2]
    if angle_deg:
        matrix = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), -angle_deg, 1.0)
        img = cv2.warpAffine(img, matrix, (w, h), borderMode=cv2.BORDER_REPLICATE)
    _, _, rw, rh = camera_yaw.WORLD_REGION
    cy, cx = h // 2, w // 2
    return img[cy - rh // 2:cy + rh // 2, cx - rw // 2:cx + rw // 2]


class FakeKeyboard:
    """Records presses and, when wired to a FakeCamera, is what actually
    makes that camera turn -- the camera only moves while a key is held, so
    the two have to be connected or a convergence test would silently be
    measuring a camera nothing ever rotated."""

    def __init__(self, camera=None):
        self.events = []
        self.camera = camera

    def key_down(self, key):
        self.events.append(("down", key))
        if self.camera is not None:
            self.camera.holding = key

    def key_up(self, key):
        self.events.append(("up", key))
        if self.camera is not None:
            self.camera.holding = None


class FakeCamera:
    """A camera whose yaw only changes while an arrow key is held, at a rate
    the caller does not get to know -- the situation core.camera_yaw.align
    exists for. `rate_sign` flips which arrow key reduces the offset, since
    nothing in the loop may assume that direction."""

    def __init__(self, offset, rate=85.0, rate_sign=1, jitter=0.0, seed=3):
        self.offset = offset
        self.rate = rate * rate_sign
        self.jitter = jitter
        self.holding = None
        self.presses = 0
        self._rng = np.random.default_rng(seed)

    def sleep(self, seconds):
        if self.holding is None:
            return
        wobble = 1.0 + float(self._rng.uniform(-self.jitter, self.jitter))
        direction = 1 if self.holding == keys.VK_LEFT else -1
        self.offset += direction * self.rate * seconds * wobble
        self.presses += 1

    def measure(self, _hwnd, _name):
        return {"ok": True, "angle": self.offset, "score": 0.8}


@pytest.fixture
def instant_align(monkeypatch):
    """align() with a rate it has not learned yet -- a leaked rate from an
    earlier test would hide exactly the cold-start behavior worth testing."""
    monkeypatch.setattr(camera_yaw, "_last_rate", None)


@pytest.mark.parametrize("truth", [0.0, 4.5, -12.5, 30.0, -30.0, 47.0])
def test_a_rotated_view_is_measured_back_to_its_true_angle(truth):
    base = _synthetic_map()
    result = camera_yaw.estimate_rotation(_view(base), _view(base, truth))
    assert result["ok"]
    assert result["angle"] == pytest.approx(truth, abs=camera_yaw._FINE_STEP)


def test_an_unrelated_view_is_reported_as_low_confidence_not_as_an_angle():
    # A different map (or a cutscene, or a frame grabbed before the map
    # rendered) must not produce a confident angle the caller would then
    # turn the camera by.
    result = camera_yaw.estimate_rotation(_view(_synthetic_map(seed=1)),
                                          _view(_synthetic_map(seed=99)))
    assert not result["ok"]
    assert result["score"] < camera_yaw.MIN_CONFIDENCE


def test_measure_without_a_stored_reference_says_so(monkeypatch, tmp_path):
    monkeypatch.setattr(camera_yaw, "REFS_DIR", str(tmp_path))
    result = camera_yaw.measure(1, "never recorded")
    assert result == {"ok": False, "reason": "no_reference", "angle": 0.0, "score": 0.0}


@pytest.mark.parametrize("rate_sign", [1, -1])
@pytest.mark.parametrize("start", [-31.0, 12.0, 44.0, -5.0])
def test_align_converges_without_being_told_the_rate_or_the_direction(
        monkeypatch, instant_align, rate_sign, start):
    fake = FakeCamera(start, rate_sign=rate_sign, jitter=0.15)
    monkeypatch.setattr(camera_yaw, "measure", fake.measure)

    result = camera_yaw.align(FakeKeyboard(fake), 1, "map", sleep_fn=fake.sleep)

    assert result["ok"]
    assert abs(result["angle"]) <= camera_yaw.TOLERANCE_DEG
    assert fake.presses <= camera_yaw.MAX_ITERATIONS


def test_align_does_not_touch_a_camera_that_is_already_aligned(monkeypatch, instant_align):
    fake = FakeCamera(1.0)
    monkeypatch.setattr(camera_yaw, "measure", fake.measure)
    keyboard = FakeKeyboard(fake)

    result = camera_yaw.align(keyboard, 1, "map", sleep_fn=fake.sleep)

    assert result["ok"] and result["iterations"] == 0
    assert keyboard.events == []


def test_align_reports_failure_instead_of_walking_an_unaligned_route(monkeypatch, instant_align):
    # Losing the reference mid-correction has to fail loudly: replaying a
    # recorded path against a camera that is still turned is worse than not
    # replaying it at all.
    calls = {"n": 0}

    def flaky_measure(_hwnd, _name):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"ok": True, "angle": 25.0, "score": 0.8}
        return {"ok": False, "reason": "low_confidence", "angle": 0.0, "score": 0.1}

    monkeypatch.setattr(camera_yaw, "measure", flaky_measure)
    result = camera_yaw.align(FakeKeyboard(), 1, "map", sleep_fn=lambda _s: None)

    assert not result["ok"]
    assert result["reason"] == "low_confidence"


def test_align_never_leaves_an_arrow_key_held_down(monkeypatch, instant_align):
    # An arrow key left down would keep rotating the camera for the rest of
    # the run -- the same failure core.camera guards its drag against.
    fake = FakeCamera(20.0)
    monkeypatch.setattr(camera_yaw, "measure", fake.measure)
    keyboard = FakeKeyboard(fake)

    def exploding_sleep(seconds):
        fake.sleep(seconds)
        if keyboard.events and keyboard.events[-1][0] == "down":
            raise RuntimeError("input backend died mid-hold")

    with pytest.raises(RuntimeError):
        camera_yaw.align(keyboard, 1, "map", sleep_fn=exploding_sleep)

    downs = [key for kind, key in keyboard.events if kind == "down"]
    ups = [key for kind, key in keyboard.events if kind == "up"]
    assert downs == ups


def test_align_gives_up_when_the_arrow_keys_do_nothing(monkeypatch, instant_align):
    # Roblox not focused: the presses land nowhere and the angle never
    # moves. Better to say so than to keep pressing for six rounds.
    stuck = FakeCamera(30.0, rate=0.0)
    monkeypatch.setattr(camera_yaw, "measure", stuck.measure)

    result = camera_yaw.align(FakeKeyboard(stuck), 1, "map", sleep_fn=stuck.sleep)

    assert not result["ok"]
    assert result["reason"] in ("no_response", "not_converged")
