import re
import threading
from pathlib import Path

import pytest

from core import runner_eclipse
from core import vision
from core.runner_constants import (
    CHALLENGE_STORY_MAPS,
    ECLIPSE_CARD_IMAGES,
    ECLIPSE_CARD_ORDER,
    ECLIPSE_MARKER_MAP_MAX_DX,
    QUEST_ACCEPT_IMAGE,
    QUEST_DIALOG_IMAGE,
    QUEST_REDEEM_IMAGES,
    QUEST_STATE_ACTIVE,
    QUEST_STATE_NOT_STARTED,
    QUEST_STATE_UNKNOWN,
    SOULS_FULL_IMAGE,
)


def _match(cx, cy, score=0.9):
    return {"x": cx - 10, "y": cy - 5, "w": 20, "h": 10, "cx": cx, "cy": cy, "score": score}


class FakeRunner(runner_eclipse.EclipseOps):
    """The mixin with just the MacroRunner surface it actually touches."""

    def __init__(self):
        self.logs = []
        self.clicks = []
        self.taps = []
        self.statuses = []

    def _log(self, message):
        self.logs.append(message)

    def _set_status(self, **kwargs):
        self.statuses.append(kwargs)

    def _debug_save(self, hwnd, name, match):
        return None

    def _checkpoint(self, stop_event):
        return stop_event is not None and stop_event.is_set()

    @property
    def said(self):
        return " ".join(self.logs)


@pytest.fixture
def runner():
    return FakeRunner()


def _on_screen(*names_on_screen):
    """A screen showing exactly these images.

    Patched over wait_for_image_any, which is what reads the dialog: it tries
    every candidate name per poll tick and returns the first that hits, so the
    fake answers in candidate ORDER rather than per-name.
    """
    def wait(hwnd, names, **kw):
        for name in names:
            if name in names_on_screen:
                return _match(400, 300), name
        return None, None
    return wait


def _only(name_on_screen):
    return _on_screen(name_on_screen)


@pytest.fixture(autouse=True)
def all_crops_present(monkeypatch):
    """Default: every reference image exists. Tests about MISSING crops
    override this -- everything else would otherwise be testing the absence
    of files rather than the logic it means to."""
    monkeypatch.setattr(vision, "template_variant_paths", lambda name, d: ["x.png"])


def _nothing(hwnd, names, **kw):
    return None, None


def _all_present(hwnd, names, **kw):
    """Every candidate matches -- the fake for "which one wins" tests."""
    return _match(400, 300), names[0]


# ── card choice ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("choice,expected", sorted(ECLIPSE_CARD_IMAGES.items()))
def test_each_card_choice_maps_to_its_own_reference_image(runner, choice, expected):
    assert runner._eclipse_card_image({"eclipse_card": choice}) == expected


@pytest.mark.parametrize("task", [{}, {"eclipse_card": ""}, {"eclipse_card": "banana"}])
def test_an_unset_or_unknown_card_still_farms_and_says_what_it_used(runner, task):
    # Refusing to run would cost a whole cycle over a field the user can fix
    # in a second -- but it has to be visible in the log which card was used.
    assert runner._eclipse_card_image(task) == ECLIPSE_CARD_IMAGES[ECLIPSE_CARD_ORDER[0]]
    assert ECLIPSE_CARD_ORDER[0] in runner.said


def test_the_configured_card_is_clicked_where_it_was_found(runner, monkeypatch):
    # Not a click in the middle of the screen: which card is taken is the
    # whole point, and the three do not hold fixed positions in the row.
    found = _match(720, 400)
    monkeypatch.setattr(vision, "find_image", lambda hwnd, name, **kw: found)
    monkeypatch.setattr(runner_eclipse.wm, "activate_window", lambda hwnd: True)
    clicked = []
    monkeypatch.setattr(vision, "click_match",
                        lambda mouse, hwnd, match, **kw: clicked.append(match))
    runner._mouse = object()

    assert runner._take_eclipse_card_if_found(1, "eclipse_card_sacrifice") is True
    assert clicked == [found]


def test_no_card_on_screen_is_not_reported_as_taken(runner, monkeypatch):
    monkeypatch.setattr(vision, "find_image", lambda hwnd, name, **kw: None)
    assert runner._take_eclipse_card_if_found(1, "eclipse_card_sacrifice") is False


def test_a_missing_card_crop_does_not_spam_the_log_every_poll(runner, monkeypatch):
    # This is polled several times a second for the whole match; one line per
    # tick would bury everything else in the log.
    def missing(hwnd, name, **kw):
        raise vision.TemplateNotFound(name)

    monkeypatch.setattr(vision, "find_image", missing)
    for _ in range(20):
        assert runner._take_eclipse_card_if_found(1, "eclipse_card_neutral") is False
    assert runner.logs == []


# ── the farm loop's stop condition ──────────────────────────────────────────

def test_a_full_soul_stack_is_detected(runner, monkeypatch):
    monkeypatch.setattr(vision, "find_image", lambda hwnd, name, **kw: _match(500, 300))
    assert runner._eclipse_souls_are_full(1) is True


