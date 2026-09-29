"""What happens to a fish after it is caught.

A catch does not pay out by itself: it sits in one of the six fish-inventory
slots until it is dealt with, and six full slots take no further catch -- so a
row left standing quietly ends fishing for the rest of the round. Wanted fish
pay out on a single left-click; unwanted ones have to be dragged onto the bin
right of slot 6. Neither raises a dialog.

The asymmetry is what these pin down: clicking a fish that turns out to be
junk costs nothing, dragging one that pays throws the money away. Every
tie-break here leans that way.
"""
from pathlib import Path

import pytest

import core.runner as runner_module
from core import config
from core.runner import MacroRunner
from core.runner_constants import (
    DEFAULT_COORDS, FISH_CHECK_INTERVAL, FISH_SLOT_BOX, FISH_SLOT_COUNT,
    FISH_UNWANTED_IMAGE, FISH_WANTED_IMAGE,
)

# The row is picked per setup (Settings > Debug > Macro Coordinates), so the
# tests pick one too rather than leaning on a default -- there is none.
SLOT_1 = (420, 700)
STEP = 62
TRASH = (SLOT_1[0] + FISH_SLOT_COUNT * STEP, SLOT_1[1])

# Taken before any test stubs it, for the tests that run the real search.
REAL_FIND_IMAGE = runner_module.vision.find_image
UI_DIR = Path(__file__).resolve().parent.parent / "Assets" / "ui"


def _shipped_crops():
    """(folder name, path) for every crop in both fish folders."""
    return [(name, path) for name in (FISH_WANTED_IMAGE, FISH_UNWANTED_IMAGE)
            for path in sorted((UI_DIR / name).glob("*.png"))]


def _crop_gray(path):
    """A crop exactly as the matcher loads it."""
    return runner_module.vision._load_gray_from_path(str(path))[0]


