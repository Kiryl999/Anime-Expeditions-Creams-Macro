"""Guards for which tasks watch for a full-screen "Click anywhere to close".

The panel covers the whole screen, Victory included, so a task that can hit
one and does not watch for it does not fail loudly -- it polls a hidden
result screen until MATCH_RESULT_TIMEOUT and loses the run. The watch is
gated (one extra image search per poll tick) so the gate itself is the thing
worth pinning down: it was hardcoded to Spirit City Act 3 on the assumption
that its boss intro was the only such panel, until Snowy Castle Act 3's
"Iron Wolf" secret-unit reveal turned up doing the same thing.
"""
import pytest

from core.runner import MacroRunner
from core import runner_constants as rc


@pytest.mark.parametrize("map_name", rc.CLOSE_POPUP_RAID_MAPS)
def test_every_listed_raid_map_watches_on_its_act_3(map_name):
    task = {"mode": "raid", "map": map_name, "stage": rc.CLOSE_POPUP_RAID_STAGE}

    assert MacroRunner._wants_close_popup_watch(task)


def test_snowy_castle_act_3_is_covered():
    """The case this gate was widened for -- Iron Wolf can drop at any point
    in the round, so the panel is not tied to a fixed moment in the fight the
    way Spirit City's cutscene is."""
    assert MacroRunner._wants_close_popup_watch(
        {"mode": "raid", "map": "Snowy Castle", "stage": "3"})


@pytest.mark.parametrize("stage", ["1", "2"])
@pytest.mark.parametrize("map_name", rc.CLOSE_POPUP_RAID_MAPS)
def test_the_other_acts_of_those_maps_do_not_watch(map_name, stage):
    """Only Act 3 throws the panel, and the watch costs a search per poll."""
    assert not MacroRunner._wants_close_popup_watch(
        {"mode": "raid", "map": map_name, "stage": stage})


@pytest.mark.parametrize("task", [
    {"mode": "story", "map": "Crimson Shore", "stage": "3"},
    {"mode": "raid", "map": "Some Future Raid", "stage": "3"},
    {"mode": "portal", "map": "Summer Portal", "stage": "3"},
    {"mode": "raid", "map": "Spirit City"},          # no stage at all
    {},
])
def test_unlisted_tasks_do_not_watch(task):
    assert not MacroRunner._wants_close_popup_watch(task)


def test_an_integer_stage_still_matches():
    """Task stages arrive as strings from the UI, but a task built in a test
    or migrated from older saved data can carry an int -- the gate compares
    str(stage) so both read the same."""
    assert MacroRunner._wants_close_popup_watch(
        {"mode": "raid", "map": "Spirit City", "stage": 3})


def test_listed_maps_are_real_raid_maps():
    """A typo here disables the watch silently: the name has to match the
    task's `map` value, which comes from TASK_DATA.raid.maps in ui/app.js."""
    import re
    from pathlib import Path

    app_js = (Path(__file__).resolve().parent.parent / "ui" / "app.js").read_text(encoding="utf-8")
    match = re.search(r"raid:\s*\{.*?maps:\s*\[(.*?)\]", app_js, re.S)
    assert match, "couldn't find TASK_DATA.raid.maps in ui/app.js"
    raid_maps = [a or b for a, b in re.findall(r"'([^']*)'|\"([^\"]*)\"", match.group(1))]

    assert set(rc.CLOSE_POPUP_RAID_MAPS) <= set(raid_maps)


def test_the_watched_stage_is_a_real_act():
    assert rc.CLOSE_POPUP_RAID_STAGE in rc.ACT_ORDER