def test_a_partial_soul_stack_keeps_the_loop_farming(runner, monkeypatch):
    monkeypatch.setattr(vision, "find_image", lambda hwnd, name, **kw: None)
    assert runner._eclipse_souls_are_full(1) is False


def test_a_missing_souls_crop_stops_farming_rather_than_farming_forever(runner, monkeypatch):
    # "crop missing" and "not full yet" both produce no match, and this is
    # the loop's ONLY exit -- so the missing crop has to break the loop, not
    # silently become "keep going" and farm the same event all night.
    def missing(hwnd, name, **kw):
        raise vision.TemplateNotFound(name)

    monkeypatch.setattr(vision, "find_image", missing)
    assert runner._eclipse_souls_are_full(1) is True
    assert SOULS_FULL_IMAGE in runner.said


# ── which map is the event on ───────────────────────────────────────────────

def test_the_map_under_the_marker_is_the_one_reported(runner, monkeypatch):
    marker = _match(576, 200)
    labels = {
        "School Grounds": _match(196, 320),   # left card
        "East Town": _match(560, 320),        # under the marker
        "Flower Forest": _match(956, 320),    # right card
    }
    monkeypatch.setattr(vision, "find_image",
                        lambda hwnd, name, **kw: labels.get(name))

    assert runner._eclipse_map_under(1, marker) == "East Town"


def test_a_label_above_the_marker_is_not_a_card_label(runner, monkeypatch):
    # The marker sits ABOVE its own card's name. Anything higher up the
    # screen is some other piece of UI, not the card this marker belongs to.
    marker = _match(576, 300)
    monkeypatch.setattr(vision, "find_image",
                        lambda hwnd, name, **kw: _match(576, 120) if name == "East Town" else None)

    assert runner._eclipse_map_under(1, marker) is None


def test_a_label_too_far_sideways_belongs_to_a_neighbouring_card(runner, monkeypatch):
    marker = _match(576, 200)
    far = ECLIPSE_MARKER_MAP_MAX_DX + 40
    monkeypatch.setattr(vision, "find_image",
                        lambda hwnd, name, **kw: (_match(576 + far, 320)
                                                  if name == "East Town" else None))

    assert runner._eclipse_map_under(1, marker) is None


def test_maps_without_a_label_crop_are_skipped_not_fatal(runner, monkeypatch):
    # Crimson Shore's carousel crop is still being added; a map with no crop
    # must not stop the other six from being recognized.
    marker = _match(576, 200)

    def find(hwnd, name, **kw):
        if name == CHALLENGE_STORY_MAPS[0]:
            raise vision.TemplateNotFound(name)
        return _match(576, 320) if name == "East Town" else None

    monkeypatch.setattr(vision, "find_image", find)
    assert runner._eclipse_map_under(1, marker) == "East Town"


def test_no_marker_on_screen_means_no_event_running(runner, monkeypatch):
    monkeypatch.setattr(vision, "wait_for_image", lambda hwnd, name, **kw: None)
    assert runner._find_eclipse_story_map(1, threading.Event()) == (None, None)


def test_a_marker_with_no_identifiable_map_is_still_returned(runner, monkeypatch):
    # The card can be clicked from the marker's own position even when no
    # label matched, so losing the NAME must not lose the event.
    marker = _match(576, 200)
    monkeypatch.setattr(vision, "wait_for_image", lambda hwnd, name, **kw: marker)
    monkeypatch.setattr(vision, "find_image", lambda hwnd, name, **kw: None)

    found_map, found_marker = runner._find_eclipse_story_map(1, threading.Event())
    assert found_map is None
    assert found_marker == marker


# ── talking to the NPC ──────────────────────────────────────────────────────

@pytest.mark.parametrize("path_data", [None, {"events": []}, {}])
def test_a_missing_or_empty_walk_path_is_reported(runner, monkeypatch, path_data):
    monkeypatch.setattr(runner_eclipse.walk_paths, "load_path", lambda name: path_data)
    assert runner._talk_to_quest_npc(1, threading.Event(), "npc route") == (None, False)
    assert "npc route" in runner.said


def test_no_walk_path_configured_at_all_is_reported(runner):
    assert runner._talk_to_quest_npc(1, threading.Event(), "") == (None, False)
    assert "walk path" in runner.said.lower()


