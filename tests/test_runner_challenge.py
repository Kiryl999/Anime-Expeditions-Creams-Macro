import threading

import numpy as np
import pytest

from core import ocr
from core import vision
from core import ocr_windows
from core import runner_challenge
from core.runner_challenge import ChallengeOps
from core.runner_constants import CHALLENGE_STORY_MAPS


class ChallengeProbe:
    def __init__(self):
        self.logs = []
        self.debug_calls = []

    def _debug_save(self, hwnd, name, match):
        self.debug_calls.append((hwnd, name, match))
        return None

    def _log(self, message):
        self.logs.append(message)


def test_detect_current_challenge_map_uses_ordered_candidate_search(monkeypatch):
    """Challenge map detection delegates its ordered alternatives to vision."""
    probe = ChallengeProbe()
    match = {"score": 0.95}
    calls = []

    def find_image_any(hwnd, names):
        calls.append((hwnd, names))
        return match, "King's Tomb"

    monkeypatch.setattr(vision, "find_image_any", find_image_any)

    detected = ChallengeOps._detect_current_challenge_map(probe, 123)

    assert detected == "King's Tomb"
    assert calls == [(123, CHALLENGE_STORY_MAPS)]
    assert probe.debug_calls == [(123, "King's Tomb", match)]


def test_detect_current_challenge_map_handles_missing_templates(monkeypatch):
    """Missing challenge templates remain a non-fatal detection miss."""
    probe = ChallengeProbe()

    def find_image_any(hwnd, names):
        raise vision.TemplateNotFound("missing")

    monkeypatch.setattr(vision, "find_image_any", find_image_any)

    assert ChallengeOps._detect_current_challenge_map(probe, 123) is None


def test_daily_challenge_counts_as_ready_without_regular_challenge():
    probe = ChallengeProbe()
    probe._get_challenge_settings = lambda: {
        "enabled": False,
        "daily": {"enabled": True, "ready": True},
    }

    assert ChallengeOps._challenge_has_ready_stage(probe) is True


class DailyEntryProbe(ChallengeProbe):
    def __init__(self):
        super().__init__()
        self.clicked = []
        self._open_challenge_screen = lambda *_args: True
        self._set_status = lambda **_kwargs: None
        self._checkpoint = lambda _stop: False
        self._recover_to_lobby = lambda *_args: True
        self._enter_selected_challenge = lambda *_args, **_kwargs: True

    def _click_found_image(self, _hwnd, name, _timeout, _stop, *args, **kwargs):
        self.clicked.append(name)
        return {"score": 0.99}


def test_daily_challenge_clicks_tab_then_stage_card(monkeypatch):
    probe = DailyEntryProbe()
    monkeypatch.setattr(vision, "find_image", lambda *_args, **_kwargs: None)

    result = ChallengeOps._enter_daily_challenge_stage(
        probe, 123, threading.Event(), "solo", {}, {})

    assert result == "entered"
    assert probe.clicked == ["daily_challenge_available", "daily_challenge_stage"]


def test_daily_challenge_unavailable_returns_to_lobby_without_clicking(monkeypatch):
    probe = DailyEntryProbe()
    monkeypatch.setattr(
        vision, "find_image",
        lambda *_args, **_kwargs: {"score": 0.98},
    )

    result = ChallengeOps._enter_daily_challenge_stage(
        probe, 123, threading.Event(), "solo", {}, {})

    assert result == "unavailable"
    assert probe.clicked == []


def test_daily_challenge_unavailable_marks_current_game_day_complete():
    probe = ChallengeProbe()
    marked = []
    probe._get_challenge_settings = lambda: {
        "enabled": False,
        "play_mode": "solo",
        "daily": {"enabled": True, "ready": True},
    }
    probe._run_one_daily_challenge = lambda *_args: "unavailable"
    probe._checkpoint = lambda _stop: False
    probe._mark_challenge_stage_played = lambda stage: marked.append(stage)

    ChallengeOps._run_challenges(probe, 123, threading.Event(), {}, {}, {})

    assert marked == ["daily"]


