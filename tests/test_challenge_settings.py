import main


def _api(logs=None):
    api = main.Api.__new__(main.Api)
    api.push_log = (logs if logs is not None else []).append
    return api


def _state(macros=None, *, enabled=False, daily_enabled=False):
    macros = macros or {}
    return {
        "challenge": {
            "enabled": enabled,
            "play_mode": "solo",
            "daily": {
                "enabled": daily_enabled,
                "last_completed_period": "",
            },
            "stages": {
                slot: {"enabled": True, "count": 0, "last_played_at": 0}
                for slot in main.CHALLENGE_STAGE_SLOTS
            },
            "maps": {
                name: {"macro": macros.get(name, "")}
                for name in main.CHALLENGE_STORY_MAPS
            },
            "last_reset_date": "2026-07-29",
            "reset_schedule": main.CHALLENGE_RESET_SCHEDULE,
        }
    }


def _modern_template(_name):
    return {"blocks": {"prestart": [], "battle": []}}


def _patch_settings(monkeypatch, state):
    monkeypatch.setattr(main.cfg, "load", lambda: state)
    monkeypatch.setattr(main.cfg, "update", lambda patch: state.update(patch))
    monkeypatch.setattr(
        main, "_current_challenge_reset_period", lambda now=None: "2026-07-29")


def test_challenge_settings_report_incomplete_story_map_setup(monkeypatch):
    macros = {
        name: f"{name} Farm"
        for name in main.CHALLENGE_STORY_MAPS[:-1]
    }
    state = _state(macros)
    _patch_settings(monkeypatch, state)
    monkeypatch.setattr(main.tpl, "template_exists", lambda _name: True)
    monkeypatch.setattr(main.tpl, "load_template", _modern_template)

    result = _api().get_challenge_settings()

    assert result["setup_ready"] is False
    assert result["missing_maps"] == [main.CHALLENGE_STORY_MAPS[-1]]
    assert result["invalid_maps"] == []


def test_regular_challenge_cannot_enable_until_every_map_has_a_macro(monkeypatch):
    state = _state()
    _patch_settings(monkeypatch, state)
    logs = []
    api = _api(logs)

    result = api.set_challenge_enabled(True)

    assert result["ok"] is False
    assert result["reason"] == "incomplete_challenge_maps"
    assert state["challenge"]["enabled"] is False
    assert any("Auto Challenge was not enabled" in message for message in logs)


def test_daily_challenge_cannot_enable_until_every_map_has_a_macro(monkeypatch):
    state = _state()
    _patch_settings(monkeypatch, state)
    logs = []
    api = _api(logs)

    result = api.set_daily_challenge_enabled(True)

    assert result["ok"] is False
    assert result["reason"] == "incomplete_challenge_maps"
    assert state["challenge"]["daily"]["enabled"] is False
    assert any("Daily Challenge was not enabled" in message for message in logs)


def test_clearing_a_challenge_map_disables_both_challenge_modes(monkeypatch):
    macros = {
        name: f"{name} Farm"
        for name in main.CHALLENGE_STORY_MAPS
    }
    state = _state(macros, enabled=True, daily_enabled=True)
    _patch_settings(monkeypatch, state)
    monkeypatch.setattr(main.tpl, "template_exists", lambda _name: True)
    monkeypatch.setattr(main.tpl, "load_template", _modern_template)

    result = _api().set_challenge_map_macro("School Grounds", "")

    assert result["ok"] is True
    assert result["auto_disabled"] is True
    assert state["challenge"]["enabled"] is False
    assert state["challenge"]["daily"]["enabled"] is False
    assert result["missing_maps"] == ["School Grounds"]


# ---------------------------------------------------------------------------
# World Boss: Events > World Boss > Ancient One, once per clock hour
# ---------------------------------------------------------------------------

_HOUR = 1_790_002_800  # a full hour (divisible by 3600)


def _boss_state(*, enabled=False, macro="", last_played_at=0):
    state = _state()
    state["challenge"]["world_boss"] = {
        "enabled": enabled, "macro": macro, "last_played_at": last_played_at}
    return state


def _patch_boss(monkeypatch, state, *, crops=True, macro_ok=True, now=_HOUR + 120):
    from core import vision
    _patch_settings(monkeypatch, state)
    monkeypatch.setattr(main.time, "time", lambda: now)
    monkeypatch.setattr(vision, "template_variant_paths",
                        lambda name, *_a, **_k: [f"{name}.png"] if crops else [])
    monkeypatch.setattr(main.tpl, "template_exists", lambda _name: macro_ok)
    monkeypatch.setattr(main.tpl, "load_template", _modern_template)


def test_the_world_boss_starts_off_and_ready(monkeypatch):
    state = _state()  # saved before the World Boss existed
    _patch_boss(monkeypatch, state)

    boss = _api().get_challenge_settings()["world_boss"]

    assert boss["enabled"] is False
    assert boss["ready"] is True
    assert boss["setup_problems"] == ["assign a Macro Operation"]