def test_a_route_recorded_without_the_e_press_still_opens_the_dialog(runner, monkeypatch):
    # Old recordings (and anyone who just walked and stopped) have no E in
    # them -- the fallback tap is what keeps those working.
    monkeypatch.setattr(runner_eclipse.walk_paths, "load_path",
                        lambda name: {"events": [{"t": 0.0, "key": "w", "state": "down"}]})
    monkeypatch.setattr(runner_eclipse.walk_paths, "replay_events", lambda *a, **kw: None)
    monkeypatch.setattr(runner_eclipse.wm, "activate_window", lambda hwnd: True)

    tapped = {"yet": False}

    def wait(hwnd, names, **kw):
        # Nothing on screen until the E tap lands.
        if not tapped["yet"]:
            return None, None
        return _match(400, 300), QUEST_ACCEPT_IMAGE

    monkeypatch.setattr(vision, "wait_for_image_any", wait)
    runner._keyboard = type("K", (), {
        "tap": lambda self, vk: (runner.taps.append(vk), tapped.update(yet=True))})()
    runner._click_found_image = lambda *a, **kw: _match(400, 400)

    assert runner._talk_to_quest_npc(
        1, threading.Event(), "npc route",
        press_states=(QUEST_STATE_NOT_STARTED,)) == (QUEST_STATE_NOT_STARTED, True)
    assert runner.taps == [ord("E")]


def test_a_route_that_already_presses_e_is_not_tapped_again(runner, monkeypatch):
    # A second E would advance or close a dialog that is already open. The
    # button being on screen is itself the proof it opened.
    monkeypatch.setattr(runner_eclipse.walk_paths, "load_path",
                        lambda name: {"events": [{"t": 0.0, "key": "e", "state": "down"}]})
    monkeypatch.setattr(runner_eclipse.walk_paths, "replay_events", lambda *a, **kw: None)
    monkeypatch.setattr(runner_eclipse.wm, "activate_window", lambda hwnd: True)
    monkeypatch.setattr(vision, "wait_for_image_any", _only(QUEST_ACCEPT_IMAGE))
    runner._keyboard = type("K", (), {"tap": lambda self, vk: runner.taps.append(vk)})()
    runner._click_found_image = lambda *a, **kw: _match(400, 400)

    assert runner._talk_to_quest_npc(
        1, threading.Event(), "npc route",
        press_states=(QUEST_STATE_NOT_STARTED,)) == (QUEST_STATE_NOT_STARTED, True)
    assert runner.taps == []


# ── where the route to the NPC comes from ───────────────────────────────────

def _template(blocks):
    return {"name": "t", "blocks": blocks}


def test_the_npc_route_is_read_off_the_tasks_macro_operation(runner, monkeypatch):
    # The route is not an Eclipse-only task field -- it is the Custom Walk
    # Path block inside the Macro Operation the task already picks.
    import core.templates as tpl
    monkeypatch.setattr(tpl, "load_template", lambda name: _template({
        "prestart": [
            {"type": "setting", "params": {}},
            {"type": "walk_path", "mode": "custom", "pathName": "To the NPC", "sprint": True},
        ]}))

    assert runner._eclipse_npc_walk_path({"macro": "t"}) == ("To the NPC", True)


def test_an_auto_walk_block_is_not_a_route_to_the_npc(runner, monkeypatch):
    # Auto resolves to the MAP's default walk, which goes wherever that map's
    # units get placed -- not to a quest NPC.
    import core.templates as tpl
    monkeypatch.setattr(tpl, "load_template", lambda name: _template({
        "prestart": [{"type": "walk_path", "mode": "auto", "pathName": ""}]}))

    assert runner._eclipse_npc_walk_path({"macro": "t"}) == (None, False)


def test_a_template_saved_in_the_old_top_level_walk_shape_still_resolves(runner, monkeypatch):
    # Same legacy shape _run_walk_path_block migrates -- a template nobody
    # has reopened in Macro Manager since the block change.
    import core.templates as tpl
    monkeypatch.setattr(tpl, "load_template", lambda name: _template({
        "prestart": [],
        "walk": {"mode": "custom", "pathName": "Old route", "sprint": False},
    }))

    assert runner._eclipse_npc_walk_path({"macro": "t"}) == ("Old route", False)


def test_a_task_with_no_macro_has_no_route(runner):
    assert runner._eclipse_npc_walk_path({}) == (None, False)


def test_a_template_saved_in_the_old_list_format_does_not_crash(runner, monkeypatch):
    import core.templates as tpl
    monkeypatch.setattr(tpl, "load_template", lambda name: _template([]))
    assert runner._eclipse_npc_walk_path({"macro": "t"}) == (None, False)


def test_the_route_is_replayed_with_the_blocks_sprint_setting(runner, monkeypatch):
    # A route recorded at sprint speed only reaches its spot at sprint speed.
    monkeypatch.setattr(runner_eclipse.walk_paths, "load_path",
                        lambda name: {"events": [{"t": 0.0, "key": "w", "state": "down"}]})
    seen = {}
    monkeypatch.setattr(runner_eclipse.walk_paths, "replay_events",
                        lambda events, kb, stop, sprint=False: seen.update(sprint=sprint))
    monkeypatch.setattr(runner_eclipse.wm, "activate_window", lambda hwnd: True)
    monkeypatch.setattr(vision, "wait_for_image_any", _only(QUEST_ACCEPT_IMAGE))
    runner._keyboard = type("K", (), {"tap": lambda self, vk: runner.taps.append(vk)})()
    runner._click_found_image = lambda *a, **kw: _match(400, 400)

    runner._talk_to_quest_npc(1, threading.Event(), "route", sprint=True)
    assert seen == {"sprint": True}