def test_regular_challenge_finishes_slots_1_2_3_in_one_ordered_pass():
    probe = ChallengeProbe()
    played = []
    marked = []
    reads = 0

    def settings():
        nonlocal reads
        reads += 1
        # Simulate live state changing after slot 1. The pass must retain
        # the work it accepted at entry instead of returning to the task.
        ready = reads == 1
        return {
            "enabled": True,
            "play_mode": "solo",
            "daily": {"enabled": False, "ready": False},
            "cap": 0,
            "stages": {
                slot: {"enabled": True, "ready": ready, "count": 0}
                for slot in ("1", "2", "3")
            },
        }

    probe._get_challenge_settings = settings
    probe._checkpoint = lambda _stop: False
    probe._run_one_challenge_stage = (
        lambda _hwnd, _stop, slot, *_args: played.append(slot) or "win")
    probe._mark_challenge_stage_played = lambda slot: marked.append(slot)

    ChallengeOps._run_challenges(probe, 123, threading.Event(), {}, {}, {})

    assert played == ["1", "2", "3"]
    assert marked == ["1", "2", "3"]


@pytest.mark.parametrize(
    ("ocr_text", "expected"),
    (
        ("Grands - Act 1", "School Grounds"),
        ("Kingdm - Act 1", "Rose Kingdom"),
        ("Fary King Forest", "Fairy King Forest"),
        ("Tornb - Act 1", "King's Tomb"),
        ("Flovver Forest", "Flower Forest"),
        ("Eest Town - Act 1", "East Town"),
        ("Crirnson Shore - Act 2", "Crimson Shore"),
        ("Flarning Monastery - Act 1", "Flaming Monastery"),
        ("Flamlng Monaslery - Act 2", "Flaming Monastery"),
        ("Mcnastery", "Flaming Monastery"),
    ),
)
def test_challenge_map_ocr_uses_unique_map_words(monkeypatch, ocr_text, expected):
    probe = ChallengeProbe()
    frame = np.zeros((756, 1152, 3), dtype=np.uint8)
    monkeypatch.setattr(vision, "capture_game_bgr", lambda _hwnd: frame)
    monkeypatch.setattr(
        vision,
        "find_in_gray_multiscale",
        lambda *_args, **_kwargs: {"x": 895, "y": 348, "w": 123, "h": 21},
    )
    monkeypatch.setattr(ocr, "get_pytesseract", lambda: (_ for _ in ()).throw(ocr.TesseractNotAvailable()))
    monkeypatch.setattr(ocr, "ocr_mask", lambda _engine, _image, _config: ocr_text)

    assert ChallengeOps._detect_challenge_map_ocr(probe, 123) == expected


def test_challenge_map_ocr_does_not_guess_from_shared_forest_word(monkeypatch):
    probe = ChallengeProbe()
    frame = np.zeros((756, 1152, 3), dtype=np.uint8)
    monkeypatch.setattr(vision, "capture_game_bgr", lambda _hwnd: frame)
    monkeypatch.setattr(
        vision,
        "find_in_gray_multiscale",
        lambda *_args, **_kwargs: {"x": 895, "y": 348, "w": 123, "h": 21},
    )
    monkeypatch.setattr(ocr, "get_pytesseract", lambda: (_ for _ in ()).throw(ocr.TesseractNotAvailable()))
    monkeypatch.setattr(ocr, "ocr_mask", lambda _engine, _image, _config: "Forest - Act 1")

    assert ChallengeOps._detect_challenge_map_ocr(probe, 123) is None