def _runner(monkeypatch, slots=(), missing=(), coords=None):
    """A runner whose fish inventory holds `slots`.

    `slots` is one entry per slot, 0-based: "wanted", "unwanted" or None for
    an empty slot. `missing` names image folders that have no crop yet.
    `coords` overrides the picked row.
    """
    runner = object.__new__(MacroRunner)
    runner.events = []
    runner.logged = []
    runner.regions = []
    runner._coords = {**DEFAULT_COORDS,
                      "fish_slot_x": SLOT_1[0], "fish_slot_y": SLOT_1[1],
                      "fish_slot_step": STEP,
                      **(coords or {})}
    runner._reset_fishing_for_match()
    runner._log = lambda message: runner.logged.append(message)
    runner._set_status = lambda **kw: None
    mouse = type("Mouse", (), {})()
    mouse.click = lambda x, y, **k: runner.events.append(("click", x, y))
    mouse.drag = lambda x1, y1, x2, y2, **k: runner.events.append(("drag", x1, y1, x2, y2))
    runner._mouse = mouse

    def look(hwnd, name, region=None, **k):
        runner.regions.append((name, region))
        if name in missing:
            raise runner_module.vision.TemplateNotFound("no {} crop.".format(name))
        index = (region[0] + FISH_SLOT_BOX[0] // 2 - runner._coords["fish_slot_x"]) // STEP
        held = slots[index] if index < len(slots) else None
        if held is None or held + "_fish" != name:
            return None
        return {"score": 0.95, "cx": region[0] + region[2] // 2, "cy": region[1] + region[3] // 2}

    monkeypatch.setattr(runner_module.vision, "find_image", look)
    monkeypatch.setattr(runner_module.vision, "ref_to_screen",
                        lambda hwnd, x, y: (int(x), int(y)))
    monkeypatch.setattr(runner_module.time, "sleep", lambda seconds: None)
    return runner


def _clock(monkeypatch, start=1000.0):
    now = [start]
    monkeypatch.setattr(runner_module.time, "time", lambda: now[0])
    return now


def _slot_center(index):
    return (SLOT_1[0] + index * STEP, SLOT_1[1])


# ---------------------------------------------------------------------------
# Cashing in and binning
# ---------------------------------------------------------------------------

def test_a_wanted_fish_is_clicked_once(monkeypatch):
    """One click is the whole payout -- no dialog follows it."""
    runner = _runner(monkeypatch, slots=["wanted"])

    assert runner._tick_fish_inventory(1) is True
    assert runner.events == [("click",) + _slot_center(0)]


def test_an_unwanted_fish_is_dragged_to_the_bin(monkeypatch):
    runner = _runner(monkeypatch, slots=["unwanted"])

    assert runner._tick_fish_inventory(1) is True
    assert runner.events == [("drag",) + _slot_center(0) + TRASH]


def test_a_wanted_fish_is_never_dragged(monkeypatch):
    """The expensive mistake: a binned fish pays nothing."""
    runner = _runner(monkeypatch, slots=["wanted", "wanted", "wanted"])

    runner._tick_fish_inventory(1)

    assert not [e for e in runner.events if e[0] == "drag"]


def test_empty_slots_are_left_alone(monkeypatch):
    runner = _runner(monkeypatch, slots=[None] * FISH_SLOT_COUNT)

    assert runner._tick_fish_inventory(1) is False
    assert runner.events == []


def test_every_slot_is_handled_in_one_pass(monkeypatch):
    """A full row takes no more fish, so one pass has to clear all six rather
    than one slot per tick."""
    runner = _runner(monkeypatch, slots=["wanted", "unwanted", "wanted",
                                         None, "unwanted", "wanted"])

    runner._tick_fish_inventory(1)

    assert [e[0] for e in runner.events] == ["click", "drag", "click", "drag", "click"]


def test_a_fish_matching_both_folders_is_kept_not_binned(monkeypatch):
    """A half-drawn icon can match both folders. Unwanted is asked first, so
    this pins the tie-break: the cheap mistake is clicking junk, not binning a
    fish that pays."""
    runner = _runner(monkeypatch, slots=["wanted"])
    hits = {FISH_UNWANTED_IMAGE: None}

    def look(hwnd, name, region=None, **k):
        if name in hits:
            return hits[name]
        return {"score": 0.9, "cx": region[0], "cy": region[1]}

    monkeypatch.setattr(runner_module.vision, "find_image", look)
    runner._tick_fish_inventory(1)

    assert [e[0] for e in runner.events] == ["click"] * FISH_SLOT_COUNT


def test_unwanted_is_asked_before_wanted(monkeypatch):
    """Order is what makes the tie-break above true -- pin it at the call
    level, not just at its effect."""
    runner = _runner(monkeypatch, slots=["unwanted"])

    runner._tick_fish_inventory(1)

    first_slot_left = runner._fish_slot_region(0)[0]
    asked = [name for name, region in runner.regions if region[0] == first_slot_left]
    assert asked[0] == FISH_UNWANTED_IMAGE


def test_a_neighbouring_card_cannot_match_from_this_slot():
    """A crop is a whole slot card, about a step wide, so a box that holds one
    overhangs its slot -- and that is fine, because a match has to fit whole
    inside the box it was searched in. What must not fit is the NEIGHBOUR's
    whole card as well, or that fish is found from this slot too. Asserted
    against the step the tests pick, since the real one is the user's."""
    narrowest = min(_crop_gray(path).shape[1] for _name, path in _shipped_crops())

    assert FISH_SLOT_BOX[0] < 2 * STEP + narrowest


def test_the_slots_are_read_in_order_and_each_one_only_once(monkeypatch):
    runner = _runner(monkeypatch, slots=[None] * FISH_SLOT_COUNT)

    runner._tick_fish_inventory(1)

    lefts = [region[0] for name, region in runner.regions if name == FISH_UNWANTED_IMAGE]
    assert lefts == sorted(lefts) and len(lefts) == FISH_SLOT_COUNT


# ---------------------------------------------------------------------------
# Never breaking the round
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("missing", [(FISH_WANTED_IMAGE,), (FISH_UNWANTED_IMAGE,)])
def test_a_missing_crop_folder_is_survivable(monkeypatch, missing):
    """Neither folder ships filled. Without crops the slots are simply left
    alone -- casting and the rod watch keep running."""
    runner = _runner(monkeypatch, slots=["wanted"], missing=missing)

    assert runner._tick_fish_inventory(1) is False
    assert runner.events == []
    assert len(runner.logged) == 1


def test_a_missing_crop_is_said_once_not_every_tick(monkeypatch):
    clock = _clock(monkeypatch)
    runner = _runner(monkeypatch, slots=["wanted"], missing=(FISH_UNWANTED_IMAGE,))

    for _ in range(5):
        runner._tick_fish_inventory(1)
        clock[0] += FISH_CHECK_INTERVAL

    assert len(runner.logged) == 1


def test_the_pause_lifts_on_the_next_match(monkeypatch):
    """Paused for the match, never for the run -- the rule the rod watch
    learned the hard way after one failed attempt cost 9.5 hours of fishing."""
    runner = _runner(monkeypatch, slots=["wanted"], missing=(FISH_UNWANTED_IMAGE,))
    runner._tick_fish_inventory(1)

    runner._reset_fishing_for_match()

    assert runner._fish_inventory_paused is False
    assert runner._fish_next_look_at == 0.0


# ---------------------------------------------------------------------------
# Pacing and place in the tick
# ---------------------------------------------------------------------------

def test_the_slots_are_not_read_on_every_tick(monkeypatch):
    """Six template searches for something that changes minutes apart."""
    clock = _clock(monkeypatch)
    runner = _runner(monkeypatch, slots=[None] * FISH_SLOT_COUNT)

    runner._tick_fish_inventory(1)
    reads = len(runner.regions)
    clock[0] += FISH_CHECK_INTERVAL / 2
    runner._tick_fish_inventory(1)
    assert len(runner.regions) == reads, "read again inside the interval"

    clock[0] += FISH_CHECK_INTERVAL
    runner._tick_fish_inventory(1)
    assert len(runner.regions) > reads


def test_the_first_tick_of_a_match_reads_the_slots(monkeypatch):
    """A match can start with fish still sitting in the row from the last
    one."""
    _clock(monkeypatch)
    runner = _runner(monkeypatch, slots=["unwanted"])

    assert runner._tick_fish_inventory(1) is True


def test_a_pass_that_acted_holds_this_ticks_cast_back():
    """A cast landing in the middle of a drag drops the fish anywhere but the
    bin. The next tick casts anyway, so this costs at most one cast."""
    import inspect

    source = inspect.getsource(MacroRunner._wait_for_match_result)
    assert "if not self._tick_fish_inventory(hwnd, stop_event):" in source
    assert source.index("_tick_fish_inventory") < source.index("_tick_fishing(hwnd, fishing_point")


def test_the_inventory_is_only_read_while_fishing_is_on():
    """No fishing, no fish -- and this is six image searches."""
    import inspect

    source = inspect.getsource(MacroRunner._wait_for_match_result)
    guard = source.index("if fishing_point and not clicked_something and not block_acted:")
    assert source.index("_tick_fish_inventory") > guard


def test_both_fish_folders_exist():
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "Assets" / "ui"
    for name in (FISH_WANTED_IMAGE, FISH_UNWANTED_IMAGE):
        assert (root / name).is_dir(), "{} needs a folder for its crops".format(name)


# ---------------------------------------------------------------------------
# Where the row is
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("coords", [
    {"fish_slot_x": None},                 # never picked
    {"fish_slot_step": None},              # half-picked
    {"fish_slot_step": 0},                 # would pile all six on one spot
    {"fish_slot_y": "nonsense"},
])
def test_an_unpicked_row_is_off_not_guessed(monkeypatch, coords):
    """No default could be right, and a made-up row would drag whatever sits
    at those pixels onto whatever sits where the bin was assumed to be."""
    runner = _runner(monkeypatch, slots=["unwanted"], coords=coords)

    assert runner._tick_fish_inventory(1) is False
    assert runner.events == []
    assert runner.regions == [], "nothing should even be searched for"


def test_an_unpicked_row_says_so_once(monkeypatch):
    """Silently doing nothing is indistinguishable from a bad crop."""
    clock = _clock(monkeypatch)
    runner = _runner(monkeypatch, slots=["wanted"], coords={"fish_slot_x": None})

    for _ in range(4):
        runner._tick_fish_inventory(1)
        clock[0] += FISH_CHECK_INTERVAL

    assert len(runner.logged) == 1
    assert "Macro Coordinates" in runner.logged[0]


def test_the_bin_defaults_to_one_step_past_the_last_slot(monkeypatch):
    runner = _runner(monkeypatch)
    last_slot = runner._fish_slot_region(FISH_SLOT_COUNT - 1)

    trash = runner._fish_trash_point()

    assert trash == TRASH
    assert trash[0] > last_slot[0] + last_slot[2], "the bin sits right of slot 6"


def test_a_picked_bin_wins_over_the_derived_one(monkeypatch):
    """One slot-width past slot 6 is an assumption about the gap, and a drag
    landing beside the bin drops the fish straight back into the row."""
    runner = _runner(monkeypatch, slots=["unwanted"],
                     coords={"fish_trash_x": 900, "fish_trash_y": 688})

    runner._tick_fish_inventory(1)

    assert runner.events == [("drag",) + _slot_center(0) + (900, 688)]


def test_the_row_moves_with_the_setting(monkeypatch):
    """The whole point of picking it: another layout is another row, not a
    code change."""
    runner = _runner(monkeypatch, coords={"fish_slot_x": 100, "fish_slot_y": 200,
                                          "fish_slot_step": 70})

    assert runner._fish_slot_region(2)[0] + FISH_SLOT_BOX[0] // 2 == 240
    assert runner._fish_trash_point() == (100 + 6 * 70, 200)


def test_both_coordinate_tables_carry_the_fish_row():
    """main.MACRO_COORD_DEFAULTS is what Settings reads and writes;
    runner.DEFAULT_COORDS is what a run falls back to. A key in one and not
    the other is a setting that silently does nothing."""
    import main

    for key in ("fish_slot_x", "fish_slot_y", "fish_slot_step",
                "fish_trash_x", "fish_trash_y"):
        assert key in main.MACRO_COORD_DEFAULTS, key
        assert key in DEFAULT_COORDS, key
        assert main.MACRO_COORD_DEFAULTS[key] is None and DEFAULT_COORDS[key] is None


def test_the_fish_row_can_be_cleared_from_settings():
    """Picked by hand, so it has to be un-pickable by hand."""
    import main

    for prefix in ("fish_slot", "fish_trash"):
        assert prefix in main.Api.OPTIONAL_COORD_PREFIXES


def test_the_ui_knows_how_many_slots_there_are():
    """app.js previews all six slots plus the bin after a Pick; a drift here
    would preview a row the runner does not read."""
    import re
    from pathlib import Path

    app_js = (Path(__file__).resolve().parent.parent / "ui" / "app.js").read_text(encoding="utf-8")
    match = re.search(r"const FISH_SLOT_COUNT = (\d+)", app_js)
    assert match, "couldn't find FISH_SLOT_COUNT in ui/app.js"
    assert int(match.group(1)) == FISH_SLOT_COUNT


def test_every_fish_coordinate_has_an_input_to_edit_it():
    from pathlib import Path

    html = (Path(__file__).resolve().parent.parent / "ui" / "index.html").read_text(encoding="utf-8")
    for key in ("fish_slot_x", "fish_slot_y", "fish_slot_step",
                "fish_trash_x", "fish_trash_y"):
        assert 'id="coord-{}"'.format(key) in html, key


# ---------------------------------------------------------------------------
# The shipped crops against the real search
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name, path", _shipped_crops(), ids=lambda v: getattr(v, "name", v))
def test_a_shipped_crop_is_found_in_its_slot(monkeypatch, name, path):
    """Every other test here stubs the search, which is how a slot box
    smaller than the crops went unnoticed: the matcher skips a template
    bigger than the image it searches as a plain miss, so every slot read as
    empty and not one fish was ever clicked. Here the real matcher reads a
    row with the crop sitting in slot 1 -- and a wanted fish coming out as
    unwanted fails too, since that drags a paying fish to the bin."""
    import numpy as np

    card = _crop_gray(path)
    screen = np.random.default_rng(0).integers(
        0, 60, (config.FIXED_WIN_H, config.FIXED_WIN_W), dtype=np.uint8)
    (cx, cy), (h, w) = _slot_center(0), card.shape
    screen[cy - h // 2:cy - h // 2 + h, cx - w // 2:cx - w // 2 + w] = card

    runner = _runner(monkeypatch)
    monkeypatch.setattr(runner_module.vision, "find_image", REAL_FIND_IMAGE)
    monkeypatch.setattr(runner_module.vision, "_name_thresholds", {})
    monkeypatch.setattr(runner_module.vision, "capture_game_gray",
                        lambda hwnd, region=None: screen[region[1]:region[1] + region[3],
                                                         region[0]:region[0] + region[2]])

    assert runner._tick_fish_inventory(1) is True
    expected = ("click",) if name == FISH_WANTED_IMAGE else ("drag",)
    assert runner.events[0][:1] == expected and len(runner.events) == 1
    # On the card, not necessarily its centre: another crop of the same fish
    # (e.g. the icon without its label) can be the variant that hits first.
    x, y = runner.events[0][1:3]
    assert abs(x - cx) <= w // 2 and abs(y - cy) <= h // 2, (x, y)


def test_every_shipped_crop_fits_the_slot_box_at_every_scale():
    """The matcher also tries each crop up to 10% larger for a UI that
    renders a little off-size. A crop that only fits at 1x is lost on
    exactly the setups that sweep is there for."""
    from core.vision import SCALE_FACTORS

    for _name, path in _shipped_crops():
        height, width = _crop_gray(path).shape
        for scale in SCALE_FACTORS:
            assert round(width * scale) <= FISH_SLOT_BOX[0], (path.name, scale)
            assert round(height * scale) <= FISH_SLOT_BOX[1], (path.name, scale)