# ── only Eclipse pays for the card search ───────────────────────────────────

@pytest.mark.parametrize("mode,watched", [
    ("eclipse", True), ("story", False), ("raid", False),
    ("expedition", False), ("portals", False), (None, False),
])
def test_only_an_eclipse_task_watches_for_the_card_choice(mode, watched):
    # The watch runs inside the battle poll loop, which is time-critical --
    # every other mode would be paying for a search that can never hit.
    assert runner_eclipse.EclipseOps._wants_eclipse_card_watch({"mode": mode}) is watched


def test_a_missing_task_does_not_watch_for_cards():
    assert runner_eclipse.EclipseOps._wants_eclipse_card_watch(None) is False


# ── picking up a cycle a crash interrupted ──────────────────────────────────

def test_a_redeem_button_means_a_quest_is_still_running(runner, monkeypatch):
    monkeypatch.setattr(vision, "wait_for_image_any", _only("quest_redeem_sacrifice"))
    state, button, _ = runner._eclipse_quest_state(1, {"eclipse_card": "sacrifice"})
    assert (state, button) == (QUEST_STATE_ACTIVE, "quest_redeem_sacrifice")


def test_an_accept_button_means_nothing_is_running(runner, monkeypatch):
    monkeypatch.setattr(vision, "wait_for_image_any", _only(QUEST_ACCEPT_IMAGE))
    state, button, _ = runner._eclipse_quest_state(1, {})
    assert (state, button) == (QUEST_STATE_NOT_STARTED, QUEST_ACCEPT_IMAGE)


def test_the_redeem_button_matching_the_farmed_card_is_preferred(runner, monkeypatch):
    # Both are on screen (a crop that matches too loosely, say) -- the one
    # for the souls this task actually farmed has to win.
    monkeypatch.setattr(vision, "wait_for_image_any", _all_present)
    _, button, _ = runner._eclipse_quest_state(1, {"eclipse_card": "redemption"})
    assert button == QUEST_REDEEM_IMAGES["redemption"]


def test_a_card_with_no_redeem_button_of_its_own_takes_whatever_is_offered(runner, monkeypatch):
    # Neutral has no redeem button in QUEST_REDEEM_IMAGES; the NPC only ever
    # offers the one matching what you actually carry, so take that.
    monkeypatch.setattr(vision, "wait_for_image_any", _only("quest_redeem_redemption"))
    state, button, _ = runner._eclipse_quest_state(1, {"eclipse_card": "neutral"})
    assert (state, button) == (QUEST_STATE_ACTIVE, "quest_redeem_redemption")


def test_no_button_at_all_reads_as_unknown(runner, monkeypatch):
    monkeypatch.setattr(vision, "wait_for_image_any", _nothing)
    state, button, _ = runner._eclipse_quest_state(1, {})
    assert (state, button) == (QUEST_STATE_UNKNOWN, None)


def test_missing_crops_do_not_blind_the_search_for_the_others(runner, monkeypatch):
    # The reference images are still being collected -- one missing crop must
    # not stop the buttons that DO have one from being found. vision's own
    # find_image_any skips names with no file; this checks the state read
    # passes every candidate down so that skipping can happen at all.
    def wait(hwnd, names, **kw):
        assert QUEST_REDEEM_IMAGES["redemption"] in names
        return _match(400, 300), QUEST_REDEEM_IMAGES["redemption"]

    monkeypatch.setattr(vision, "wait_for_image_any", wait)
    state, button, _ = runner._eclipse_quest_state(1, {"eclipse_card": "sacrifice"})
    assert (state, button) == (QUEST_STATE_ACTIVE, QUEST_REDEEM_IMAGES["redemption"])


def test_every_candidate_missing_reads_as_unknown_without_logging(runner, monkeypatch):
    # vision raises on the first poll tick when nothing is on disk. The read
    # stays quiet about it: it happens twice per visit, and the task-level
    # preflight already refuses the run with a message that names every
    # missing file.
    def all_missing(hwnd, names, **kw):
        raise vision.TemplateNotFound(names[0])

    monkeypatch.setattr(vision, "wait_for_image_any", all_missing)
    state, button, _ = runner._eclipse_quest_state(1, {})
    assert (state, button) == (QUEST_STATE_UNKNOWN, None)
    assert runner.logs == []


@pytest.mark.parametrize("state,farms_first", [
    (QUEST_STATE_ACTIVE, True),
    # The recoverable guess: if it is wrong, no map carries the marker and
    # the cycle finds out in seconds. Guessing the other way burns a cycle
    # hunting an Accept button the dialog is not offering, on a quest that
    # was already half farmed.
    (QUEST_STATE_UNKNOWN, True),
    (QUEST_STATE_NOT_STARTED, False),
])
def test_an_unreadable_state_errs_toward_the_recoverable_mistake(state, farms_first):
    assert runner_eclipse.EclipseOps._eclipse_should_farm_first(state) is farms_first