def test_challenge_map_ocr_uses_hud_crop_before_fixed_fallback(monkeypatch):
    probe = ChallengeProbe()
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    seen_shapes = []
    monkeypatch.setattr(vision, "capture_game_bgr", lambda _hwnd: frame)
    monkeypatch.setattr(
        vision,
        "find_in_gray_multiscale",
        lambda *_args, **_kwargs: {"x": 100, "y": 20, "w": 20, "h": 10},
    )
    monkeypatch.setattr(ocr, "get_pytesseract", lambda: (_ for _ in ()).throw(ocr.TesseractNotAvailable()))

    def fake_ocr(_engine, image, _config):
        seen_shapes.append(image.shape[:2])
        return "School Grounds"

    monkeypatch.setattr(ocr, "ocr_mask", fake_ocr)

    assert ChallengeOps._detect_challenge_map_ocr(probe, 123) == "School Grounds"
    assert seen_shapes[0] == (43 * 8, 85 * 8)


def test_challenge_map_ocr_uses_fixed_fallback_when_hud_absent(monkeypatch):
    probe = ChallengeProbe()
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    seen_shapes = []
    monkeypatch.setattr(vision, "capture_game_bgr", lambda _hwnd: frame)
    monkeypatch.setattr(vision, "find_in_gray_multiscale", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ocr, "get_pytesseract", lambda: (_ for _ in ()).throw(ocr.TesseractNotAvailable()))

    def fake_ocr(_engine, image, _config):
        seen_shapes.append(image.shape[:2])
        return "Rose Kingdom"

    monkeypatch.setattr(ocr, "ocr_mask", fake_ocr)

    assert ChallengeOps._detect_challenge_map_ocr(probe, 123) == "Rose Kingdom"
    assert seen_shapes[0] == (10 * 8, 81 * 8)


# ---------------------------------------------------------------------------
# World Boss: Events > World Boss > Ancient One, once per clock hour
# ---------------------------------------------------------------------------

def _boss_settings(**boss):
    return {
        "enabled": False, "play_mode": "solo", "cap": 0,
        "daily": {"enabled": False, "ready": False},
        "world_boss": {"enabled": True, "ready": True, "macro": "Boss Farm", "setup_problems": [], **boss},
    }


def test_a_due_world_boss_counts_as_a_ready_challenge():
    probe = ChallengeProbe()
    probe._get_challenge_settings = lambda: _boss_settings()

    assert ChallengeOps._challenge_has_ready_stage(probe) is True


@pytest.mark.parametrize("boss", [
    {"enabled": False},
    {"ready": False},
    # Without its crops or macro it cannot get in -- pulling the task out of
    # its stage for it at every repeat would only waste the run.
    {"setup_problems": ["assign a Macro Operation"]},
])
def test_a_world_boss_that_cannot_run_leaves_the_task_alone(boss):
    probe = ChallengeProbe()
    probe._get_challenge_settings = lambda: _boss_settings(**boss)

    assert ChallengeOps._challenge_has_ready_stage(probe) is False


def _pass_probe(settings, outcome):
    probe = ChallengeProbe()
    probe.order = []
    probe.marked = []
    probe.recovered = []
    probe._get_challenge_settings = lambda: settings
    probe._checkpoint = lambda stop: stop.is_set()
    probe._run_one_daily_challenge = lambda *_a: probe.order.append("daily") or "win"
    probe._run_one_world_boss = lambda *_a: probe.order.append("world_boss") or outcome
    probe._run_one_challenge_stage = lambda _hwnd, _stop, slot, *_a: probe.order.append(slot) or "win"
    probe._mark_challenge_stage_played = lambda stage, *_a: probe.marked.append(stage)
    probe._recover_failed_challenge = lambda *_a: probe.recovered.append(True) or True
    probe._run_world_boss_hour = lambda *a: ChallengeOps._run_world_boss_hour(probe, *a)
    probe._world_boss_still_due = lambda: ChallengeOps._world_boss_still_due(probe)
    return probe


