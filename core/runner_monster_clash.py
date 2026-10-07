"""Monster Clash (the Events menu's Battle Event), as one mixin.

Entered from the Events menu like the World Boss -- Events > Monster Clash >
Play Event > Play - Choose Stage, then the shared Select Stage + Start -- and
played like any stage. What is special comes once the map is cleared: now and
then a helicopter spawns instead of the Victory screen, and all that shows is
the "Game Results" button. About 15s later E boards it, and it flies to a
second map that starts empty -- Pre Start again (the task's Helicopter Macro
Operation, or the same one), Start Game, fight.

One repeat is one RUN, one map or two, the shape Boss Rush has (see
core/runner_boss_rush.py). Either map's result screen only leads back to the
lobby, so every repeat goes in through the Events menu again (see
MacroRunner._repeats_in_place).

Split out of core/runner.py like the other *Ops classes -- see core/runner.py,
which composes the mixins (MacroRunner). Methods here run with MacroRunner's
full self: shared state and helpers (_log, _checkpoint, _press_start_game,
...) resolve normally.
"""
import threading
import time

from . import vision
from . import window as wm
from .runner_constants import *  # noqa: F401,F403 -- the shared constants namespace


class MonsterClashOps:
    @staticmethod
    def _monster_clash_helicopter_task(task: dict) -> dict:
        """The task as the helicopter's map runs it: with the Helicopter Macro
        Operation when one is set, otherwise the first map's."""
        macro = str(task.get("helicopter_macro") or "").strip()
        return dict(task, macro=macro) if macro else dict(task)

    def _monster_clash_preflight(self, task: dict) -> bool:
        """Whether the crops the way in needs are on disk.

        Checked before the lobby is left, as Boss Rush does: a missing one
        otherwise fails at the screen it is needed on, and every recovery
        attempt pays the trip there again to learn the same thing.
        """
        needed = ("nav_event",) + MONSTER_CLASH_ENTRY_IMAGES + (GAME_RESULTS_IMAGE,)
        missing = [name for name in needed
                   if not vision.template_variant_paths(name, vision.UI_ASSETS_DIR)]
        if not missing:
            return True
        self._log(f"[Macro] Monster Clash: no crop yet for {', '.join(missing)} -- save one per name "
                  "via Settings > General > Image Manager. Skipping this task.")
        return False

    # ── Getting in ──────────────────────────────────────────────────────────

    def _run_monster_clash_setup(self, hwnd, stop_event: threading.Event) -> bool:
        """Lobby > Events > Monster Clash > Play Event > Play - Choose Stage,
        retried from the lobby like the other entries -- a failed attempt
        leaves nothing safe to assume about where it ended up. The shared
        Select Stage + Start tail (_enter_selected_stage) does the rest."""
        for attempt in range(1, MAP_SELECT_RETRY_ATTEMPTS + 1):
            if self._checkpoint(stop_event):
                return False
            if attempt > 1:
                self._log(f"[Macro] Retrying the Monster Clash entry from the lobby "
                          f"(attempt {attempt}/{MAP_SELECT_RETRY_ATTEMPTS})...")
            if self._reach_monster_clash_stage(hwnd, stop_event):
                return True
            if stop_event.is_set():
                return False
        self._log(f"[Macro] Couldn't reach Monster Clash after {MAP_SELECT_RETRY_ATTEMPTS} attempts -- "
                  "stopping.")
        return False

    def _reach_monster_clash_stage(self, hwnd, stop_event: threading.Event) -> bool:
        if not self._ensure_lobby(hwnd, stop_event):
            return False
        if self._checkpoint(stop_event):
            return False
        for name in ("nav_event",) + MONSTER_CLASH_ENTRY_IMAGES:
            self._set_status(action=f'Clicking "{name}"...')
            if self._click_found_image(hwnd, name, EVENT_SCREEN_TIMEOUT, stop_event) is None:
                self._spam_back_until_gone(hwnd, stop_event)
                return False
            if self._checkpoint(stop_event):
                return False
            # Each screen animates in behind the click.
            time.sleep(SETTLE_DELAY)
        return True

    # ── The run ─────────────────────────────────────────────────────────────

    def _play_monster_clash_run(self, hwnd, stop_event: threading.Event, task: dict,
                                default_walk_paths: dict, first_repeat: bool = True,
                                webhook: dict = None):
        """One whole run: the map, and the helicopter's map when one spawns.

        Returns what _play_one_match returns -- "win"/"loss" off the last
        result screen, "left", or None on failure/stop -- so _run_task's
        repeat, result and recovery handling apply unchanged.
        """
        if not self._run_prestart(hwnd, stop_event, task, default_walk_paths, first_repeat):
            return None
        if self._checkpoint(stop_event):
            return None
        self._log("[Macro] Pre Start finished -- starting the round.")
        if not self._press_start_game(hwnd, stop_event, task, webhook):
            return None

        self._set_status(action="Battle...")
        self._log("[Macro] Moving into Battle.")
        battle_blocks = self._begin_battle(task)
        result = self._wait_for_match_result(
            hwnd, stop_event, battle_blocks, first_repeat, task.get("macro"), task.get("mode"),
            self._wants_close_popup_watch(task), webhook, task, watch_helicopter=True)
        if result != "helicopter":
            return result
        if not self._board_monster_clash_helicopter(hwnd, stop_event):
            return None
        return self._fight_monster_clash_helicopter_map(hwnd, stop_event, task, default_walk_paths, webhook)

    def _monster_clash_game_results(self, hwnd):
        """The lone Game Results button a helicopter leaves on screen, or None."""
        try:
            return vision.find_image(hwnd, GAME_RESULTS_IMAGE, region=GAME_RESULTS_REGION)
        except vision.TemplateNotFound:
            return None

    def _board_monster_clash_helicopter(self, hwnd, stop_event: threading.Event) -> bool:
        """Board the helicopter with E once it takes boarders -- E again while
        the Game Results button stays up, since then the press was not taken."""
        self._log(f"[Macro] Monster Clash: a helicopter spawned -- boarding it about "
                  f"{MONSTER_CLASH_HELICOPTER_BOARD_AFTER:.0f}s after it showed up.")
        self._set_status(action="Monster Clash: waiting for the helicopter...")
        # The button has been up for MONSTER_CLASH_HELICOPTER_CONFIRM already.
        self._interruptible_sleep(
            MONSTER_CLASH_HELICOPTER_BOARD_AFTER - MONSTER_CLASH_HELICOPTER_CONFIRM, stop_event)
        for attempt in range(1, MONSTER_CLASH_HELICOPTER_BOARD_ATTEMPTS + 1):
            if self._checkpoint(stop_event):
                return False
            self._set_status(action="Monster Clash: boarding the helicopter...")
            if not wm.activate_window(hwnd):
                self._log("[Macro] Couldn't confirm focus before pressing E -- it may not register.")
            self._keyboard.tap(ord("E"))
            self._interruptible_sleep(MONSTER_CLASH_HELICOPTER_BOARD_VERIFY, stop_event)
            if self._checkpoint(stop_event):
                return False
            if self._monster_clash_game_results(hwnd) is None:
                self._log(f"[Macro] Monster Clash: boarded the helicopter (E, attempt {attempt}).")
                return True
            self._log(f"[Macro] Monster Clash: still on the cleared map after E (attempt {attempt}/"
                      f"{MONSTER_CLASH_HELICOPTER_BOARD_ATTEMPTS}).")
        self._log("[Macro] Monster Clash: couldn't board the helicopter -- abandoning this run.")
        self._save_debug_screenshot_unconditional(hwnd, "monster_clash_helicopter_not_boarded")
        return False

    def _fight_monster_clash_helicopter_map(self, hwnd, stop_event: threading.Event, task: dict,
                                            default_walk_paths: dict, webhook: dict = None):
        """Place every unit again on the helicopter's map, start, fight.

        A new map like any first entry, so its Pre Start runs in full --
        camera, Team Loadout, Once blocks. Ends on the ordinary Victory/Defeat
        screen, so it returns what a normal match does.
        """
        heli_task = self._monster_clash_helicopter_task(task)
        self._set_status(action="Monster Clash: flying to the next map...")
        # That map's own Start Game is the only sign it has loaded. Placing
        # before that would click into the flight.
        _, match = self._find_start_game_button(hwnd, stop_event, MONSTER_CLASH_HELICOPTER_MAP_TIMEOUT)
        if self._checkpoint(stop_event):
            return None
        if match is None:
            self._log(f"[Macro] Monster Clash: no Start Game on the helicopter's map after "
                      f"{MONSTER_CLASH_HELICOPTER_MAP_TIMEOUT:.0f}s -- placing anyway.")

        macro = heli_task.get("macro")
        self._log("[Macro] Monster Clash: the helicopter's map -- placing every unit again"
                  + (f' with "{macro}".' if macro else " (no Macro Operation set)."))
        if not self._run_prestart(hwnd, stop_event, heli_task, default_walk_paths, True):
            return None
        if self._checkpoint(stop_event):
            return None
        if not self._press_start_game(hwnd, stop_event, heli_task, webhook):
            return None

        self._set_status(action="Monster Clash: helicopter map battle...")
        battle_blocks = self._begin_battle(heli_task)
        return self._wait_for_match_result(
            hwnd, stop_event, battle_blocks, True, heli_task.get("macro"), heli_task.get("mode"),
            self._wants_close_popup_watch(heli_task), webhook, heli_task)