def test_the_world_boss_rests_until_the_next_full_hour(monkeypatch):
    state = _boss_state(last_played_at=_HOUR + 60)
    _patch_boss(monkeypatch, state)
    assert _api().get_challenge_settings()["world_boss"]["ready"] is False

    state = _boss_state(last_played_at=_HOUR - 60)  # played in the hour before
    _patch_boss(monkeypatch, state)
    assert _api().get_challenge_settings()["world_boss"]["ready"] is True


def test_the_world_boss_names_what_its_setup_still_needs(monkeypatch):
    state = _boss_state()
    _patch_boss(monkeypatch, state, crops=False)

    problems = _api().get_challenge_settings()["world_boss"]["setup_problems"]

    assert problems[0] == "assign a Macro Operation"
    assert any("world_boss_ancient_one" in p for p in problems)
    assert any("world_boss_enter_encounter" in p for p in problems)


def test_the_world_boss_cannot_be_switched_on_until_it_is_set_up(monkeypatch):
    state = _boss_state(macro="Boss Farm")
    _patch_boss(monkeypatch, state, crops=False)
    logs = []

    result = _api(logs).set_world_boss_enabled(True)

    assert result["ok"] is False
    assert result["reason"] == "world_boss_setup"
    assert state["challenge"]["world_boss"]["enabled"] is False
    assert any("World Boss was not enabled" in message for message in logs)


def test_the_world_boss_switches_on_once_it_is_set_up(monkeypatch):
    state = _boss_state(macro="Boss Farm")
    _patch_boss(monkeypatch, state)

    assert _api().set_world_boss_enabled(True) == {"ok": True}
    assert state["challenge"]["world_boss"]["enabled"] is True


def test_playing_the_world_boss_uses_up_its_hour(monkeypatch):
    state = _boss_state(enabled=True, macro="Boss Farm")
    _patch_boss(monkeypatch, state)
    api = _api()

    assert api.mark_challenge_stage_played("world_boss") == {"ok": True}

    boss = api.get_challenge_settings()["world_boss"]
    assert boss["last_played_at"] == _HOUR + 120
    assert (boss["state"], boss["ready"]) == ("done", False)


def test_an_hour_not_played_in_time_is_closed_not_done(monkeypatch):
    """Enter Encounter only works for 10 minutes after the full hour. Setting
    out at :09 at the latest still lands inside them; later, the hour is
    simply missed -- shown as closed, not as played."""
    last_start = _HOUR + main.WORLD_BOSS_SET_OUT_SECONDS - 1
    for now, state in ((_HOUR, "ready"), (last_start, "ready"),
                       (last_start + 1, "closed"), (_HOUR + 3599, "closed")):
        _patch_boss(monkeypatch, _boss_state(), now=now)
        boss = _api().get_challenge_settings()["world_boss"]
        assert (boss["state"], boss["ready"]) == (state, state == "ready"), now - _HOUR


def test_the_hour_can_be_marked_done_or_cleared_by_hand(monkeypatch):
    state = _boss_state()
    _patch_boss(monkeypatch, state)
    api = _api()

    api.set_world_boss_count(1)
    assert api.get_challenge_settings()["world_boss"]["state"] == "done"
    api.set_world_boss_count(0)
    assert api.get_challenge_settings()["world_boss"]["state"] == "ready"
    assert api.set_world_boss_count(5)["ok"] is False


def test_clearing_the_world_boss_macro_switches_it_off(monkeypatch):
    state = _boss_state(enabled=True, macro="Boss Farm")
    _patch_boss(monkeypatch, state)

    result = _api().set_world_boss_macro("")

    assert result == {"ok": True, "auto_disabled": True}
    assert state["challenge"]["world_boss"]["enabled"] is False
    assert state["challenge"]["world_boss"]["macro"] == ""


def test_resetting_challenge_status_frees_the_world_boss_hour(monkeypatch):
    state = _boss_state(last_played_at=_HOUR + 60)
    _patch_boss(monkeypatch, state)
    api = _api()

    api.reset_challenge_counts()

    assert api.get_challenge_settings()["world_boss"]["ready"] is True


def test_time_until_challenge_counts_the_world_boss(monkeypatch):
    monkeypatch.setattr(main.time, "time", lambda: _HOUR + 600)

    assert main._time_until_challenge_ready({"world_boss": {"enabled": True, "ready": True}}) == "Ready"
    assert main._time_until_challenge_ready({"world_boss": {"enabled": True, "ready": False}}) == "50:00"
    assert main._time_until_challenge_ready({"world_boss": {"enabled": False}}) == "No stages enabled"


def test_the_world_boss_alone_counts_as_challenge_enabled():
    assert main._any_challenge_enabled({"world_boss": {"enabled": True}}) is True
    assert main._any_challenge_enabled({"world_boss": {"enabled": False}}) is False
