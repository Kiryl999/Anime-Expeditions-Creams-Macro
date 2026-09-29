"""The Eclipse quest line (secret unit), as one mixin.

Unlike every other mode in this codebase, this one is a CYCLE rather than a
stage entry. One "task" here is the whole loop:

  1. enter Crimson Shore, walk to the quest NPC, press E, accept the quest
  2. leave the map
  3. find whichever story map is now carrying the Eclipse marker, enter it
  4. play the event, taking the configured card every time the choice is up
  5. on Victory: souls not capped yet -> Retry and play it again (back to 4)
                 souls capped     -> leave
  6. back to Crimson Shore, talk to the same NPC, hand the souls in
  7. that is one cycle; the task's repeat count decides how many run

Steps 1 and 6 are the same walk to the same NPC and differ only in which
button is waiting in the dialog, so they share one method. Step 3 is the
part with no precedent in the other modes: which map carries the event is
random, so the macro cannot search for a map by name the way Story does --
it searches for the MARKER and works out which map it landed on afterwards.

Split out of core/runner.py mechanically like the other *Ops classes -- see
core/runner.py, which composes the mixins (MacroRunner). Methods here run
with MacroRunner's full self: shared state and helpers (_log, _checkpoint,
_click_found_image, ...) resolve normally.
"""
import threading
import time

from . import paths as walk_paths
from . import stage_select
from . import vision
from . import window as wm
from .runner_constants import *  # noqa: F401,F403 -- the shared constants namespace