def test_the_world_boss_runs_after_daily_and_before_the_regular_slots():
    settings = {
        **_boss_settings(),
        "enabled": True,
        "daily": {"enabled": True, "ready": True},
        "stages": {"1": {"enabled": True, "ready": True, "count": 0}},
    }
    probe = _pass_probe(settings, "win")

    ChallengeOps._run_challenges(probe, 123, threading.Event(), {}, {}, {})

    assert probe.order == ["daily", "world_boss", "1"]
    assert probe.marked == ["daily", "world_boss", "1"]


@pytest.mark.parametrize("outcome", ["win", "loss", "left"])
def test_a_played_world_boss_rests_until_the_next_hour(outcome):
    probe = _pass_probe(_boss_settings(), outcome)

    ChallengeOps._run_challenges(probe, 123, threading.Event(), {}, {}, {})

    assert probe.order == ["world_boss"]
    assert probe.marked == ["world_boss"]
    assert probe.recovered == []


def test_a_failed_world_boss_goes_back_to_the_lobby_and_tries_again():
    """A click in the Events menu that didn't register must not cost the hour."""
    probe = _pass_probe(_boss_settings(), None)
    outcomes = iter([None, "win"])
    probe._run_one_world_boss = lambda *_a: probe.order.append("world_boss") or next(outcomes)

    ChallengeOps._run_challenges(probe, 123, threading.Event(), {}, {}, {})

    assert probe.order == ["world_boss", "world_boss"]
    assert probe.recovered == [True]
    assert probe.marked == ["world_boss"]


def test_the_world_boss_gives_up_for_the_hour_after_its_last_try():
    """And then rests: left ready, it would pull the task out of its stage
    at every repeat boundary until the hour ends."""
    from core.runner_constants import WORLD_BOSS_ATTEMPTS

    probe = _pass_probe(_boss_settings(), None)

    ChallengeOps._run_challenges(probe, 123, threading.Event(), {}, {}, {})

    assert probe.order == ["world_boss"] * WORLD_BOSS_ATTEMPTS
    assert probe.recovered == [True] * WORLD_BOSS_ATTEMPTS
    assert probe.marked == ["world_boss"]


def test_a_failed_world_boss_is_not_retried_once_its_window_closed():
    settings = _boss_settings()
    probe = _pass_probe(settings, None)
    # Past :09 by the time it is back in the lobby.
    probe._recover_failed_challenge = lambda *_a: settings["world_boss"].update(ready=False) or True

    ChallengeOps._run_challenges(probe, 123, threading.Event(), {}, {}, {})

    assert probe.order == ["world_boss"]
    assert probe.marked == ["world_boss"]


def test_a_world_boss_that_cannot_get_back_to_the_lobby_ends_the_pass():
    settings = {**_boss_settings(), "enabled": True,
                "stages": {"1": {"enabled": True, "ready": True, "count": 0}}}
    probe = _pass_probe(settings, None)
    probe._recover_failed_challenge = lambda *_a: False

    ChallengeOps._run_challenges(probe, 123, threading.Event(), {}, {}, {})

    assert probe.order == ["world_boss"]
    assert probe.marked == ["world_boss"]


def test_a_world_boss_missing_its_setup_is_skipped_with_the_reason():
    problem = 'crop "world_boss_ancient_one" in the Image Manager'
    probe = _pass_probe(_boss_settings(setup_problems=[problem]), "win")

    ChallengeOps._run_challenges(probe, 123, threading.Event(), {}, {}, {})

    assert probe.order == []
    assert probe.marked == []
    assert any(problem in line for line in probe.logs)


def test_a_stop_during_the_world_boss_does_not_use_up_its_hour():
    stop = threading.Event()
    probe = _pass_probe(_boss_settings(), None)
    probe._run_one_world_boss = lambda *_a: stop.set() or None

    ChallengeOps._run_challenges(probe, 123, stop, {}, {}, {})

    assert probe.marked == []