def test_the_walk_presses_the_button_the_dialog_is_actually_offering(runner, monkeypatch):
    # The caller does not have to know which half of the cycle it is in --
    # that is what makes a crashed cycle recoverable.
    monkeypatch.setattr(runner_eclipse.walk_paths, "load_path",
                        lambda name: {"events": [{"t": 0.0, "key": "e", "state": "down"}]})
    monkeypatch.setattr(runner_eclipse.walk_paths, "replay_events", lambda *a, **kw: None)
    monkeypatch.setattr(runner_eclipse.wm, "activate_window", lambda hwnd: True)
    monkeypatch.setattr(vision, "wait_for_image_any", _only(QUEST_REDEEM_IMAGES["sacrifice"]))
    runner._keyboard = object()
    pressed = []
    runner._click_found_image = lambda hwnd, name, *a, **kw: pressed.append(name) or _match(1, 1)

    state, did_press = runner._talk_to_quest_npc(
        1, threading.Event(), "route", task={"eclipse_card": "sacrifice"},
        press_states=(QUEST_STATE_ACTIVE,))
    assert (state, did_press) == (QUEST_STATE_ACTIVE, True)
    assert pressed == [QUEST_REDEEM_IMAGES["sacrifice"]]


def test_a_walk_that_never_reaches_the_npc_presses_nothing(runner, monkeypatch):
    monkeypatch.setattr(runner_eclipse.walk_paths, "load_path",
                        lambda name: {"events": [{"t": 0.0, "key": "w", "state": "down"}]})
    monkeypatch.setattr(runner_eclipse.walk_paths, "replay_events", lambda *a, **kw: None)
    monkeypatch.setattr(runner_eclipse.wm, "activate_window", lambda hwnd: True)
    monkeypatch.setattr(vision, "wait_for_image_any", _nothing)
    monkeypatch.setattr(vision, "wait_for_image", lambda hwnd, name, **kw: None)
    monkeypatch.setattr(vision, "template_variant_paths", lambda name, d: ["x.png"])
    runner._keyboard = type("K", (), {"tap": lambda self, vk: runner.taps.append(vk)})()
    runner._interruptible_sleep = lambda secs, stop=None: None
    pressed = []
    runner._click_found_image = lambda hwnd, name, *a, **kw: pressed.append(name) or _match(1, 1)

    assert runner._talk_to_quest_npc(1, threading.Event(), "route") == (QUEST_STATE_UNKNOWN, False)
    assert pressed == []
    assert runner.taps == [ord("E")]      # the one retry, then it gives up


# ── the Task Builder and the runner have to agree ───────────────────────────

APP_JS = Path(__file__).resolve().parent.parent / "ui" / "app.js"


def test_every_offered_card_has_a_reference_image_name():
    assert set(ECLIPSE_CARD_IMAGES) == set(ECLIPSE_CARD_ORDER)


def test_the_task_builders_card_list_matches_the_runner_constants():
    """TASK_DATA.eclipse.cards in ui/app.js is what writes a task's
    `eclipse_card`, and the runner looks that string up in
    ECLIPSE_CARD_IMAGES to know which card to click. A card offered in the UI
    but missing from the constants would silently fall back to the default
    mid-battle, so the two lists have to stay in step."""
    src = APP_JS.read_text(encoding="utf-8")
    block = re.search(r"eclipse:\s*\{.*?cards:\s*\[(.*?)\]", src, re.S)
    assert block, "couldn't find TASK_DATA.eclipse.cards in ui/app.js"
    ui_cards = [a or b for a, b in re.findall(r"'([^']+)'|\"([^\"]+)\"", block.group(1))]
    assert ui_cards == list(ECLIPSE_CARD_ORDER)


def test_every_redeem_button_belongs_to_a_card_the_ui_offers():
    # A redeem button for a card nobody can select would never be reachable.
    assert set(QUEST_REDEEM_IMAGES) <= set(ECLIPSE_CARD_ORDER)


# ── the cycle ───────────────────────────────────────────────────────────────

class CycleRunner(FakeRunner):
    """FakeRunner plus stubs for the navigation the cycle delegates."""

    def __init__(self, npc_visits=(), farm_ok=True):
        super().__init__()
        self._npc_visits = list(npc_visits)
        self._farm_ok = farm_ok
        self.visit_press_states = []
        self.farmed = 0

    def _eclipse_npc_walk_path(self, task):
        return "route", False

    def _eclipse_visit_npc(self, hwnd, stop_event, task, walk_path, sprint,
                           press_states, coords, scroll_power, scroll_nudges, webhook=None):
        self.visit_press_states.append(press_states)
        return self._npc_visits.pop(0) if self._npc_visits else (None, False)

    def _run_eclipse_farm(self, *a, **kw):
        self.farmed += 1
        return self._farm_ok