class EclipseOps:
    # ── The pieces the battle loop polls for ────────────────────────────────

    @staticmethod
    def _wants_eclipse_card_watch(task: dict) -> bool:
        """Whether this task can be shown the mid-battle card choice.

        Only the Eclipse mode can, so nothing else pays for the search --
        the same rule _wants_portal_offer_watch applies to portal offers.
        """
        return (task or {}).get("mode") == "eclipse"

    def _eclipse_card_image(self, task: dict) -> str:
        """Which card reference image this task's configured choice maps to.

        Falls back to the first of ECLIPSE_CARD_ORDER rather than failing:
        an unset or stale field should still farm, just not necessarily with
        the card the user meant, and the log line says which one it used.
        """
        choice = str(task.get("eclipse_card") or "").strip().lower()
        image = ECLIPSE_CARD_IMAGES.get(choice)
        if image is None:
            fallback = ECLIPSE_CARD_ORDER[0]
            self._log(f'[Macro] Eclipse: no card choice set (or "{choice}" is not one of '
                      f'{list(ECLIPSE_CARD_IMAGES)}) -- defaulting to {fallback}.')
            return ECLIPSE_CARD_IMAGES[fallback]
        return image

    def _take_eclipse_card_if_found(self, hwnd, card_image: str) -> bool:
        """Click the configured card if the mid-battle choice is up.

        Deliberately NOT the shape of _take_portal_offer_if_found, which
        clicks the middle of the screen because the three portals are
        interchangeable to it. Here the whole point is WHICH card gets taken
        -- the choice is what fills the bar and decides which souls drop --
        and the cards do not keep a fixed position in the row, so each is
        found by its own image and clicked where it was actually found.

        Polled repeatedly for the whole match, not once: the choice comes
        back every few waves, unlike a portal offer (one per round).

        Returns whether a card was actually taken, so the caller can log the
        count rather than one line per poll tick.
        """
        try:
            match = vision.find_image(hwnd, card_image)
        except vision.TemplateNotFound:
            # No crop for this card yet -- the run is still playable, it just
            # will not steer the choice. Silent here on purpose: this is
            # polled several times a second and _run_eclipse_battle says it
            # once up front instead.
            return False
        if match is None:
            return False

        debug_path = self._debug_save(hwnd, card_image, match)
        suffix = f" Debug: {debug_path}" if debug_path else ""
        self._log(f'[Macro] Eclipse card choice is up -- taking "{card_image}" '
                  f'(score {match["score"]:.2f}).{suffix}')
        if not wm.activate_window(hwnd):
            self._log("[Macro] Couldn't confirm focus before taking the card -- "
                      "the click may not register.")
        vision.click_match(self._mouse, hwnd, match)
        return True

    def _eclipse_souls_are_full(self, hwnd) -> bool:
        """Whether the Victory screen's loot row shows a capped soul stack.

        This is the farm loop's only stop condition, which makes a MISSING
        crop dangerous in a specific way: "not found" and "not full yet" look
        identical, so without the guard below a missing reference would farm
        forever. TemplateNotFound is therefore reported and treated as "stop
        farming", not as "keep going".
        """
        try:
            match = vision.find_image(hwnd, SOULS_FULL_IMAGE)
        except vision.TemplateNotFound as exc:
            self._log(f"[Macro] Eclipse: {exc} -- without it there is no way to tell a full "
                      "soul stack from a partial one, so this cycle stops farming here.")
            return True
        if match is None:
            return False
        debug_path = self._debug_save(hwnd, SOULS_FULL_IMAGE, match)
        suffix = f" Debug: {debug_path}" if debug_path else ""
        self._log(f'[Macro] Eclipse: soul stack is full (score {match["score"]:.2f}).{suffix}')
        return True

    # ── Finding the map the event landed on ─────────────────────────────────

    def _find_eclipse_story_map(self, hwnd, stop_event: threading.Event):
        """Which story map is carrying the Eclipse marker right now.

        The macro cannot search for the map by name the way Story does --
        which map runs the event is random every cycle. So it searches for
        the marker, then asks which map's name label sits under it.

        Returns (map_name, marker_match). map_name is None when the marker
        was found but no label could be tied to it -- the caller can still
        click the marker in that case, it just cannot say which map it is.
        Returns (None, None) when there is no marker on screen at all.

        Assumes the Story carousel is already open; it does not navigate.
        """
        try:
            marker = vision.wait_for_image(hwnd, ECLIPSE_MARKER_IMAGE,
                                           timeout=ECLIPSE_MARKER_TIMEOUT,
                                           stop_event=stop_event)
        except vision.TemplateNotFound as exc:
            self._log(f"[Macro] Eclipse: {exc}")
            return None, None
        if marker is None:
            return None, None

        debug_path = self._debug_save(hwnd, ECLIPSE_MARKER_IMAGE, marker)
        suffix = f" Debug: {debug_path}" if debug_path else ""
        self._log(f'[Macro] Eclipse marker found (score {marker["score"]:.2f}).{suffix}')

        map_name = self._eclipse_map_under(hwnd, marker)
        if map_name:
            self._log(f'[Macro] Eclipse event is running on "{map_name}".')
        else:
            self._log("[Macro] Eclipse marker found but no map label could be matched under it "
                      "-- clicking the marker's own card anyway.")
        return map_name, marker

    def _eclipse_map_under(self, hwnd, marker: dict) -> str:
        """The story map whose carousel name label sits under `marker`.

        Reuses the same Assets/maps/<map>/ label crops the ordinary map
        search uses (see core.stage_select), so a map that can already be
        picked by a Task can be recognized here with no new reference images.

        Nearest label BELOW the marker and within ECLIPSE_MARKER_MAP_MAX_DX
        horizontally -- the marker sits above its own card's name, so a label
        that is far to the side belongs to a neighbouring card, and one that
        is above the marker is not a card label at all.
        """
        best_name, best_dx = None, None
        for map_name in CHALLENGE_STORY_MAPS:
            try:
                match = vision.find_image(hwnd, map_name,
                                          threshold=stage_select.MATCH_THRESHOLD,
                                          template_dir=vision.MAPS_DIR)
            except vision.TemplateNotFound:
                continue  # that map has no label crop yet -- skip, don't fail
            if match is None:
                continue
            if match["cy"] < marker["cy"]:
                continue
            dx = abs(match["cx"] - marker["cx"])
            if dx > ECLIPSE_MARKER_MAP_MAX_DX:
                continue
            if best_dx is None or dx < best_dx:
                best_name, best_dx = map_name, dx
        return best_name

    # ── Talking to the quest NPC ────────────────────────────────────────────

    def _eclipse_npc_walk_path(self, task: dict):
        """(path name, sprint) for the route to the quest NPC, taken from the
        task's own Macro Operation.

        The route is NOT a field on the Eclipse task. It lives where every
        other recorded route lives: a Custom Walk Path block inside the
        Macro Operation the task already selects (Macro Manager > record the
        walk to the NPC > set the block to Custom). That keeps one way of
        recording and picking a route in the whole app instead of a second,
        Eclipse-only one, and it means the sprint toggle on that block
        applies here exactly as it does everywhere else -- a route recorded
        at sprint speed only reaches its spot at sprint speed.

        Returns (None, False) when the template has no custom walk block, so
        the caller can say what to fix rather than walking nowhere.
        """
        macro_name = task.get("macro")
        if not macro_name:
            return None, False
        from . import templates as tpl
        data = tpl.load_template(macro_name)
        blocks = data.get("blocks") or {}
        if not isinstance(blocks, dict):
            return None, False
        prestart = blocks.get("prestart") or blocks.get("before") or []
        for block in prestart:
            if not isinstance(block, dict) or block.get("type") != "walk_path":
                continue
            if block.get("mode") == "custom" and block.get("pathName"):
                return block["pathName"], bool(block.get("sprint"))
        # A template saved before the walk became a real block keeps it at
        # the top level -- the same legacy shape _run_walk_path_block
        # migrates (see core/runner_blocks.py).
        legacy = blocks.get("walk")
        if isinstance(legacy, dict) and legacy.get("mode") == "custom" and legacy.get("pathName"):
            return legacy["pathName"], bool(legacy.get("sprint"))
        return None, False

    def _talk_to_quest_npc(self, hwnd, stop_event: threading.Event, walk_path: str,
                             sprint: bool = False, task: dict = None,
                             press_states: tuple = ()):
        """Walk the recorded route to the NPC, read the quest state, and press
        the button ONLY if that state is one the caller asked to act on.

        Returns (state, pressed). The state is always reported, whether or not
        anything was pressed, so the caller can decide what to do next.

        `press_states` is the whole safety story. The dialog's button is
        whatever the quest state makes it, so an unconditional press does
        something DIFFERENT depending on state -- and at the start of a cycle,
        on a quest a crash left running, that difference is "hand in the
        partial soul stack you spent the last hour farming". So a caller says
        which states it is prepared to act on: the accept visit passes
        (NOT_STARTED,) and the redeem visit passes (ACTIVE,). Anything else is
        read and reported, never clicked. An empty press_states looks without
        touching anything.

        The E press is handled BOTH ways on purpose. The walk recorder now
        watches E (see core.paths._WATCHED_KEYS), so a route recorded with
        the interact press in it talks to the NPC at exactly the point the
        player pressed it -- but a route recorded before that, or by someone
        who simply walked and stopped, has no E in it at all. So: walk,
        check whether the dialog opened, and only tap E if it did not. That
        covers both recordings without an extra E ever reaching an
        already-open dialog, where it would advance or close it.

        Assumes the character is already in the map.
        """
        if not walk_path:
            self._log("[Macro] Eclipse: the task's Macro Operation has no Custom Walk Path "
                      "block -- record the route to the quest NPC in Macro Manager and set "
                      "that block to Custom.")
            return None, False

        data = walk_paths.load_path(walk_path)
        if not data or not data.get("events"):
            self._log(f'[Macro] Eclipse: walk path "{walk_path}" is empty or missing.')
            return None, False

        self._set_status(action="Walking to the quest NPC...")
        self._log(f'[Macro] Eclipse: walking to the quest NPC ("{walk_path}").')
        if not wm.activate_window(hwnd):
            self._log("[Macro] Couldn't confirm focus before the walk -- it may not register.")
        walk_paths.replay_events(data["events"], self._keyboard, stop_event, sprint=sprint)
        if self._checkpoint(stop_event):
            return None, False

        # Reading the state IS the dialog check: a quest button on screen can
        # only be there because the dialog opened. So there is no separate
        # "did it open" step to get wrong, and no blind click at wherever a
        # button usually sits.
        #
        # Short wait first, for a route that presses E itself. It has to be a
        # WAIT and not an instant look -- the walk ends when its last key is
        # released, which is before the game has drawn anything.
        self._set_status(action="Waiting for the NPC dialog...")
        state, button, _ = self._eclipse_quest_state(
            hwnd, task, stop_event, timeout=ECLIPSE_DIALOG_PRECHECK)
        if state == QUEST_STATE_UNKNOWN:
            # Nothing yet. Either the route never pressed E, or it did and the
            # dialog is slower than the short wait -- a tap costs nothing in
            # the second case, because a dialog that is already open would
            # have matched above.
            self._log("[Macro] Eclipse: no quest button yet -- tapping E in case the route "
                      "was recorded without the interact press.")
            self._keyboard.tap(ord("E"))
            if self._checkpoint(stop_event):
                return None, False
            state, button, _ = self._eclipse_quest_state(
                hwnd, task, stop_event, timeout=ECLIPSE_DIALOG_TIMEOUT)

        if button is None:
            self._log_missing_quest_dialog(hwnd, stop_event, task)
            return state, False

        if state not in press_states:
            self._log(f'[Macro] Eclipse: the NPC is offering "{button}", which is not what this '
                      f"step came for -- leaving it alone rather than pressing it.")
            return state, False

        self._set_status(action="Talking to the quest NPC...")
        if self._click_found_image(hwnd, button,
                                   ECLIPSE_QUEST_BUTTON_TIMEOUT, stop_event) is None:
            return state, False
        time.sleep(SETTLE_DELAY)
        return state, True

    def _log_missing_quest_dialog(self, hwnd, stop_event: threading.Event = None,
                                    task: dict = None) -> None:
        """Say WHICH failure happened, as precisely as the crops on disk allow.

        Three genuinely different causes end up here and they need different
        fixes, so guessing one wording for all of them sends people looking in
        the wrong place -- "the walk didn't end on the NPC" was being printed
        while the dialog was visibly open and still animating in.

        This WAITS for quest_dialog rather than glancing at it, for the same
        reason the button read does: by the time the button search has given
        up the dialog may still be arriving.
        """
        missing = self._eclipse_missing_button_crops(task)
        try:
            open_dialog = vision.wait_for_image(
                hwnd, QUEST_DIALOG_IMAGE, timeout=ECLIPSE_DIALOG_PRECHECK,
                stop_event=stop_event) is not None
            know_dialog = True
        except vision.TemplateNotFound:
            open_dialog, know_dialog = False, False

        if missing and len(missing) == len(self._quest_button_names(task)):
            where = ", ".join(missing)
            self._log(f"[Macro] Eclipse: none of the quest button crops exist yet ({where}). "
                      "Nothing can be read off the dialog until at least one of them is in "
                      "Assets/ui/ -- see each folder's _WHAT_TO_CROP.txt.")
            return
        if not know_dialog:
            self._log("[Macro] Eclipse: no quest button matched. Either the walk didn't end on "
                      f"the NPC, or the crops are too tight/loose -- add Assets/ui/"
                      f"{QUEST_DIALOG_IMAGE}/ to tell those two apart.")
            return
        if open_dialog:
            self._log("[Macro] Eclipse: the NPC dialog IS open but no quest button matched -- "
                      + (f"these crops are still missing: {', '.join(missing)}." if missing
                         else "the existing crops are cropped too loosely or too tightly."))
        else:
            self._log("[Macro] Eclipse: the NPC dialog never opened -- the walk didn't end "
                      "on the NPC.")


    # ── Picking up where a crashed cycle left off ───────────────────────────

    def _eclipse_redeem_image(self, task: dict) -> str:
        """Which redeem button this task's farmed souls should be handed to.

        Which soul you carry follows from which card you farmed, so the card
        choice already on the task answers this -- no second setting.

        A card with no redeem button of its own (Neutral, or anything added
        later) returns None, and the caller falls back to whichever redeem
        button is actually on screen. Better than guessing a name: the NPC
        only ever offers the one that matches what you are carrying.
        """
        choice = str(task.get("eclipse_card") or "").strip().lower()
        return QUEST_REDEEM_IMAGES.get(choice)

    def _quest_button_names(self, task: dict) -> list:
        """Every quest button worth looking for, best candidate first.

        The redeem button matching what this task farmed comes first so that
        it wins on a tick where a loose crop would otherwise match two, then
        the remaining redeem buttons, then Accept.
        """
        names = []
        preferred = self._eclipse_redeem_image(task or {})
        if preferred:
            names.append(preferred)
        names += [QUEST_REDEEM_IMAGES[k] for k in QUEST_REDEEM_ORDER
                  if QUEST_REDEEM_IMAGES[k] not in names]
        names.append(QUEST_ACCEPT_IMAGE)
        return names

    def _eclipse_missing_button_crops(self, task: dict = None) -> list:
        """Which quest-button reference images do not exist on disk yet.

        Checked BEFORE a cycle goes anywhere, because the failure is
        otherwise invisible until the worst possible moment: vision's
        find_image_any raises the instant EVERY candidate is missing, so the
        polled wait for the dialog returns immediately without ever polling,
        and the run has already spent a couple of minutes entering the map
        and walking to the NPC to find that out (reported live, twice, read
        as a timing bug because the give-up looked instant).
        """
        return [name for name in self._quest_button_names(task)
                if not vision.template_variant_paths(name, vision.UI_ASSETS_DIR)]

    def _wait_any_quest_image(self, hwnd, names, timeout: float,
                                stop_event: threading.Event = None):
        """wait_for_image_any, with "none of these exist on disk" folded into
        "none of these are on screen".

        vision raises rather than returning when EVERY candidate is missing,
        and it raises on the first poll tick -- so an unguarded call here
        looks like an instant give-up and reads as a timing bug. The caller
        separates the two cases from the crops on disk instead.
        """
        try:
            return vision.wait_for_image_any(hwnd, tuple(names), timeout=timeout,
                                             stop_event=stop_event)
        except vision.TemplateNotFound:
            return None, None

    def _state_for_button(self, name: str) -> str:
        return QUEST_STATE_NOT_STARTED if name == QUEST_ACCEPT_IMAGE else QUEST_STATE_ACTIVE

    def _eclipse_quest_state(self, hwnd, task: dict = None,
                               stop_event: threading.Event = None,
                               timeout: float = None):
        """Whether a quest is already running, read off the open NPC dialog.

        This is what makes the cycle restartable. A run that dies mid-cycle
        (crash, Stop, disconnect) leaves the macro with no idea how far it
        got, and blindly starting at "accept the quest" on an already-running
        one would press the wrong button in a dialog that is not offering it.

        Three things can answer the question, and they are tried in that
        order of directness:

          1. the Accept button is up      -> nothing is running
          2. a Redeem button is up        -> something is running
          3. only the dialog FRAME is up  -> the dialog is open and is not
             offering Accept, so something is running

        (3) is what makes the whole cycle testable off two crops. Reading
        state used to need a Redeem crop, which cannot be captured until 150
        souls have already been farmed -- a chicken-and-egg the quest_dialog
        crop breaks, since the absence of Accept in an open dialog says the
        same thing a Redeem button would.

        (3) only holds when the Accept crop actually EXISTS -- otherwise
        "Accept didn't match" means "nobody looked", and the state stays
        unknown rather than being guessed from a search that never ran.

        POLLED throughout. The walk ends the instant its last key is
        released, but the game still has to register the interact and animate
        the dialog in -- one immediate check lands in that gap and reports an
        empty screen, indistinguishable from the walk having missed the NPC.

        Returns (state, button_name, match). button_name is None whenever
        nothing pressable was found, including in case (3).
        """
        buttons = self._quest_button_names(task)
        timeout = ECLIPSE_DIALOG_TIMEOUT if timeout is None else timeout

        # Buttons first in the candidate order so that on a tick where both
        # a button and the frame are visible, the button wins.
        match, name = self._wait_any_quest_image(
            hwnd, buttons + [QUEST_DIALOG_IMAGE], timeout, stop_event)
        if name is None:
            return QUEST_STATE_UNKNOWN, None, None

        if name != QUEST_DIALOG_IMAGE:
            return self._report_quest_button(hwnd, name, match)

        # Only the frame so far. The buttons render inside it and may still be
        # arriving, so give them their own moment before reading their absence
        # as meaning anything.
        match, name = self._wait_any_quest_image(
            hwnd, buttons, ECLIPSE_BUTTON_SETTLE, stop_event)
        if name is not None:
            return self._report_quest_button(hwnd, name, match)

        if vision.template_variant_paths(QUEST_ACCEPT_IMAGE, vision.UI_ASSETS_DIR):
            self._log("[Macro] Eclipse: the dialog is open and is not offering Accept -- "
                      "so a quest is already running.")
            return QUEST_STATE_ACTIVE, None, None

        self._log(f'[Macro] Eclipse: the dialog is open, but with no "{QUEST_ACCEPT_IMAGE}" '
                  "crop there is nothing to tell a fresh quest from a running one.")
        return QUEST_STATE_UNKNOWN, None, None

    def _report_quest_button(self, hwnd, name: str, match: dict):
        """Log a found quest button and turn it into a state.

        Reports only what it SAW -- what to do about it is the caller's
        decision, and saying so here made the log claim decisions that were
        never taken.
        """
        state = self._state_for_button(name)
        debug_path = self._debug_save(hwnd, name, match)
        suffix = f" Debug: {debug_path}" if debug_path else ""
        verdict = ("no quest is running" if state == QUEST_STATE_NOT_STARTED
                   else "a quest is already running")
        self._log(f'[Macro] Eclipse: the NPC is offering "{name}" '
                  f'(score {match["score"]:.2f}) -- {verdict}.{suffix}')
        return state, name, match

    @staticmethod
    def _eclipse_should_farm_first(state: str) -> bool:
        """Whether to skip the accept step and go straight to farming.

        UNKNOWN deliberately counts as "already running". The two ways of
        being wrong are not symmetric:

          - guessing "running" when it is not: no map carries the Eclipse
            marker, the cycle notices within seconds and nothing is lost
          - guessing "not started" when it is: the macro hunts for an Accept
            button the dialog is not offering, and a cycle is burned on a
            quest that was already half farmed

        So the guess goes to the recoverable side.
        """
        return state in (QUEST_STATE_ACTIVE, QUEST_STATE_UNKNOWN)

    # ── The cycle ───────────────────────────────────────────────────────────

    def _eclipse_quest_task(self, task: dict) -> dict:
        """A plain Story task for Crimson Shore, used to reach the quest NPC.

        The NPC stands in the map whatever act/difficulty it was entered on,
        so this takes the cheapest one (see ECLIPSE_QUEST_STAGE). It carries
        the real task's Macro Operation so nothing downstream has to special-
        case a synthetic task, but the visit never presses Start Game -- stage
        entry ends at the teleport-in, which is all the visit needs.
        """
        return {
            "mode": "story",
            "map": ECLIPSE_QUEST_MAP,
            "stage": ECLIPSE_QUEST_STAGE,
            "difficulty": ECLIPSE_QUEST_DIFFICULTY,
            "play_mode": "solo",
            "macro": task.get("macro"),
            "repeat": 1,
        }

    def _eclipse_visit_npc(self, hwnd, stop_event: threading.Event, task: dict,
                            walk_path: str, sprint: bool, press_states: tuple,
                            coords: dict, scroll_power: int, scroll_nudges: int,
                            webhook: dict = None):
        """Enter Crimson Shore, talk to the quest NPC, leave again.

        Returns (state, pressed) from the dialog, or (None, False) if the map
        was never reached.

        Leaving uses the in-match To Lobby button rather than a result screen:
        the visit never starts a match, so there is no Victory to leave from
        (see _leave_match_to_lobby, shared with the Leave at Minute block).
        """
        quest_task = self._eclipse_quest_task(task)
        self._set_status(action=f"Entering {ECLIPSE_QUEST_MAP} for the quest NPC...")
        if not self._run_task_setup(hwnd, stop_event, quest_task, "story", ECLIPSE_QUEST_MAP,
                                    coords, scroll_power, scroll_nudges, webhook):
            self._log(f"[Macro] Eclipse: couldn't reach {ECLIPSE_QUEST_MAP} for the quest NPC.")
            return None, False
        if self._checkpoint(stop_event):
            return None, False

        state, pressed = self._talk_to_quest_npc(hwnd, stop_event, walk_path, sprint,
                                                 task, press_states)
        # Leave even when the dialog went wrong -- otherwise a failed visit
        # strands the run standing in a story map with no way back to the
        # lobby, and every later step starts from the wrong place.
        if not self._leave_match_to_lobby(hwnd, stop_event, reason="Eclipse NPC visit"):
            # The visit never started a match, so the in-match To Lobby button
            # may not even be up. Falling through is fine: the cycle's own
            # failure path backs out to the lobby, and a successful visit that
            # could not leave still reports what the dialog said.
            self._log("[Macro] Eclipse: couldn't leave the map with the To Lobby button -- "
                      "the cycle's lobby recovery will take it from here.")
        return state, pressed

    def _run_eclipse_farm(self, hwnd, stop_event: threading.Event, task: dict,
                            default_walk_paths: dict, coords: dict, scroll_power: int,
                            scroll_nudges: int, webhook: dict = None) -> bool:
        """Play the Eclipse event over and over until the soul stack caps.

        Whether the stack is full is only ever readable on a Victory screen
        (see _eclipse_souls_are_full), so the loop is "play a run, look at the
        result, decide" rather than anything that tracks a count itself.

        Bounded by ECLIPSE_MAX_RUNS_PER_CYCLE: the stop condition is a single
        image match, and a crop that silently never matches would otherwise
        farm the same event until the user noticed.
        """
        for run_index in range(1, ECLIPSE_MAX_RUNS_PER_CYCLE + 1):
            if self._checkpoint(stop_event):
                return False
            self._set_status(action=f"Eclipse run {run_index}...")
            if not self._enter_eclipse_map(hwnd, stop_event, task, coords,
                                           scroll_power, scroll_nudges, webhook):
                return False
            if self._checkpoint(stop_event):
                return False

            result = self._play_one_match(hwnd, stop_event, task, default_walk_paths,
                                          first_repeat=True, webhook=webhook)
            if result is None:
                if stop_event.is_set():
                    return False
                self._log(f"[Macro] Eclipse: run {run_index} didn't finish cleanly -- "
                          "backing out to the lobby and trying the cycle again.")
                return False
            if result != "win":
                self._log(f"[Macro] Eclipse: run {run_index} ended in \"{result}\" -- "
                          "no souls from it, going again.")
                continue

            if self._eclipse_souls_are_full(hwnd):
                self._log(f"[Macro] Eclipse: soul stack capped after {run_index} run(s) "
                          "-- off to hand them in.")
                return True
            self._log(f"[Macro] Eclipse: run {run_index} won, stack not full yet -- going again.")

        self._log(f"[Macro] Eclipse: {ECLIPSE_MAX_RUNS_PER_CYCLE} runs without the soul stack "
                  f'ever reading as full. Either "{SOULS_FULL_IMAGE}" doesn\'t match your '
                  "screen, or something is wrong -- stopping this cycle rather than farming on.")
        return False

    def _run_eclipse_cycle(self, hwnd, stop_event: threading.Event, task: dict,
                             default_walk_paths: dict, coords: dict, scroll_power: int,
                             scroll_nudges: int, webhook: dict = None) -> bool:
        """One full quest cycle: take it, farm it, hand it in.

        Starts by ASKING the game what state the quest is in rather than
        assuming a fresh one -- a previous cycle may have died halfway (crash,
        Stop, disconnect) and left a partially farmed quest running, which
        must be continued, not restarted.
        """
        walk_path, sprint = self._eclipse_npc_walk_path(task)
        if not walk_path:
            return False

        state, accepted = self._eclipse_visit_npc(
            hwnd, stop_event, task, walk_path, sprint,
            press_states=(QUEST_STATE_NOT_STARTED,),
            coords=coords, scroll_power=scroll_power,
            scroll_nudges=scroll_nudges, webhook=webhook)
        if state is None or self._checkpoint(stop_event):
            return False

        if state == QUEST_STATE_UNKNOWN:
            self._log("[Macro] Eclipse: couldn't read the quest state off the dialog -- "
                      "assuming a quest is running and going farming, which is the "
                      "recoverable guess (see _eclipse_should_farm_first).")
        if not accepted and not self._eclipse_should_farm_first(state):
            self._log("[Macro] Eclipse: no quest is running and the Accept press didn't land "
                      "-- abandoning this cycle rather than farming an event that isn't up.")
            return False
        if accepted:
            self._log("[Macro] Eclipse: quest accepted -- looking for the map carrying the event.")

        if not self._run_eclipse_farm(hwnd, stop_event, task, default_walk_paths,
                                      coords, scroll_power, scroll_nudges, webhook):
            return False
        if self._checkpoint(stop_event):
            return False

        _, redeemed = self._eclipse_visit_npc(
            hwnd, stop_event, task, walk_path, sprint,
            press_states=(QUEST_STATE_ACTIVE,),
            coords=coords, scroll_power=scroll_power,
            scroll_nudges=scroll_nudges, webhook=webhook)
        if not redeemed:
            self._log("[Macro] Eclipse: the souls were farmed but handing them in didn't go "
                      "through -- they stay in the inventory for the next cycle to redeem.")
            return False
        self._log("[Macro] Eclipse: cycle complete -- souls handed in.")
        return True

    # ── Entering the map the event landed on ────────────────────────────────

    def _open_story_carousel(self, hwnd, stop_event: threading.Event) -> bool:
        """Lobby -> Play -> Story, leaving the map carousel on screen.

        The same front half _reach_map_selected runs, minus the map search --
        the Eclipse event's map cannot be searched for by name, so the search
        is replaced by the marker hunt in _enter_eclipse_map. The nav_back
        shortcut is kept for the same reason it exists there: if the gamemode
        menu is already open, Play does not exist on that screen and waiting
        for the lobby would just burn the timeout.
        """
        try:
            already_open = vision.find_image(hwnd, "nav_back") is not None
        except vision.TemplateNotFound as exc:
            self._log(f"[Macro] {exc}")
            return False
        if already_open:
            self._log("[Macro] Already on the gamemode menu -- skipping the lobby and Play.")
        else:
            if not self._ensure_lobby(hwnd, stop_event):
                return False
            if self._checkpoint(stop_event):
                return False
            if not self._click_play(hwnd, stop_event):
                return False
            if self._checkpoint(stop_event):
                return False
        return self._click_gamemode(hwnd, stop_event, "story", wait_for_menu=not already_open)

    def _enter_eclipse_map(self, hwnd, stop_event: threading.Event, task: dict, coords: dict,
                             scroll_power: int, scroll_nudges: int, webhook: dict = None) -> bool:
        """Open the Story carousel, find the map carrying the Eclipse marker,
        and enter its Eclipse stage.

        Clicking prefers the map's NAME once the marker has been tied to one:
        stage_select.find_and_click_map scrolls the carousel and verifies its
        own click, where the marker match is a single position on whatever
        happened to be visible at the time. The marker is the fallback for
        when no label matched -- a card that can be seen can be clicked.
        """
        self._set_status(action="Looking for the Eclipse event...")
        if not self._open_story_carousel(hwnd, stop_event):
            self._spam_back_until_gone(hwnd, stop_event)
            return False
        if self._checkpoint(stop_event):
            return False

        map_name, marker = self._find_eclipse_story_map(hwnd, stop_event)
        if marker is None:
            self._log("[Macro] Eclipse: no story map is carrying the event marker. Either the "
                      "quest isn't running, or the event hasn't come up yet.")
            self._spam_back_until_gone(hwnd, stop_event)
            return False

        if map_name:
            clicked = stage_select.find_and_click_map(
                self._mouse, hwnd, map_name, self._log, stop_event=stop_event,
                scroll_power=scroll_power, scroll_nudges=scroll_nudges)
        else:
            vision.click_match(self._mouse, hwnd, marker)
            clicked = True
        if not clicked:
            self._spam_back_until_gone(hwnd, stop_event)
            return False
        if self._checkpoint(stop_event):
            return False
        self._interruptible_sleep(SETTLE_DELAY, stop_event)

        # The act picker is shared with the map's ordinary acts, so landing on
        # it proves nothing on its own -- the Eclipse symbol is what says this
        # is the event and not Act 1. Without that check a missed click would
        # quietly farm a normal stage that drops no souls at all.
        try:
            eclipse = vision.wait_for_image(hwnd, ECLIPSE_ACT_IMAGE,
                                            timeout=ECLIPSE_MARKER_TIMEOUT,
                                            stop_event=stop_event)
        except vision.TemplateNotFound as exc:
            self._log(f"[Macro] Eclipse: {exc} -- can't confirm this is the Eclipse stage "
                      "rather than the map's ordinary acts, so this run is skipped.")
            self._spam_back_until_gone(hwnd, stop_event)
            return False
        if eclipse is None:
            self._log("[Macro] Eclipse: the act screen isn't showing the Eclipse symbol -- "
                      "the card click probably landed on the wrong map.")
            self._spam_back_until_gone(hwnd, stop_event)
            return False

        entry_task = dict(task)
        entry_task["play_mode"] = "solo"
        return self._enter_selected_stage(hwnd, stop_event, entry_task, "story", coords, webhook)

    def _run_eclipse_task(self, hwnd, stop_event: threading.Event, task: dict,
                            task_index: int, task_count: int, coords: dict,
                            scroll_power: int, scroll_nudges: int,
                            default_walk_paths: dict, webhook: dict = None) -> bool:
        """An Eclipse task: `repeat` full quest cycles, back to back.

        Same contract as _run_task, which hands off to this: returns False
        only when the whole run should stop (Stop was pressed), True for
        everything else -- including giving up on this task -- so one bad
        cycle never ends an unattended overnight run.
        """
        cycles = max(1, int(task.get("repeat") or 1))
        card = str(task.get("eclipse_card") or ECLIPSE_CARD_ORDER[0]).lower()

        # Refuse up front rather than discovering this at the NPC. With
        # nothing readable the dialog can never be understood, so every cycle
        # would enter Crimson Shore, walk the route, fail, and recover --
        # minutes per cycle to learn something knowable from disk in
        # microseconds. Checked per task, not per cycle: dropping a crop in
        # mid-run should take effect on the next Start, which is also when
        # vision's template cache is reloaded.
        def have(name):
            return bool(vision.template_variant_paths(name, vision.UI_ASSETS_DIR))

        have_accept = have(QUEST_ACCEPT_IMAGE)
        redeem_present = [n for n in QUEST_REDEEM_IMAGES.values() if have(n)]
        if not have_accept and not redeem_present:
            self._log(f'[Macro] Eclipse: there is no "{QUEST_ACCEPT_IMAGE}" crop and no redeem '
                      "crop either, so the NPC dialog can't be read at all -- this task is "
                      f'skipped. Capture "{QUEST_ACCEPT_IMAGE}" first: it is the one that '
                      "needs no farming to see (Assets/ui/ has a _WHAT_TO_CROP.txt per "
                      "folder), and together with "
                      f'"{QUEST_DIALOG_IMAGE}" it is enough to run a whole cycle.')
            return True
        if not have_accept:
            self._log(f'[Macro] Eclipse: no "{QUEST_ACCEPT_IMAGE}" crop -- a fresh quest '
                      "cannot be recognized, so every visit reads as \"already running\" "
                      "and no new quest is ever taken.")
        elif not have(QUEST_DIALOG_IMAGE) and not redeem_present:
            self._log(f'[Macro] Eclipse: only "{QUEST_ACCEPT_IMAGE}" is available. A running '
                      f'quest is recognized by "{QUEST_DIALOG_IMAGE}" being up without it, so '
                      "capture that one next or a running quest reads as unknown.")
        if not redeem_present:
            self._log("[Macro] Eclipse: no redeem crop yet "
                      f"({', '.join(QUEST_REDEEM_IMAGES.values())}) -- farming works, but "
                      "handing the souls in will fail until one exists. Capture it from the "
                      "dialog once a stack is full.")

        walk_path, _ = self._eclipse_npc_walk_path(task)
        if not walk_path:
            self._log("[Macro] Eclipse: the task's Macro Operation has no Custom Walk Path "
                      "block, so there is no route to the quest NPC -- record one in Macro "
                      "Manager, set that block to Custom, and Start again.")
            return True
        self._current_task = task
        self._active_task_progress = {
            "index": task_index, "count": task_count,
            "map": "Eclipse", "next_repeat": 1, "repeat_total": cycles,
        }
        self._log(f"[Macro] Task {task_index}/{task_count}: Eclipse quest x{cycles} "
                  f"(taking {card} cards).")

        for cycle in range(1, cycles + 1):
            if self._checkpoint(stop_event):
                return False
            self._active_task_progress["next_repeat"] = cycle
            self._set_status(current_task=f"{task_index} / {task_count}",
                             current_repeat=f"{cycle} / {cycles}", map="Eclipse",
                             action="Starting quest cycle...", mode="eclipse",
                             stage="-", difficulty="-", play_mode="solo",
                             macro=task.get("macro") or "-")
            self._log(f"[Macro] Eclipse: cycle {cycle}/{cycles}.")

            if self._run_eclipse_cycle(hwnd, stop_event, task, default_walk_paths,
                                       coords, scroll_power, scroll_nudges, webhook):
                continue
            if stop_event.is_set():
                return False
            # A cycle can fail anywhere -- mid-dialog, mid-farm, mid-redeem --
            # and wherever it stopped is not somewhere the next cycle can
            # start from. Back out to a known place first; the next cycle then
            # re-reads the quest state at the NPC and picks up correctly
            # whatever this one left behind.
            self._log(f"[Macro] Eclipse: cycle {cycle}/{cycles} didn't complete -- "
                      "returning to the lobby before the next one.")
            if not self._recover_to_lobby(hwnd, stop_event):
                return not stop_event.is_set()
        return True
