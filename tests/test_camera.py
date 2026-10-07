import pytest

from core import camera
from core import keys

I, O = ord("I"), ord("O")
GAME_RECT = (100, 200, 500, 600)


class FakeMouse:
    def __init__(self, events, fail_on_look=None):
        self.events = events
        self.looks = 0
        self.fail_on_look = fail_on_look

    def move_to(self, x, y):
        self.events.append(("move_to", x, y))

    def nudge(self, dx=1, dy=0):
        self.events.append(("nudge", dx, dy))
        if dy:
            self.looks += 1
            if self.looks == self.fail_on_look:
                raise RuntimeError("move failed")

    def down(self, button):
        self.events.append(("mouse_down", button))

    def up(self, button):
        self.events.append(("mouse_up", button))


class FakeKeyboard:
    def __init__(self, events, fail_on=None):
        self.events = events
        self.fail_on = fail_on

    def key_down(self, key):
        self.events.append(("key_down", key))
        if key == self.fail_on:
            raise RuntimeError("key failed")

    def key_up(self, key):
        self.events.append(("key_up", key))


@pytest.fixture(autouse=True)
def timeline(monkeypatch):
    """One timeline for every input, pause and cursor clip -- and the clip is
    only recorded, never really cages the cursor of whatever machine runs the
    tests."""
    events = []
    monkeypatch.setattr(camera.time, "sleep", lambda seconds: events.append(("sleep", seconds)))
    monkeypatch.setattr(camera.wm, "get_window_rect_screen", lambda _hwnd: GAME_RECT)
    monkeypatch.setattr(camera.wm, "clip_cursor", lambda rect: events.append(("clip", tuple(rect))) or True)
    monkeypatch.setattr(camera.wm, "release_cursor_clip", lambda: events.append(("release",)))
    return events


def _holds(events, vk):
    """How long each press of vk was held: the pauses between its down and up."""
    holds, start = [], None
    for i, event in enumerate(events):
        if event == ("key_down", vk):
            start = i
        elif event == ("key_up", vk) and start is not None:
            holds.append(sum(e[1] for e in events[start:i] if e[0] == "sleep"))
            start = None
    return holds


def _looks(events):
    return [i for i, e in enumerate(events) if e == ("nudge", 0, camera.LOOK_DOWN_PX)]


# The right-click drag let its button come up outside the game over Remote
# Desktop. The tilt now goes through first person instead, where Roblox turns
# the camera with plain mouse movement: I in, mouse down, O back out.

def test_tilt_zooms_in_looks_down_and_zooms_out_without_a_mouse_button(timeline):
    camera.tilt_camera_top_down(FakeMouse(timeline), FakeKeyboard(timeline), hwnd=123)

    assert timeline[0] == ("move_to", 300, 400)
    steps = [e for e in timeline if e[0] in ("key_down", "key_up", "nudge")]
    assert steps == ([("nudge", 1, 0), ("key_down", I), ("key_up", I)]
                     + [("nudge", 0, camera.LOOK_DOWN_PX)] * camera.LOOK_DOWN_STEPS
                     + [("key_down", O), ("key_up", O)])
    assert camera.LOOK_DOWN_PX > 0, "down, toward the ground"
    assert not [e for e in timeline if e[0] in ("mouse_down", "mouse_up")], "no button is held at any point"


def test_tilt_takes_half_a_second_each_for_i_the_mouse_and_o(timeline):
    camera.tilt_camera_top_down(FakeMouse(timeline), FakeKeyboard(timeline), hwnd=123)

    looks = _looks(timeline)
    look_time = sum(e[1] for e in timeline[looks[0]:looks[-1] + 2] if e[0] == "sleep")
    assert _holds(timeline, I) == [0.5]
    assert look_time == pytest.approx(0.5)
    assert _holds(timeline, O) == [0.5]


def test_look_down_keeps_the_cursor_inside_the_game_window(timeline):
    camera.tilt_camera_top_down(FakeMouse(timeline), FakeKeyboard(timeline), hwnd=123)

    assert all(timeline[i - 1] == ("clip", GAME_RECT) for i in _looks(timeline)), "re-set before every move"
    assert timeline.count(("release",)) == 1
    assert timeline.index(("release",)) < timeline.index(("key_down", O)), "freed before zooming back out"


def test_a_failing_look_down_still_zooms_back_out_and_frees_the_cursor(timeline):
    """Left in first person, the game keeps the cursor locked to the middle of
    the screen and every later click of the run lands there."""
    with pytest.raises(RuntimeError, match="move failed"):
        camera.tilt_camera_top_down(FakeMouse(timeline, fail_on_look=3), FakeKeyboard(timeline), hwnd=123)

    assert ("release",) in timeline
    assert _holds(timeline, O) == [camera.ZOOM_OUT_HOLD]
    assert timeline[-1] == ("key_up", O)


def test_cursor_is_freed_even_when_the_zoom_out_fails(timeline):
    with pytest.raises(RuntimeError, match="key failed"):
        camera.tilt_camera_top_down(FakeMouse(timeline), FakeKeyboard(timeline, fail_on=O), hwnd=123)

    assert ("release",) in timeline


def test_standard_camera_setup_zooms_out_fully_after_the_tilt(timeline):
    """The tilt alone leaves the camera close in. The 2s O hold after it is
    what gets back to the full zoom-out every Place Unit position was
    recorded against."""
    camera.run_camera_setup(FakeMouse(timeline), FakeKeyboard(timeline), hwnd=123, hold_ms=2000)

    assert _holds(timeline, I) == [0.5]
    assert _holds(timeline, O) == [0.5, 2.0]


def test_an_interrupted_hold_still_releases_its_key(monkeypatch, timeline):
    def sleep(seconds):
        timeline.append(("sleep", seconds))
        if seconds == 2.0:
            raise KeyboardInterrupt

    monkeypatch.setattr(camera.time, "sleep", sleep)

    with pytest.raises(KeyboardInterrupt):
        camera.run_camera_setup(FakeMouse(timeline), FakeKeyboard(timeline), hwnd=123, hold_ms=2000)

    assert timeline[-1] == ("key_up", O)


def test_expedition_rotate_follows_the_tilt_then_taps_o(timeline):
    camera.run_camera_rotate_hold(FakeMouse(timeline), FakeKeyboard(timeline), hwnd=123,
                                  hold_ms=730, o_tap_ms=100)

    assert [e[1] for e in timeline if e[0] == "key_down"] == [I, O, keys.VK_LEFT, O]
    assert _holds(timeline, keys.VK_LEFT) == [pytest.approx(0.73)]
    assert _holds(timeline, O) == [0.5, pytest.approx(0.1)]


def test_expedition_rotate_without_an_o_tap(timeline):
    camera.run_camera_rotate_hold(FakeMouse(timeline), FakeKeyboard(timeline), hwnd=123, hold_ms=730)

    assert [e[1] for e in timeline if e[0] == "key_down"] == [I, O, keys.VK_LEFT]