def _cycle(runner, task=None):
    return runner._run_eclipse_cycle(1, threading.Event(), task or {}, {}, {}, 1, 1)


def test_a_fresh_cycle_accepts_farms_and_redeems():
    runner = CycleRunner(npc_visits=[(QUEST_STATE_NOT_STARTED, True),
                                     (QUEST_STATE_ACTIVE, True)])
    assert _cycle(runner) is True
    assert runner.farmed == 1
    # The first visit may only press Accept, the second only Redeem -- that
    # asymmetry is what stops a half-finished quest being cashed in early.
    assert runner.visit_press_states == [(QUEST_STATE_NOT_STARTED,), (QUEST_STATE_ACTIVE,)]


def test_a_quest_a_crash_left_running_is_continued_not_restarted():
    # The NPC offers Redeem, so nothing is pressed on the way in (press_states
    # is Accept-only) and the cycle goes straight to farming the rest.
    runner = CycleRunner(npc_visits=[(QUEST_STATE_ACTIVE, False),
                                     (QUEST_STATE_ACTIVE, True)])
    assert _cycle(runner) is True
    assert runner.farmed == 1


def test_an_unreadable_dialog_still_goes_farming():
    runner = CycleRunner(npc_visits=[(QUEST_STATE_UNKNOWN, False),
                                     (QUEST_STATE_ACTIVE, True)])
    assert _cycle(runner) is True
    assert runner.farmed == 1


def test_a_failed_accept_does_not_go_farming():
    # No quest running AND the Accept press didn't land -- there is no event
    # to farm, so burning a cycle looking for one helps nobody.
    runner = CycleRunner(npc_visits=[(QUEST_STATE_NOT_STARTED, False)])
    assert _cycle(runner) is False
    assert runner.farmed == 0


def test_never_reaching_the_npc_ends_the_cycle():
    runner = CycleRunner(npc_visits=[(None, False)])
    assert _cycle(runner) is False
    assert runner.farmed == 0


def test_a_farm_that_never_caps_does_not_try_to_redeem():
    runner = CycleRunner(npc_visits=[(QUEST_STATE_NOT_STARTED, True)], farm_ok=False)
    assert _cycle(runner) is False
    assert len(runner.visit_press_states) == 1


def test_souls_stay_in_the_inventory_when_redeeming_fails():
    runner = CycleRunner(npc_visits=[(QUEST_STATE_NOT_STARTED, True),
                                     (QUEST_STATE_ACTIVE, False)])
    assert _cycle(runner) is False
    assert "next cycle" in runner.said


def test_a_task_without_a_recorded_route_never_leaves_the_lobby():
    runner = CycleRunner()
    runner._eclipse_npc_walk_path = lambda task: (None, False)
    assert _cycle(runner) is False
    assert runner.visit_press_states == []


def test_a_redeem_button_is_never_pressed_by_the_accept_visit(runner, monkeypatch):
    # THE safety property. A cycle starts by visiting the NPC to find out
    # where it stands. If a crash left a quest running, the dialog offers
    # Redeem -- and pressing it would cash in a partial soul stack, throwing
    # away however long the interrupted cycle had already farmed.
    monkeypatch.setattr(runner_eclipse.walk_paths, "load_path",
                        lambda name: {"events": [{"t": 0.0, "key": "e", "state": "down"}]})
    monkeypatch.setattr(runner_eclipse.walk_paths, "replay_events", lambda *a, **kw: None)
    monkeypatch.setattr(runner_eclipse.wm, "activate_window", lambda hwnd: True)
    monkeypatch.setattr(vision, "wait_for_image_any", _only(QUEST_REDEEM_IMAGES["sacrifice"]))
    runner._keyboard = object()
    pressed = []
    runner._click_found_image = lambda hwnd, name, *a, **kw: pressed.append(name) or _match(1, 1)

    state, did_press = runner._talk_to_quest_npc(
        1, threading.Event(), "route", task={"eclipse_card": "sacrifice"},
        press_states=(QUEST_STATE_NOT_STARTED,))

    assert (state, did_press) == (QUEST_STATE_ACTIVE, False)
    assert pressed == []


def test_an_accept_button_is_never_pressed_by_the_redeem_visit(runner, monkeypatch):
    # The mirror case: souls farmed, but the NPC is offering Accept. Pressing
    # it would start a SECOND quest on top of an unredeemed stack.
    monkeypatch.setattr(runner_eclipse.walk_paths, "load_path",
                        lambda name: {"events": [{"t": 0.0, "key": "e", "state": "down"}]})
    monkeypatch.setattr(runner_eclipse.walk_paths, "replay_events", lambda *a, **kw: None)
    monkeypatch.setattr(runner_eclipse.wm, "activate_window", lambda hwnd: True)
    monkeypatch.setattr(vision, "wait_for_image_any", _only(QUEST_ACCEPT_IMAGE))
    runner._keyboard = object()
    pressed = []
    runner._click_found_image = lambda hwnd, name, *a, **kw: pressed.append(name) or _match(1, 1)

    state, did_press = runner._talk_to_quest_npc(
        1, threading.Event(), "route", press_states=(QUEST_STATE_ACTIVE,))

    assert (state, did_press) == (QUEST_STATE_NOT_STARTED, False)
    assert pressed == []