class WorldBossEntryProbe(ChallengeProbe):
    def __init__(self, missing=None):
        super().__init__()
        self.clicked = []
        self.backs = 0
        self.entered = []
        self.missing = missing
        self._ensure_lobby = lambda *_args: True
        self._set_status = lambda **_kwargs: None
        self._checkpoint = lambda _stop: False

    def _click_found_image(self, _hwnd, name, _timeout, _stop, *args, **kwargs):
        self.clicked.append(name)
        return None if name == self.missing else {"score": 0.99}

    def _spam_back_until_gone(self, *_args):
        self.backs += 1

    def _enter_selected_stage(self, _hwnd, _stop, task, mode, _coords, _webhook):
        self.entered.append((task, mode))
        return True


def test_the_world_boss_is_entered_through_the_events_menu(monkeypatch):
    monkeypatch.setattr(runner_challenge.time, "sleep", lambda _s: None)
    probe = WorldBossEntryProbe()

    assert ChallengeOps._enter_world_boss(probe, 123, threading.Event(), {}, {}) is True
    assert probe.clicked == ["nav_event", "world_boss_ancient_one", "world_boss_enter_encounter"]
    # Then Select Stage and Start, the same Solo tail every stage uses.
    assert probe.entered == [({"mode": "world_boss", "play_mode": "solo"}, "world_boss")]


def test_a_world_boss_screen_that_never_shows_backs_out_to_the_lobby(monkeypatch):
    monkeypatch.setattr(runner_challenge.time, "sleep", lambda _s: None)
    probe = WorldBossEntryProbe(missing="world_boss_enter_encounter")

    assert ChallengeOps._enter_world_boss(probe, 123, threading.Event(), {}, {}) is False
    assert probe.backs == 1
    assert probe.entered == []


class WorldBossBattleProbe(ChallengeProbe):
    def __init__(self, outcome):
        super().__init__()
        self.played = []
        self.handled = []
        self.finished = []
        self._outcome = outcome
        self._set_status = lambda **_kwargs: None
        self._checkpoint = lambda _stop: False
        self._enter_world_boss = lambda *_args: True
        self._send_progress_webhook = lambda *_args, **_kwargs: None
        self._send_challenge_progress_finished = lambda *args: self.finished.append(args[4])
        self._format_duration = lambda _seconds: "1m"

    def _play_one_match(self, _hwnd, _stop, task, _walks, first_repeat=True, webhook=None):
        self.played.append((task, first_repeat))
        return self._outcome

    def _handle_match_result(self, _hwnd, _stop, _task, result, _duration, _webhook, repeat):
        self.handled.append((result, repeat))
        return True


def test_the_world_boss_is_played_with_its_own_macro_and_left_afterwards():
    probe = WorldBossBattleProbe("win")

    result = ChallengeOps._run_one_world_boss(
        probe, 123, threading.Event(), {"macro": "Boss Farm"}, {}, {}, {})

    assert result == "win"
    task, first_repeat = probe.played[0]
    assert (task["mode"], task["map"], task["macro"], task["play_mode"]) == (
        "world_boss", "Ancient One", "Boss Farm", "solo")
    assert first_repeat is True, "a fresh entry: camera, Team Loadout and Once blocks all run"
    assert probe.handled == [("win", False)], "Leave Stage, back to the lobby"
    assert probe.finished == ["win"]


def test_leaving_the_world_boss_early_skips_the_result_screen():
    probe = WorldBossBattleProbe("left")

    result = ChallengeOps._run_one_world_boss(
        probe, 123, threading.Event(), {"macro": "Boss Farm"}, {}, {}, {})

    assert result == "left"
    assert probe.handled == []


def test_both_world_boss_crops_ship():
    from pathlib import Path

    from core.runner_constants import WORLD_BOSS_ENTRY_IMAGES

    root = Path(__file__).resolve().parent.parent / "Assets" / "ui"
    for name in WORLD_BOSS_ENTRY_IMAGES:
        assert (root / name / f"{name}.png").is_file(), f"{name} has no crop to find the World Boss by"
