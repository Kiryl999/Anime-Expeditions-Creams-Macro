import re
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core import runner as runner_module
from core import runner_boss_rush
from core import vision
from core.runner import MacroRunner
from core.runner_constants import (
    BOSS_RUSH_CARD_IMAGE,
    BOSS_RUSH_CONTINUE_IMAGE,
    BOSS_RUSH_FIGHT_BOSS_IMAGE,
    BOSS_RUSH_GATE_COUNT,
    BOSS_RUSH_IMAGE_NAMES,
    BOSS_RUSH_MAP_IMAGES,
    BOSS_RUSH_MAP_ORDER,
    BOSS_RUSH_MIN_BOSS_GATE,
    BOSS_RUSH_POST_GATE_TIMEOUT,
)

MAP = BOSS_RUSH_MAP_ORDER[0]
# The real shipped routes, captured before the autouse fixture below hides
# them from every test that is not about them.
SHIPPED_GATE_PATHS = dict(runner_boss_rush.walk_paths._BUILTIN_BOSS_RUSH_GATE_PATHS)


def _match(name="x", cx=400, cy=300, score=0.9):
    return {"x": cx - 10, "y": cy - 5, "w": 20, "h": 10, "cx": cx, "cy": cy,
            "score": score, "name": name}


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def time(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FakeRunner(runner_boss_rush.BossRushOps):
    """The mixin with just the MacroRunner surface it touches."""

    def __init__(self, clock=None):
        self.clock = clock or _Clock()
        self.logs = []
        self.screenshots = []
        self.middle_clicks = 0
        self.taps = []
        self._coords = {"screen_middle_x": 576, "screen_middle_y": 378}
        self._mouse = MagicMock()
        self._mouse.click.side_effect = lambda *_a, **_k: self._on_middle_click()
        self._keyboard = MagicMock()
        self._keyboard.tap.side_effect = self.taps.append

    def _on_middle_click(self):
        self.middle_clicks += 1

    def _log(self, message):
        self.logs.append(message)

    def _set_status(self, **_kw):
        pass

    def _debug_save(self, hwnd, name, match):
        return None

    def _checkpoint(self, stop_event):
        return stop_event is not None and stop_event.is_set()

    def _interruptible_sleep(self, seconds, stop_event=None):
        self.clock.advance(seconds)

    def _save_debug_screenshot_unconditional(self, hwnd, name):
        self.screenshots.append(name)
        return None

    @property
    def said(self):
        return " ".join(self.logs)


@pytest.fixture(autouse=True)
def quiet_window(monkeypatch):
    monkeypatch.setattr(runner_boss_rush.wm, "activate_window", lambda _h: True)
    monkeypatch.setattr(runner_boss_rush.wm, "get_window_rect_screen", lambda _h: (0, 0, 1152, 756))


@pytest.fixture(autouse=True)
def no_shipped_routes(monkeypatch):
    """Default: nothing ships for any map, so a test's own gate_paths are the
    only routes there are. The tests about shipped routes set their own."""
    monkeypatch.setattr(runner_boss_rush.walk_paths, "_BUILTIN_BOSS_RUSH_GATE_PATHS", {})


def _ship(monkeypatch, gates, sprint=True, map_name=MAP):
    monkeypatch.setattr(runner_boss_rush.walk_paths, "_BUILTIN_BOSS_RUSH_GATE_PATHS",
                        {map_name: {"gates": list(gates), "sprint": sprint}})


@pytest.fixture(autouse=True)
def all_crops_present(monkeypatch):
    """Default: every reference image exists. The tests about MISSING crops
    override this."""
    monkeypatch.setattr(vision, "template_variant_paths", lambda name, d=None: ["x.png"])


# ── the task's fields ──────────────────────────────────────────────────────

@pytest.mark.parametrize("value, gate", [
    ("2", 2), ("4", 4), ("6", 6), (6, 6),
    # The game offers Fight Boss from gate 2 and forces it after gate 6 --
    # anything outside that is clamped to the nearest gate that exists.
    ("1", BOSS_RUSH_MIN_BOSS_GATE), ("9", BOSS_RUSH_GATE_COUNT),
    ("", BOSS_RUSH_MIN_BOSS_GATE), (None, BOSS_RUSH_MIN_BOSS_GATE), ("abc", BOSS_RUSH_MIN_BOSS_GATE),
])
def test_the_boss_gate_is_clamped_to_the_gates_the_game_offers_it_after(value, gate):
    assert runner_boss_rush.BossRushOps._boss_rush_boss_gate({"boss_after": value}) == gate


@pytest.mark.parametrize("raw, expected", [
    (None, [""] * 6),
    (["a", "b"], ["a", "b", "", "", "", ""]),
    ([" a ", None, "c", "", "e", "f", "too many"], ["a", "", "c", "", "e", "f"]),
    ("not a list", [""] * 6),
])
def test_gate_paths_are_always_one_per_gate(raw, expected):
    assert runner_boss_rush.BossRushOps._boss_rush_gate_paths({"gate_paths": raw}) == expected


def test_the_boss_fight_uses_its_own_macro_operation_when_one_is_set():
    task = {"mode": "boss_rush", "macro": "Gates", "boss_macro": "Boss Arena"}
    boss = runner_boss_rush.BossRushOps._boss_rush_boss_task(task)
    assert boss["macro"] == "Boss Arena"
    assert task["macro"] == "Gates", "the task itself must not be changed"


def test_without_a_boss_macro_the_boss_fight_reuses_the_gates_one():
    task = {"mode": "boss_rush", "macro": "Gates", "boss_macro": ""}
    assert runner_boss_rush.BossRushOps._boss_rush_boss_task(task)["macro"] == "Gates"


# ── shipped routes ─────────────────────────────────────────────────────────

def test_an_unset_gate_walks_the_shipped_route_at_its_own_speed(monkeypatch):
    _ship(monkeypatch, ["s1", "s2", "s3"], sprint=True)
    task = {"map": MAP, "gate_paths": ["mine", "", ""], "gate_sprint": False}
    assert runner_boss_rush.BossRushOps._boss_rush_routes(task)[:4] == [
        ("mine", False),   # the task's own recording, at the task's own speed
        ("s2", True),      # shipped routes were recorded sprinting
        ("s3", True),
        ("", False),       # nothing shipped for gate 4
    ]


def test_a_map_with_nothing_shipped_only_has_the_tasks_own_routes():
    task = {"map": MAP, "gate_paths": ["mine"], "gate_sprint": True}
    assert runner_boss_rush.BossRushOps._boss_rush_routes(task) == (
        [("mine", True)] + [("", False)] * (BOSS_RUSH_GATE_COUNT - 1))


def test_a_task_with_nothing_recorded_runs_on_the_shipped_routes(monkeypatch):
    _ship(monkeypatch, ["s1", "s2", "s3"])
    _recordings(monkeypatch, "s1", "s2", "s3")
    runner = FakeRunner()
    assert runner._boss_rush_preflight(_task(routes=())) is True


def test_a_missing_shipped_recording_is_named(monkeypatch):
    _ship(monkeypatch, ["s1", "s2", "s3"])
    _recordings(monkeypatch, "s1", "s3")
    runner = FakeRunner()
    assert runner._boss_rush_preflight(_task(routes=())) is False
    assert 'gate 2 ("s2")' in runner.said


def test_the_run_walks_shipped_routes_sprinting_even_with_the_tasks_sprint_off(monkeypatch):
    _ship(monkeypatch, ["s1", "s2"], sprint=True)
    runner = RunRunner()
    _run(runner, _task(boss_after="2", routes=("mine",), gate_sprint=False))
    assert runner.of("enter") == [("enter", 1, "mine", False), ("enter", 2, "s2", True)]


def test_every_shipped_route_is_a_real_recording_for_a_real_map():
    """What ships has to be complete: one recording per gate, each actually
    present in Paths/defaults with movement in it, for a map the Task Builder
    offers."""
    import json
    import os
    assert SHIPPED_GATE_PATHS, "nothing shipped at all"
    for map_name, entry in SHIPPED_GATE_PATHS.items():
        assert map_name in BOSS_RUSH_MAP_ORDER
        assert len(entry["gates"]) == BOSS_RUSH_GATE_COUNT
        for name in entry["gates"]:
            path = os.path.join(runner_boss_rush.walk_paths.DEFAULT_PATHS_DIR, f"{name}.json")
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            assert data.get("name") == name
            assert data.get("events"), f"{name} has no movement"


# ── preflight ──────────────────────────────────────────────────────────────

def _recordings(monkeypatch, *names):
    monkeypatch.setattr(runner_boss_rush.walk_paths, "load_path",
                        lambda name: {"name": name, "events": [{"t": 0, "key": "w", "state": "down"}]
                                      if name in names else []})


def _task(boss_after="3", routes=("g1", "g2", "g3"), **extra):
    return dict({"mode": "boss_rush", "map": MAP, "boss_after": boss_after,
                 "gate_paths": list(routes), "macro": "Gates"}, **extra)


def test_a_fully_set_up_task_passes(monkeypatch):
    _recordings(monkeypatch, "g1", "g2", "g3")
    runner = FakeRunner()
    assert runner._boss_rush_preflight(_task()) is True
    assert runner.logs == []


def test_routes_past_the_boss_gate_are_not_required(monkeypatch):
    # Boss after gate 2 never walks to gates 3-6.
    _recordings(monkeypatch, "g1", "g2")
    assert FakeRunner()._boss_rush_preflight(_task(boss_after="2", routes=("g1", "g2"))) is True


def test_a_missing_route_is_refused_and_named(monkeypatch):
    _recordings(monkeypatch, "g1", "g3")
    runner = FakeRunner()
    assert runner._boss_rush_preflight(_task(routes=("g1", "", "g3"))) is False
    assert "no route set for gate 2" in runner.said


def test_a_route_whose_recording_is_gone_is_refused_and_named(monkeypatch):
    _recordings(monkeypatch, "g1", "g2")
    runner = FakeRunner()
    assert runner._boss_rush_preflight(_task()) is False
    assert 'gate 3 ("g3")' in runner.said


def test_missing_crops_are_refused_and_named(monkeypatch):
    _recordings(monkeypatch, "g1", "g2", "g3")
    monkeypatch.setattr(vision, "template_variant_paths",
                        lambda name, d=None: [] if name == BOSS_RUSH_CARD_IMAGE else ["x.png"])
    runner = FakeRunner()
    assert runner._boss_rush_preflight(_task()) is False
    assert BOSS_RUSH_CARD_IMAGE in runner.said


def test_an_unknown_map_is_refused(monkeypatch):
    _recordings(monkeypatch, "g1", "g2", "g3")
    runner = FakeRunner()
    assert runner._boss_rush_preflight(_task(map="Nowhere")) is False
    assert "Nowhere" in runner.said


def test_every_crop_a_run_needs_is_checked(monkeypatch):
    seen = []
    monkeypatch.setattr(vision, "template_variant_paths",
                        lambda name, d=None: seen.append(name) or [])
    missing = FakeRunner()._boss_rush_missing_crops(_task())
    assert set(missing) == set(BOSS_RUSH_IMAGE_NAMES) | {
        BOSS_RUSH_MAP_IMAGES[MAP], BOSS_RUSH_CARD_IMAGE,
        BOSS_RUSH_FIGHT_BOSS_IMAGE, BOSS_RUSH_CONTINUE_IMAGE}


# ── getting into a gate ────────────────────────────────────────────────────

def _gate_runner(monkeypatch, start_game_results):
    runner = FakeRunner()
    _recordings(monkeypatch, "route")
    walked = []
    monkeypatch.setattr(runner_boss_rush.walk_paths, "replay_events",
                        lambda events, kb, stop, sprint=False: walked.append(sprint))
    results = list(start_game_results)
    runner._find_start_game_button = lambda hwnd, stop=None, timeout=0: (
        ("nav_start_game", _match()) if results.pop(0) else (None, None))
    runner.walked = walked
    return runner


def test_a_route_that_presses_e_itself_is_not_given_another(monkeypatch):
    runner = _gate_runner(monkeypatch, [True])
    assert runner._enter_boss_rush_gate(1, threading.Event(), 1, "route", sprint=True) is True
    assert runner.taps == []
    assert runner.walked == [True], "the task's sprint setting reaches the replay"


def test_a_route_recorded_without_e_gets_it_pressed_once(monkeypatch):
    runner = _gate_runner(monkeypatch, [False, True])
    assert runner._enter_boss_rush_gate(1, threading.Event(), 2, "route", sprint=False) is True
    assert runner.taps == [ord("E")]


def test_a_walk_that_misses_the_gate_abandons_the_run(monkeypatch):
    runner = _gate_runner(monkeypatch, [False, False])
    assert runner._enter_boss_rush_gate(1, threading.Event(), 3, "route", sprint=False) is False
    assert runner.screenshots == ["boss_rush_gate_3_not_entered"]
    assert '"route"' in runner.said


def test_an_empty_route_is_not_walked(monkeypatch):
    runner = _gate_runner(monkeypatch, [])
    assert runner._enter_boss_rush_gate(1, threading.Event(), 1, "", sprint=False) is False
    assert runner.walked == []


# ── recognising a cleared gate mid-battle ──────────────────────────────────

def test_any_post_gate_screen_counts_as_cleared(monkeypatch):
    asked = []

    def find_any(hwnd, names, **kw):
        asked.append(tuple(names))
        return _match(), BOSS_RUSH_FIGHT_BOSS_IMAGE

    monkeypatch.setattr(vision, "find_image_any", find_any)
    assert FakeRunner()._boss_rush_gate_cleared(1) is True
    assert set(asked[0]) == {BOSS_RUSH_CARD_IMAGE, BOSS_RUSH_FIGHT_BOSS_IMAGE,
                             BOSS_RUSH_CONTINUE_IMAGE}


def test_nothing_on_screen_is_not_cleared(monkeypatch):
    monkeypatch.setattr(vision, "find_image_any", lambda *a, **k: (None, None))
    measured = []
    runner = FakeRunner()
    runner._measure_boss_rush_card = measured.append
    assert runner._boss_rush_gate_cleared(1) is False
    assert measured == [1], "a miss is measured, so a near miss can be reported"


def _measuring_runner(monkeypatch, scores):
    """A runner whose card crop scores the given values, one per measurement."""
    runner = FakeRunner()
    monkeypatch.setattr(runner_boss_rush.time, "time", runner.clock.time)
    monkeypatch.setattr(vision, "capture_game_gray", lambda hwnd, region=None: "frame")
    queue = list(scores)
    monkeypatch.setattr(vision, "find_in_gray_multiscale_diagnostic",
                        lambda gray, name, *a, **k: {"match": None, "best": {"score": queue.pop(0)}})
    runner._save_debug_screenshot_unconditional = lambda hwnd, name: (
        runner.screenshots.append(name) or "debug/near_miss.png")
    runner._reset_boss_rush_card_watch()
    return runner


def _measure(runner, times):
    for _ in range(times):
        runner.clock.advance(runner_boss_rush.BOSS_RUSH_CARD_MEASURE_INTERVAL)
        runner._measure_boss_rush_card(1)


def test_a_card_screen_just_under_the_threshold_is_reported_with_a_screenshot(monkeypatch):
    runner = _measuring_runner(monkeypatch, [0.40, 0.84, 0.86])
    _measure(runner, 3)
    assert runner.screenshots == ["boss_rush_card_near_miss"], "one screenshot per gate, not per tick"
    assert "score 0.84" in runner.said and "needs 0.90" in runner.said
    assert "debug/near_miss.png" in runner.said


def test_a_plain_battle_only_reports_its_best_score_now_and_then(monkeypatch):
    runner = _measuring_runner(monkeypatch, [0.30, 0.45, 0.35] * 20)
    _measure(runner, 60)   # two minutes of battle
    assert runner.screenshots == []
    reports = [line for line in runner.logs if "no card screen yet" in line]
    assert 2 <= len(reports) <= 5
    assert "0.45" in reports[-1], "the best score of the gate, not the latest"


def test_measuring_is_throttled(monkeypatch):
    runner = _measuring_runner(monkeypatch, [0.3])
    runner.clock.advance(runner_boss_rush.BOSS_RUSH_CARD_MEASURE_INTERVAL)
    runner._measure_boss_rush_card(1)
    runner._measure_boss_rush_card(1)   # same instant: must not scan again (queue would be empty)


def test_a_failing_measurement_never_breaks_the_battle_loop(monkeypatch):
    runner = FakeRunner()
    monkeypatch.setattr(runner_boss_rush.time, "time", runner.clock.time)

    def boom(*a, **k):
        raise RuntimeError("capture failed")

    monkeypatch.setattr(vision, "capture_game_gray", boom)
    runner._reset_boss_rush_card_watch()
    runner.clock.advance(10)
    runner._measure_boss_rush_card(1)
    assert runner.logs == []


def test_each_gate_starts_with_a_fresh_card_measurement(monkeypatch):
    runner = _measuring_runner(monkeypatch, [0.8, 0.8])
    _measure(runner, 1)
    runner._reset_boss_rush_card_watch()
    _measure(runner, 1)
    assert runner.screenshots == ["boss_rush_card_near_miss"] * 2


def test_missing_crops_are_not_a_crash_mid_battle(monkeypatch):
    def raise_missing(*a, **k):
        raise vision.TemplateNotFound("none")
    monkeypatch.setattr(vision, "find_image_any", raise_missing)
    runner = FakeRunner()
    assert runner._boss_rush_gate_cleared(1) is False
    assert runner.logs == [], "polled every tick -- must stay quiet"


# ── after a gate: the card, then Fight Boss or Continue ────────────────────

class Screen:
    """The post-gate screens as a queue: each entry is the set of images
    showing; a click on one of them (or the middle click, for the card)
    moves on to the next entry."""

    def __init__(self, *stages):
        self.stages = [set(s) for s in stages]
        self.pressed = []

    @property
    def showing(self):
        return self.stages[0] if self.stages else set()

    def find(self, hwnd, name, **kw):
        return _match(name) if name in self.showing else None

    def click_match(self, mouse, hwnd, match, **kw):
        self.pressed.append(match["name"])
        self.stages.pop(0)

    def middle_click(self):
        if BOSS_RUSH_CARD_IMAGE in self.showing:
            self.pressed.append("card")
            self.stages.pop(0)


def _after_gate(monkeypatch, screen, gate, want_boss):
    runner = FakeRunner()
    monkeypatch.setattr(runner_boss_rush.time, "time", runner.clock.time)
    monkeypatch.setattr(vision, "find_image", screen.find)
    monkeypatch.setattr(vision, "click_match", screen.click_match)
    runner._on_middle_click = screen.middle_click
    choice = runner._boss_rush_after_gate(1, threading.Event(), gate, want_boss)
    return runner, choice


CARD = {BOSS_RUSH_CARD_IMAGE}
BOTH = {BOSS_RUSH_FIGHT_BOSS_IMAGE, BOSS_RUSH_CONTINUE_IMAGE}


def test_after_the_first_gate_the_card_alone_leads_back_to_the_spawn(monkeypatch):
    # No boss before gate 2, so there is nothing to choose after gate 1.
    screen = Screen(CARD)
    _, choice = _after_gate(monkeypatch, screen, gate=1, want_boss=False)
    assert choice == "continue"
    assert screen.pressed == ["card"]


def test_before_the_boss_gate_continue_is_pressed(monkeypatch):
    screen = Screen(CARD, BOTH)
    _, choice = _after_gate(monkeypatch, screen, gate=2, want_boss=False)
    assert choice == "continue"
    assert screen.pressed == ["card", BOSS_RUSH_CONTINUE_IMAGE]


def test_at_the_boss_gate_fight_boss_is_pressed(monkeypatch):
    screen = Screen(CARD, BOTH)
    _, choice = _after_gate(monkeypatch, screen, gate=4, want_boss=True)
    assert choice == "boss"
    assert screen.pressed == ["card", BOSS_RUSH_FIGHT_BOSS_IMAGE]


def test_the_buttons_may_come_before_the_card(monkeypatch):
    # The order the game shows them in must not matter: the card that
    # follows the choice is still taken before the run moves on.
    screen = Screen(BOTH, CARD)
    _, choice = _after_gate(monkeypatch, screen, gate=3, want_boss=False)
    assert choice == "continue"
    assert screen.pressed == [BOSS_RUSH_CONTINUE_IMAGE, "card"]


def test_the_wrong_button_is_never_pressed_when_the_right_one_does_not_match(monkeypatch):
    # Fight Boss wanted, but only Continue ever matches -- pressing it would
    # run gates the task didn't ask for.
    screen = Screen({BOSS_RUSH_CONTINUE_IMAGE})
    runner, choice = _after_gate(monkeypatch, screen, gate=3, want_boss=True)
    assert choice is None
    assert screen.pressed == []
    assert runner.screenshots == ["boss_rush_choice_not_found"]
    assert BOSS_RUSH_FIGHT_BOSS_IMAGE in runner.said


def test_a_button_rendering_a_beat_after_the_other_is_waited_for(monkeypatch):
    """Continue shows a poll before Fight Boss: that is a slow render, not a
    missing crop, and must not abandon the run."""
    runner = FakeRunner()
    monkeypatch.setattr(runner_boss_rush.time, "time", runner.clock.time)
    appears_at = runner.clock.now + 1.0
    pressed = []

    def find(hwnd, name, **kw):
        if pressed:
            return None
        if name == BOSS_RUSH_CONTINUE_IMAGE:
            return _match(name)
        if name == BOSS_RUSH_FIGHT_BOSS_IMAGE and runner.clock.now >= appears_at:
            return _match(name)
        return None

    monkeypatch.setattr(vision, "find_image", find)
    monkeypatch.setattr(vision, "click_match", lambda m, h, match, **k: pressed.append(match["name"]))
    assert runner._boss_rush_after_gate(1, threading.Event(), 2, want_boss=True) == "boss"
    assert pressed == [BOSS_RUSH_FIGHT_BOSS_IMAGE]


def test_a_later_gate_without_any_choice_gives_up_instead_of_walking_off(monkeypatch):
    # From gate 2 on a choice has to be made; a card alone is not the end.
    screen = Screen(CARD)
    runner, choice = _after_gate(monkeypatch, screen, gate=2, want_boss=False)
    assert choice is None
    assert runner.clock.now - 1000.0 >= BOSS_RUSH_POST_GATE_TIMEOUT
    assert runner.screenshots == ["boss_rush_after_gate_timeout"]


def test_stop_ends_the_post_gate_wait(monkeypatch):
    runner = FakeRunner()
    monkeypatch.setattr(runner_boss_rush.time, "time", runner.clock.time)
    monkeypatch.setattr(vision, "find_image", lambda *a, **k: None)
    stop = threading.Event()
    stop.set()
    assert runner._boss_rush_after_gate(1, stop, 2, want_boss=False) is None


# ── the run ────────────────────────────────────────────────────────────────

class RunRunner(FakeRunner):
    """FakeRunner with every step the run delegates recorded, not performed."""

    def __init__(self, gate_results=None, choices=None, entered=None):
        super().__init__()
        self.calls = []
        self.gate_results = list(gate_results or [])
        self.choices = list(choices or [])
        self.entered = list(entered or [])

    def _press_start_game(self, hwnd, stop_event, task, webhook=None):
        self.calls.append(("start", task.get("macro")))
        return True

    def _enter_boss_rush_gate(self, hwnd, stop_event, gate, route, sprint):
        self.calls.append(("enter", gate, route, sprint))
        return self.entered.pop(0) if self.entered else True

    def _run_prestart(self, hwnd, stop_event, task, default_walk_paths, first_repeat=True,
                      team_check=False):
        self.calls.append(("prestart", task.get("macro"), first_repeat, team_check))
        return True

    def _begin_battle(self, task):
        self.calls.append(("begin", task.get("macro")))
        return ["blocks for " + str(task.get("macro"))]

    def _wants_close_popup_watch(self, task):
        return False

    def _wait_for_match_result(self, hwnd, stop_event, battle_blocks=None, first_repeat=True,
                               macro_name=None, mode=None, watch_close_popup=False,
                               webhook=None, task=None, watch_gate_clear=False):
        self.calls.append(("battle", tuple(battle_blocks), watch_gate_clear))
        if not watch_gate_clear:
            return "win"
        return self.gate_results.pop(0) if self.gate_results else "gate_cleared"

    def _boss_rush_after_gate(self, hwnd, stop_event, gate, want_boss):
        self.calls.append(("after", gate, want_boss))
        if self.choices:
            return self.choices.pop(0)
        return "boss" if want_boss else "continue"

    def _find_start_game_button(self, hwnd, stop_event=None, timeout=0):
        return "nav_start_game", _match()

    def of(self, kind):
        return [c for c in self.calls if c[0] == kind]


def _run(runner, task, first_repeat=True):
    return runner._play_boss_rush_run(1, threading.Event(), task, {}, first_repeat=first_repeat)


def test_a_run_clears_the_gates_in_route_order_then_fights_the_boss():
    runner = RunRunner()
    task = _task(boss_after="3", routes=("g1", "g2", "g3", "g4"), gate_sprint=True,
                 boss_macro="Boss")
    assert _run(runner, task) == "win"
    assert runner.of("enter") == [("enter", 1, "g1", True), ("enter", 2, "g2", True),
                                  ("enter", 3, "g3", True)]
    assert runner.of("after") == [("after", 1, False), ("after", 2, False), ("after", 3, True)]
    # Spawn + one per gate + the boss.
    assert runner.of("start") == [("start", "Gates")] * 4 + [("start", "Boss")]


def test_units_are_placed_once_for_the_gates_and_again_for_the_boss():
    runner = RunRunner()
    _run(runner, _task(boss_after="4", routes=("a", "b", "c", "d"), boss_macro="Boss"))
    # Gate 1 places, gates 2-4 keep what is standing, the boss arena starts empty.
    assert runner.of("prestart") == [("prestart", "Gates", True, True),
                                     ("prestart", "Boss", True, True)]
    assert runner.of("begin") == [("begin", "Gates"), ("begin", "Boss")]


def test_the_battle_blocks_carry_on_from_gate_to_gate():
    runner = RunRunner()
    _run(runner, _task(boss_after="3"))
    battles = runner.of("battle")
    gate_battles = [b for b in battles if b[2]]
    assert len(gate_battles) == 3
    assert {b[1] for b in gate_battles} == {("blocks for Gates",)}, \
        "every gate ticks the same block list the first gate started"
    assert battles[-1] == ("battle", ("blocks for Gates",), False), \
        "the boss is a plain battle: no gate-clear watch"


def test_a_repeat_run_still_places_the_units_but_as_a_repeat():
    runner = RunRunner()
    _run(runner, _task(boss_after="2", routes=("a", "b")), first_repeat=False)
    assert runner.of("prestart") == [("prestart", "Gates", False, True),
                                     ("prestart", "Gates", False, True)]


def test_a_gate_lost_ends_the_run_on_its_defeat():
    runner = RunRunner(gate_results=["gate_cleared", "loss"])
    assert _run(runner, _task(boss_after="4", routes=("a", "b", "c", "d"))) == "loss"
    assert [c[1] for c in runner.of("enter")] == [1, 2]
    assert runner.of("after") == [("after", 1, False)]
    assert not any(c[2] is False for c in runner.of("battle")), "no boss fight after a loss"


def test_a_gate_that_cannot_be_entered_abandons_the_run():
    runner = RunRunner(entered=[True, False])
    assert _run(runner, _task(boss_after="3")) is None
    assert runner.of("after") == [("after", 1, False)]


def test_unresolved_post_gate_screens_abandon_the_run():
    runner = RunRunner(choices=["continue", None])
    assert _run(runner, _task(boss_after="3")) is None
    assert [c[1] for c in runner.of("enter")] == [1, 2]
    assert len(runner.of("prestart")) == 1, "never reaches the boss arena"


def test_stop_during_the_run_ends_it():
    runner = RunRunner()
    stop = threading.Event()
    stop.set()
    assert runner._play_boss_rush_run(1, stop, _task(), {}) is None
    assert runner.of("enter") == []


# ── wired into MacroRunner ─────────────────────────────────────────────────

def _macro_runner():
    runner = MacroRunner(MagicMock(), MagicMock(), MagicMock())
    runner._log = lambda *_a, **_k: None
    runner._set_status = lambda **_k: None
    return runner


def test_a_boss_rush_task_plays_a_whole_run_as_its_match():
    runner = _macro_runner()
    seen = []
    runner._play_boss_rush_run = lambda hwnd, stop, task, walks, first_repeat=True, webhook=None: (
        seen.append(first_repeat) or "win")
    runner._start_game_or_reset_via_settings = MagicMock(side_effect=AssertionError("not for Boss Rush"))
    result = runner._play_one_match(1, threading.Event(), {"mode": "boss_rush"}, {}, first_repeat=False)
    assert result == "win"
    assert seen == [False]


def test_a_task_the_preflight_refuses_never_leaves_the_lobby():
    runner = _macro_runner()
    runner._boss_rush_preflight = lambda task: False
    runner._run_task_setup = MagicMock(side_effect=AssertionError("must not navigate"))
    assert runner._run_task(1, threading.Event(), {"mode": "boss_rush", "map": MAP}, 1, 1,
                            {}, 1, 1, {}, None) is True


def test_boss_rush_always_starts_solo():
    runner = _macro_runner()
    runner._boss_rush_preflight = lambda task: True
    entered = []
    runner._run_task_setup = lambda hwnd, stop, task, *a, **k: entered.append(task) or False
    runner._recover_to_lobby = lambda hwnd, stop: False
    runner._run_task(1, threading.Event(),
                     {"mode": "boss_rush", "map": MAP, "play_mode": "matchmaking"},
                     1, 1, {}, 1, 1, {}, None)
    assert entered and entered[0]["play_mode"] == "solo"


def test_the_map_card_replaces_the_story_carousel(monkeypatch):
    runner = _macro_runner()
    monkeypatch.setattr(runner_module.vision, "find_image", lambda hwnd, name, **k: _match())
    runner._click_gamemode = lambda hwnd, stop, mode, wait_for_menu=True: mode == "boss_rush"
    picked = []
    runner._select_boss_rush_map = lambda hwnd, stop, name: picked.append(name) or True
    monkeypatch.setattr(runner_module.stage_select, "find_and_click_map",
                        MagicMock(side_effect=AssertionError("no Story carousel in Boss Rush")))
    assert runner._reach_map_selected(1, threading.Event(), MAP, "boss_rush", 1, 1) is True
    assert picked == [MAP]


def test_boss_rush_has_no_stage_row_or_difficulty_to_pick():
    runner = _macro_runner()
    runner._reach_map_selected = lambda *a, **k: True
    runner._select_stage = MagicMock(side_effect=AssertionError("no stage row"))
    runner._select_difficulty = MagicMock(side_effect=AssertionError("no difficulty"))
    runner._enter_selected_stage = lambda hwnd, stop, task, mode, coords, webhook=None: mode
    task = {"mode": "boss_rush", "map": MAP, "play_mode": "solo"}
    assert runner._run_task_setup(1, threading.Event(), task, "boss_rush", MAP, {}, 1, 1) == "boss_rush"


def test_the_gamemode_menu_finds_the_boss_rush_card(monkeypatch):
    runner = _macro_runner()
    monkeypatch.setattr(runner_module.time, "sleep", lambda _s: None)
    monkeypatch.setattr(runner_module.vision, "wait_for_image", lambda *a, **k: _match())
    runner._dismiss_party_overlay = lambda hwnd, stop: True
    looked_for = []
    runner._find_gamemode_card = lambda hwnd, stop, names, label: (
        looked_for.append(tuple(names)) or (_match(), names[0]))
    runner._click_gamemode_target = lambda hwnd, stop, label, click: True
    assert runner._click_gamemode(1, threading.Event(), "boss_rush") is True
    assert looked_for == [tuple(BOSS_RUSH_IMAGE_NAMES)]


def _battle_runner(monkeypatch, on_screen):
    runner = _macro_runner()
    runner._checkpoint = lambda _stop: False
    runner._tick_loop_phases = lambda *_a, **_k: None
    runner._infinite_wave_limit = lambda _task: None
    monkeypatch.setattr(runner_module.time, "sleep", lambda _s: None)
    monkeypatch.setattr(runner_module.vision, "find_image",
                        lambda hwnd, name, **k: _match(name) if name in on_screen else None)
    monkeypatch.setattr(runner_module.vision, "find_image_any",
                        lambda hwnd, names, **k: next(((_match(n), n) for n in names if n in on_screen),
                                                      (None, None)))
    return runner


def test_the_battle_loop_ends_a_gate_when_its_card_choice_comes_up(monkeypatch):
    # "victory" is on screen too so a broken gate check fails here as "win"
    # instead of polling until the match timeout.
    runner = _battle_runner(monkeypatch, {BOSS_RUSH_CARD_IMAGE, "victory"})
    assert runner._wait_for_match_result(1, threading.Event(), mode="boss_rush",
                                         watch_gate_clear=True) == "gate_cleared"


def test_the_boss_fight_does_not_watch_for_gate_screens(monkeypatch):
    # The boss ends on the ordinary Victory screen; a stray gate crop match
    # during it must not be read as another gate.
    runner = _battle_runner(monkeypatch, {BOSS_RUSH_CARD_IMAGE, "victory"})
    assert runner._wait_for_match_result(1, threading.Event(), mode="boss_rush") == "win"


def test_the_team_check_runs_on_a_repeat_when_asked(monkeypatch):
    """Gates and boss can use two Macro Operations with two teams, so every
    run has to switch between them -- not only the first."""
    runner = _macro_runner()
    runner._interruptible_sleep = lambda *_a, **_k: None
    runner._run_prestart_blocks = lambda *_a, **_k: None
    runner._team_loadout_key = lambda task: (2, "include")
    runner._last_applied_team_loadout = (1, "include")
    applied = []
    runner._apply_team_loadout = lambda hwnd, stop, task: applied.append(task) or True

    assert runner._run_prestart(1, threading.Event(), {}, {}, first_repeat=False) is True
    assert applied == [], "an ordinary repeat still skips it"
    assert runner._run_prestart(1, threading.Event(), {}, {}, first_repeat=False,
                                team_check=True) is True
    assert len(applied) == 1


def test_a_preset_warns_about_a_missing_boss_macro(monkeypatch):
    from core import task_presets
    from core import templates as tpl
    from main import Api

    monkeypatch.setattr(task_presets, "load_preset", lambda name: {"name": name, "found": True, "tasks": [
        {"mode": "boss_rush", "macro": "Gates", "boss_macro": "Boss"},
        # A leftover from before the task was switched away from Boss Rush
        # is not something the queue will run, so not worth a warning.
        {"mode": "story", "macro": "Gates", "boss_macro": "Stale"},
    ]})
    monkeypatch.setattr(tpl, "list_templates", lambda: ["Gates"])
    api = object.__new__(Api)
    api.push_log = lambda _message: None
    assert api.load_task_preset("Rush")["missing_macros"] == ["Boss"]


# ── the Task Builder and the runner have to agree ──────────────────────────

APP_JS = Path(__file__).resolve().parent.parent / "ui" / "app.js"


def _task_data_list(key):
    src = APP_JS.read_text(encoding="utf-8")
    block = re.search(r"boss_rush:\s*\{.*?" + key + r":\s*\[(.*?)\]", src, re.S)
    assert block, f"couldn't find TASK_DATA.boss_rush.{key} in ui/app.js"
    return [a or b for a, b in re.findall(r"'([^']+)'|\"([^\"]+)\"", block.group(1))]


def test_the_task_builders_maps_match_the_runner_constants():
    assert _task_data_list("maps") == list(BOSS_RUSH_MAP_ORDER)


def test_every_map_has_a_card_image():
    assert set(BOSS_RUSH_MAP_ORDER) == set(BOSS_RUSH_MAP_IMAGES)


def test_the_task_builders_boss_gates_are_the_ones_the_game_offers():
    assert _task_data_list("bossAfter") == [
        str(g) for g in range(BOSS_RUSH_MIN_BOSS_GATE, BOSS_RUSH_GATE_COUNT + 1)]


def test_the_ui_gate_count_matches_the_runner():
    src = APP_JS.read_text(encoding="utf-8")
    found = re.search(r"const BOSS_RUSH_GATE_COUNT\s*=\s*(\d+)", src)
    assert found and int(found.group(1)) == BOSS_RUSH_GATE_COUNT