def test_the_dialog_is_waited_for_not_glanced_at(runner, monkeypatch):
    # The walk ends the instant its last key is released -- before the game
    # has registered the interact or drawn anything. A zero-timeout look
    # lands in that gap and reports "the walk missed the NPC" (reported live,
    # exactly that way), so both reads have to carry a real timeout.
    timeouts = []

    def wait(hwnd, names, **kw):
        timeouts.append(kw.get("timeout"))
        return None, None

    monkeypatch.setattr(runner_eclipse.walk_paths, "load_path",
                        lambda name: {"events": [{"t": 0.0, "key": "w", "state": "down"}]})
    monkeypatch.setattr(runner_eclipse.walk_paths, "replay_events", lambda *a, **kw: None)
    monkeypatch.setattr(runner_eclipse.wm, "activate_window", lambda hwnd: True)
    monkeypatch.setattr(vision, "wait_for_image_any", wait)
    monkeypatch.setattr(vision, "wait_for_image", lambda hwnd, name, **kw: None)
    monkeypatch.setattr(vision, "template_variant_paths", lambda name, d: ["x.png"])
    runner._keyboard = type("K", (), {"tap": lambda self, vk: runner.taps.append(vk)})()

    runner._talk_to_quest_npc(1, threading.Event(), "route")

    assert len(timeouts) == 2, "expected a look before the E tap and one after"
    assert all(t and t > 0 for t in timeouts), timeouts
    # Short before the tap (dead time when the route has no E), longer after.
    assert timeouts[0] < timeouts[1]


def test_the_state_read_reports_what_it_saw_not_what_will_be_done(runner, monkeypatch):
    # The read is used both to decide AND to recover; it used to log
    # "assuming a quest is running and going farming" from inside the read
    # itself, which claimed a decision the caller had not taken and printed
    # it twice per visit.
    monkeypatch.setattr(vision, "wait_for_image_any", _only(QUEST_ACCEPT_IMAGE))
    runner._eclipse_quest_state(1, {})
    assert "going farming" not in runner.said
    assert "assuming" not in runner.said.lower()


# ── refusing a task that cannot possibly work ───────────────────────────────

class PreflightRunner(FakeRunner):
    def __init__(self):
        super().__init__()
        self.cycles = 0
        self.walk = ("route", False)

    def _eclipse_npc_walk_path(self, task):
        return self.walk

    def _run_eclipse_cycle(self, *a, **kw):
        self.cycles += 1
        return True


def _preflight(runner, task=None):
    return runner._run_eclipse_task(1, threading.Event(), task or {"repeat": 3},
                                    1, 1, {}, 1, 1, {})


def test_a_task_with_no_quest_button_crops_never_enters_a_map(monkeypatch):
    # vision raises the instant EVERY candidate is missing, so the polled wait
    # at the NPC returns without ever polling -- after the run has already
    # spent minutes entering the map and walking there. Knowable from disk.
    runner = PreflightRunner()
    monkeypatch.setattr(vision, "template_variant_paths", lambda name, d: [])

    assert _preflight(runner) is True      # task skipped, run continues
    assert runner.cycles == 0
    assert "can't be read at all" in runner.said
    # It has to point at the ONE crop that needs no farming to capture.
    assert QUEST_ACCEPT_IMAGE in runner.said


def test_some_crops_present_still_runs_but_names_what_is_missing(monkeypatch):
    runner = PreflightRunner()
    monkeypatch.setattr(vision, "template_variant_paths",
                        lambda name, d: ["x.png"] if name == QUEST_ACCEPT_IMAGE else [])

    assert _preflight(runner) is True
    assert runner.cycles == 3
    assert QUEST_REDEEM_IMAGES["sacrifice"] in runner.said


def test_a_task_with_no_recorded_route_is_refused_before_entering_a_map(monkeypatch):
    runner = PreflightRunner()
    runner.walk = (None, False)
    monkeypatch.setattr(vision, "template_variant_paths", lambda name, d: ["x.png"])

    assert _preflight(runner) is True
    assert runner.cycles == 0
    assert "Custom Walk Path" in runner.said


def test_a_fully_equipped_task_runs_every_cycle(monkeypatch):
    runner = PreflightRunner()
    monkeypatch.setattr(vision, "template_variant_paths", lambda name, d: ["x.png"])

    assert _preflight(runner) is True
    assert runner.cycles == 3
    assert "missing" not in runner.said


# ── the failure message has to point at the right fix ───────────────────────

def test_missing_crops_are_named_rather_than_blamed_on_the_walk(runner, monkeypatch):
    # "the walk didn't end on the NPC" was printed while the dialog was
    # visibly open and still animating in -- it sent the user looking at the
    # recorded route when the real fix was a crop.
    monkeypatch.setattr(vision, "template_variant_paths", lambda name, d: [])
    monkeypatch.setattr(vision, "wait_for_image", lambda hwnd, name, **kw: None)

    runner._log_missing_quest_dialog(1, None, {})
    assert "none of the quest button crops exist yet" in runner.said
    assert "walk didn't end" not in runner.said


def test_an_open_dialog_is_not_reported_as_a_failed_walk(runner, monkeypatch):
    monkeypatch.setattr(vision, "template_variant_paths",
                        lambda name, d: ["x.png"] if name == QUEST_ACCEPT_IMAGE else [])
    monkeypatch.setattr(vision, "wait_for_image", lambda hwnd, name, **kw: _match(1, 1))

    runner._log_missing_quest_dialog(1, None, {})
    assert "dialog IS open" in runner.said
    assert "walk didn't end" not in runner.said


def test_a_dialog_that_really_never_opened_still_says_so(runner, monkeypatch):
    monkeypatch.setattr(vision, "template_variant_paths", lambda name, d: ["x.png"])
    monkeypatch.setattr(vision, "wait_for_image", lambda hwnd, name, **kw: None)

    runner._log_missing_quest_dialog(1, None, {})
    assert "never opened" in runner.said


def test_the_dialog_diagnosis_waits_instead_of_glancing(runner, monkeypatch):
    seen = []
    monkeypatch.setattr(vision, "template_variant_paths", lambda name, d: ["x.png"])
    monkeypatch.setattr(vision, "wait_for_image",
                        lambda hwnd, name, **kw: seen.append(kw.get("timeout")) or None)

    runner._log_missing_quest_dialog(1, None, {})
    assert seen and all(t and t > 0 for t in seen), seen


# ── the dialog frame as a state signal ──────────────────────────────────────

def test_an_open_dialog_without_accept_means_a_quest_is_running(runner, monkeypatch):
    # The point of this inference: reading the state used to need a redeem
    # crop, which cannot be screenshotted until 150 souls have been farmed,
    # which needs the cycle to run. The dialog frame breaks that circle.
    monkeypatch.setattr(vision, "wait_for_image_any", _on_screen(QUEST_DIALOG_IMAGE))

    state, button, _ = runner._eclipse_quest_state(1, {})

    assert state == QUEST_STATE_ACTIVE
    assert button is None          # nothing to press; the caller goes farming
    assert "not offering Accept" in runner.said


def test_an_open_dialog_with_accept_still_means_a_fresh_quest(runner, monkeypatch):
    # Both visible on the same tick -- the button has to win over the frame.
    monkeypatch.setattr(vision, "wait_for_image_any",
                        _on_screen(QUEST_DIALOG_IMAGE, QUEST_ACCEPT_IMAGE))

    state, button, _ = runner._eclipse_quest_state(1, {})
    assert (state, button) == (QUEST_STATE_NOT_STARTED, QUEST_ACCEPT_IMAGE)


def test_buttons_get_a_moment_to_animate_in_before_absence_means_anything(runner, monkeypatch):
    # The buttons render INSIDE the frame, so the frame always wins the first
    # look. Reading that first look as "no Accept" would call every fresh
    # quest a running one.
    calls = []

    def wait(hwnd, names, **kw):
        calls.append(tuple(names))
        if len(calls) == 1:
            return _match(1, 1), QUEST_DIALOG_IMAGE       # frame only, so far
        return _match(400, 300), QUEST_ACCEPT_IMAGE       # button caught up

    monkeypatch.setattr(vision, "wait_for_image_any", wait)

    state, button, _ = runner._eclipse_quest_state(1, {})
    assert (state, button) == (QUEST_STATE_NOT_STARTED, QUEST_ACCEPT_IMAGE)
    assert QUEST_DIALOG_IMAGE not in calls[1], "the second look is for buttons only"


def test_the_inference_is_refused_when_accept_has_no_crop(runner, monkeypatch):
    # "Accept didn't match" only means something if something looked for it.
    monkeypatch.setattr(vision, "wait_for_image_any", _on_screen(QUEST_DIALOG_IMAGE))
    monkeypatch.setattr(vision, "template_variant_paths",
                        lambda name, d: [] if name == QUEST_ACCEPT_IMAGE else ["x.png"])

    state, button, _ = runner._eclipse_quest_state(1, {})
    assert (state, button) == (QUEST_STATE_UNKNOWN, None)


def test_a_task_runs_on_the_dialog_and_accept_crops_alone(monkeypatch):
    # The minimum viable setup: no redeem crop anywhere, but the cycle can
    # still start, farm, and only stumble at the very last step.
    runner = PreflightRunner()
    monkeypatch.setattr(vision, "template_variant_paths",
                        lambda name, d: ["x.png"]
                        if name in (QUEST_ACCEPT_IMAGE, QUEST_DIALOG_IMAGE) else [])

    assert _preflight(runner) is True
    assert runner.cycles == 3
    assert "no redeem crop yet" in runner.said
