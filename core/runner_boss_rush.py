"""Boss Rush, as one mixin.

A Boss Rush stage is entered like any other (Play > Boss Rush > map > Select
Stage > Start) and ends like any other (Victory/Defeat, then Repeat Stage or
Leave Stage), so _run_task drives it unchanged. What differs is the middle:
one "match" here is a whole RUN --

  1. Start Game at the spawn -- nothing is placed yet
  2. walk the recorded route from the spawn to gate k, E, Start Game
  3. clear the gate; three cards come up, one is taken, back at the spawn
  4. after the task's chosen gate (2..6) press Fight Boss instead of Continue
  5. the boss arena starts empty: place everything again, Start Game, fight

Units placed in the first gate stay placed through every later gate, so Pre
Start runs twice per run: in gate 1 (the task's Macro Operation) and in the
boss arena (the task's Boss Macro Operation, or the same one again).

The routes are recorded from the SPAWN, one per gate, and stored on the task
(gate_paths); a gate the task leaves unset uses the route shipped for its map
(core.paths._BUILTIN_BOSS_RUSH_GATE_PATHS). The game does not force an order,
so route k is simply "the k-th gate this run clears" -- whichever gate the
recording walks to.

Split out of core/runner.py like the other *Ops classes -- see core/runner.py,
which composes the mixins (MacroRunner). Methods here run with MacroRunner's
full self: shared state and helpers (_log, _checkpoint, _press_start_game,
...) resolve normally.
"""
import threading
import time

from . import paths as walk_paths
from . import vision
from . import window as wm
from .runner_constants import *  # noqa: F401,F403 -- the shared constants namespace

BOSS_CHOICE = "boss"
CONTINUE_CHOICE = "continue"


class BossRushOps:
    # ── The task's fields ───────────────────────────────────────────────────

    @staticmethod
    def _boss_rush_boss_gate(task: dict) -> int:
        """After which gate this task presses Fight Boss (2..6).

        Clamped rather than rejected: the game offers Fight Boss from gate 2
        on and forces it after gate 6, so nothing outside that range can be
        honoured, and the nearest value that can is what was meant.
        """
        try:
            gate = int(str(task.get("boss_after") or "").strip())
        except ValueError:
            gate = BOSS_RUSH_MIN_BOSS_GATE
        return max(BOSS_RUSH_MIN_BOSS_GATE, min(BOSS_RUSH_GATE_COUNT, gate))

    @staticmethod
    def _boss_rush_gate_paths(task: dict) -> list:
        """The task's gate routes, always BOSS_RUSH_GATE_COUNT long, "" where unset."""
        raw = task.get("gate_paths")
        routes = [str(name or "").strip() for name in raw] if isinstance(raw, (list, tuple)) else []
        routes = routes[:BOSS_RUSH_GATE_COUNT]
        return routes + [""] * (BOSS_RUSH_GATE_COUNT - len(routes))

    @classmethod
    def _boss_rush_routes(cls, task: dict) -> list:
        """(route, sprint) per gate: the task's own route where it set one,
        otherwise the route shipped for its map (core.paths), otherwise ("",
        False).

        Sprint is decided per gate, not per task: a shipped route was
        recorded sprinting and has to be replayed that way, while the task's
        own sprint switch describes how ITS recordings were walked -- a task
        mixing both needs both.
        """
        own = cls._boss_rush_gate_paths(task)
        own_sprint = bool(task.get("gate_sprint"))
        shipped = walk_paths.shipped_boss_rush_gate_paths(task.get("map"))
        routes = []
        for gate, route in enumerate(own):
            if route:
                routes.append((route, own_sprint))
            elif gate < len(shipped["gates"]):
                routes.append((shipped["gates"][gate], shipped["sprint"]))
            else:
                routes.append(("", False))
        return routes

    @staticmethod
    def _boss_rush_boss_task(task: dict) -> dict:
        """The task as the boss fight runs it: with the Boss Macro Operation
        when one is set, otherwise the gates' own. Everything else -- map,
        mode, fishing -- stays the task's."""
        boss_macro = str(task.get("boss_macro") or "").strip()
        return dict(task, macro=boss_macro) if boss_macro else dict(task)

    # ── Refusing a task that cannot run, before it enters anything ──────────

    def _boss_rush_missing_crops(self, task: dict) -> list:
        """Which reference images this task needs that are not on disk."""
        needed = list(BOSS_RUSH_IMAGE_NAMES)
        map_image = BOSS_RUSH_MAP_IMAGES.get(task.get("map"))
        if map_image:
            needed.append(map_image)
        needed += list(BOSS_RUSH_GATE_CLEAR_IMAGES)
        return [name for name in needed
                if not vision.template_variant_paths(name, vision.UI_ASSETS_DIR)]

    def _boss_rush_preflight(self, task: dict) -> bool:
        """Whether this task has everything a run needs.

        Checked from disk before the lobby is left. Every one of these
        otherwise fails minutes into the run -- a missing route at the gate
        it leads to, a missing crop at the screen it reads -- and the task's
        recovery attempts would each pay those minutes again to learn the
        same thing. Only the routes up to the boss gate are required; the
        rest are never walked.
        """
        map_name = task.get("map")
        if map_name not in BOSS_RUSH_MAP_IMAGES:
            self._log(f'[Macro] Boss Rush: unknown map "{map_name}" -- expected one of '
                      f"{list(BOSS_RUSH_MAP_ORDER)}. Skipping this task.")
            return False

        boss_gate = self._boss_rush_boss_gate(task)
        routes = [route for route, _ in self._boss_rush_routes(task)[:boss_gate]]
        unset = [str(gate) for gate, name in enumerate(routes, 1) if not name]
        empty = [f'{gate} ("{name}")' for gate, name in enumerate(routes, 1)
                 if name and not walk_paths.load_path(name).get("events")]
        missing = self._boss_rush_missing_crops(task)

        problems = []
        if unset:
            problems.append(f"no route set for gate {', '.join(unset)}")
        if empty:
            problems.append(f"the recording for gate {', '.join(empty)} is empty or gone")
        if missing:
            problems.append(f"missing crops: {', '.join(missing)} (Assets/ui/<name>/, each "
                            "folder's _WHAT_TO_CROP.txt says what to capture)")
        if not problems:
            return True
        self._log(f"[Macro] Boss Rush (boss after gate {boss_gate}): {'; '.join(problems)}. "
                  "Record the routes under the task's Gate Paths -- skipping this task.")
        return False

    # ── Getting in ──────────────────────────────────────────────────────────

    def _select_boss_rush_map(self, hwnd, stop_event: threading.Event, map_name: str) -> bool:
        """Click the map's card on the Boss Rush screen (Play > Boss Rush is
        already open). The shared Select Stage + Start tail does the rest."""
        image = BOSS_RUSH_MAP_IMAGES.get(map_name)
        if image is None:
            self._log(f'[Macro] Unknown Boss Rush map "{map_name}" -- expected one of '
                      f"{list(BOSS_RUSH_MAP_ORDER)}.")
            return False
        self._set_status(action=f'Selecting "{map_name}"...')
        if self._click_found_image(hwnd, image, BOSS_RUSH_SCREEN_TIMEOUT, stop_event) is None:
            return False
        # Select Stage animates in behind the click.
        time.sleep(SETTLE_DELAY)
        return not self._checkpoint(stop_event)

    # ── The run ─────────────────────────────────────────────────────────────

    def _play_boss_rush_run(self, hwnd, stop_event: threading.Event, task: dict,
                            default_walk_paths: dict, first_repeat: bool = True,
                            webhook: dict = None):
        """One whole run, from the spawn to the boss's Victory/Defeat.

        Returns what _play_one_match returns -- "win"/"loss" off the result
        screen, "left", or None on failure/stop -- so _run_task's repeat,
        result and recovery handling apply to Boss Rush unchanged. A gate
        lost along the way ends the run on the ordinary Defeat screen and is
        reported as that "loss".
        """
        boss_gate = self._boss_rush_boss_gate(task)
        routes = self._boss_rush_routes(task)
        self._log(f"[Macro] Boss Rush run: {boss_gate} gate(s), then the boss.")

        # The spawn has its own Start Game, pressed before anything is placed:
        # the run's units go down inside the first gate.
        self._set_status(action="Boss Rush: starting the run...")
        if not self._press_start_game(hwnd, stop_event, task, webhook):
            return None
        self._interruptible_sleep(BOSS_RUSH_SPAWN_SETTLE, stop_event)
        if self._checkpoint(stop_event):
            return None

        battle_blocks = []
        for gate in range(1, boss_gate + 1):
            self._set_status(action=f"Boss Rush: gate {gate}/{boss_gate}...")
            route, sprint = routes[gate - 1]
            if not self._enter_boss_rush_gate(hwnd, stop_event, gate, route, sprint):
                return None

            if gate == 1:
                if not self._run_prestart(hwnd, stop_event, task, default_walk_paths,
                                          first_repeat, team_check=True):
                    return None
                if self._checkpoint(stop_event):
                    return None
            else:
                self._log(f"[Macro] Boss Rush: gate {gate} -- the units from gate 1 are still "
                          "placed, starting it.")
            if not self._press_start_game(hwnd, stop_event, task, webhook):
                return None

            self._set_status(action=f"Boss Rush: gate {gate}/{boss_gate} -- battle...")
            # Battle state is reset once, for the first gate: the units stay,
            # so an Upgrade block half-way through its list at the end of
            # gate 2 carries on in gate 3 rather than starting over.
            if gate == 1:
                battle_blocks = self._begin_battle(task)
            self._reset_boss_rush_card_watch()
            result = self._wait_for_match_result(
                hwnd, stop_event, battle_blocks, first_repeat, task.get("macro"),
                task.get("mode"), self._wants_close_popup_watch(task), webhook, task,
                watch_gate_clear=True)
            if result != "gate_cleared":
                return result

            choice = self._boss_rush_after_gate(hwnd, stop_event, gate,
                                                want_boss=gate == boss_gate)
            if choice is None:
                return None
            if choice == BOSS_CHOICE:
                break
            # Back at the spawn -- no image says the teleport is done, so the
            # next walk waits it out rather than losing its first steps.
            self._interruptible_sleep(BOSS_RUSH_SPAWN_SETTLE, stop_event)
            if self._checkpoint(stop_event):
                return None

        return self._fight_boss_rush_boss(hwnd, stop_event, task, default_walk_paths,
                                          first_repeat, webhook)

    def _enter_boss_rush_gate(self, hwnd, stop_event: threading.Event, gate: int,
                              route: str, sprint: bool) -> bool:
        """Walk the spawn->gate route and get inside, pressing E if the route
        did not.

        Inside a gate is where its Start Game is, so that button appearing IS
        the "the gate let us in" check -- there is no separate one to get
        wrong. Same two-step as the Eclipse NPC visit: a route recorded with
        E in it is in by the time the short wait ends; one recorded without
        it gets the tap. The tap only happens when nothing opened, so a gate
        that is already loading never gets a second E.
        """
        data = walk_paths.load_path(route) if route else {}
        events = data.get("events") or []
        if not events:
            self._log(f"[Macro] Boss Rush: no recorded route for gate {gate} -- record it "
                      "under the task's Gate Paths.")
            return False

        self._log(f'[Macro] Boss Rush: walking to gate {gate} ("{route}"'
                  f'{", sprinting" if sprint else ""}).')
        self._set_status(action=f"Boss Rush: walking to gate {gate}...")
        if not wm.activate_window(hwnd):
            self._log("[Macro] Couldn't confirm focus before the walk -- it may not register.")
        walk_paths.replay_events(events, self._keyboard, stop_event, sprint=sprint)
        if self._checkpoint(stop_event):
            return False

        _, match = self._find_start_game_button(hwnd, stop_event, BOSS_RUSH_GATE_PRECHECK)
        if match is None:
            if self._checkpoint(stop_event):
                return False
            self._log(f"[Macro] Boss Rush: gate {gate} hasn't opened -- pressing E in case the "
                      "route was recorded without it.")
            if not wm.activate_window(hwnd):
                self._log("[Macro] Couldn't confirm focus before pressing E -- it may not register.")
            self._keyboard.tap(ord("E"))
            _, match = self._find_start_game_button(hwnd, stop_event, BOSS_RUSH_GATE_ENTER_TIMEOUT)
        if match is None:
            if self._checkpoint(stop_event):
                return False
            self._log(f"[Macro] Boss Rush: no Start Game {BOSS_RUSH_GATE_ENTER_TIMEOUT:.0f}s after "
                      f'pressing E at gate {gate} -- the route "{route}" doesn\'t end at the gate '
                      "(or the camera was turned before it). Abandoning this run.")
            self._save_debug_screenshot_unconditional(hwnd, f"boss_rush_gate_{gate}_not_entered")
            return False
        self._log(f"[Macro] Boss Rush: inside gate {gate}.")
        return True

    # ── After a gate ────────────────────────────────────────────────────────

    def _boss_rush_gate_cleared(self, hwnd) -> bool:
        """Whether a gate has just been cleared -- polled by the battle loop.

        Any of the post-gate screens counts: the card choice, or Fight Boss /
        Continue. Which one the game shows first does not matter here;
        _boss_rush_after_gate deals with all of them in whatever order.
        """
        try:
            match, name = vision.find_image_any(hwnd, BOSS_RUSH_GATE_CLEAR_IMAGES)
        except vision.TemplateNotFound:
            # Every crop missing. The preflight refuses such a task, so this
            # is a crop deleted mid-run -- quiet here, it is polled per tick.
            return False
        if match is None:
            self._measure_boss_rush_card(hwnd)
            return False
        debug_path = self._debug_save(hwnd, name, match)
        suffix = f" Debug: {debug_path}" if debug_path else ""
        self._log(f'[Macro] Boss Rush: gate cleared ("{name}" is up, score '
                  f'{match["score"]:.2f}).{suffix}')
        return True

    def _reset_boss_rush_card_watch(self) -> None:
        """Fresh card measurement for the gate about to be fought."""
        self._boss_rush_card_best = None
        self._boss_rush_card_checked_at = 0.0
        self._boss_rush_card_reported_at = time.time()
        self._boss_rush_card_shot = False

    def _measure_boss_rush_card(self, hwnd) -> None:
        """Say how close the card screen came when it did not match.

        The card choice is up for 20s and then the game picks by itself, so a
        crop that scores just under the threshold loses the run silently:
        the gate never reads as cleared and the macro waits in it forever.
        This turns that into a number in the log, plus one screenshot of the
        frame that came closest, to lower the crop's sensitivity or cut a
        better one from.
        """
        now = time.time()
        if now - getattr(self, "_boss_rush_card_checked_at", 0.0) < BOSS_RUSH_CARD_MEASURE_INTERVAL:
            return
        self._boss_rush_card_checked_at = now
        try:
            gray = vision.capture_game_gray(hwnd)
            if gray is None:
                return
            best = vision.find_in_gray_multiscale_diagnostic(gray, BOSS_RUSH_CARD_IMAGE)["best"]
        except Exception:
            return  # purely a report -- never let it break the battle loop
        if best is None:
            return
        score = best["score"]
        previous = getattr(self, "_boss_rush_card_best", None)
        self._boss_rush_card_best = score if previous is None else max(previous, score)
        needed = vision.threshold_for(BOSS_RUSH_CARD_IMAGE)

        if score >= BOSS_RUSH_CARD_NEAR_MISS and not getattr(self, "_boss_rush_card_shot", False):
            self._boss_rush_card_shot = True
            path = self._save_debug_screenshot_unconditional(hwnd, "boss_rush_card_near_miss")
            self._log(f'[Macro] Boss Rush: something close to "{BOSS_RUSH_CARD_IMAGE}" is on screen '
                      f"(score {score:.2f}, needs {needed:.2f}) -- not taken as the card screen."
                      + (f" Screenshot: {path}" if path else ""))
            self._boss_rush_card_reported_at = now
        elif now - getattr(self, "_boss_rush_card_reported_at", 0.0) >= BOSS_RUSH_CARD_REPORT_INTERVAL:
            self._boss_rush_card_reported_at = now
            self._log(f"[Macro] Boss Rush: no card screen yet (best \"{BOSS_RUSH_CARD_IMAGE}\" "
                      f"score this gate: {self._boss_rush_card_best:.2f}, needs {needed:.2f}).")

    def _boss_rush_find(self, hwnd, name: str):
        try:
            return vision.find_image(hwnd, name)
        except vision.TemplateNotFound:
            return None

    def _take_boss_rush_card(self, hwnd, gate: int) -> None:
        """Take a card from the three-card choice: the middle one.

        Same click Expedition's upgrade pick uses (_dismiss_reward_card_if_found):
        nothing reads the cards, the middle of the screen is simply where
        the middle card sits.
        """
        self._log(f"[Macro] Boss Rush: gate {gate} card choice is up -- taking the middle card.")
        if not wm.activate_window(hwnd):
            self._log("[Macro] Couldn't confirm focus before taking the card -- the click may "
                      "not register.")
        left, top, _, _ = wm.get_window_rect_screen(hwnd)
        self._mouse.click(left + self._coords["screen_middle_x"],
                          top + self._coords["screen_middle_y"])

    def _boss_rush_after_gate(self, hwnd, stop_event: threading.Event, gate: int,
                              want_boss: bool):
        """Take the card, then Fight Boss or Continue -- in whatever order the
        game shows them.

        Returns "boss" once Fight Boss was pressed, "continue" once the run is
        headed back to the spawn, or None when the screens never resolved (the
        caller abandons the run and the task recovers from the lobby).

        Finished means none of the post-gate screens has been up for
        BOSS_RUSH_POST_GATE_QUIET -- they come one after another with a gap in
        between, so the first empty frame is not the end. After the first
        gate there is nothing to choose (no boss yet), so the card alone
        finishes it; from the second gate on, a choice has to have been made.

        Fight Boss and Continue render together. If only the one this gate
        does NOT want is up for BOSS_RUSH_BUTTON_SETTLE, the other one's crop
        is not matching -- the run stops there rather than press the wrong
        one: a Continue in place of Fight Boss runs gates the task did not
        ask for, and a Fight Boss in place of Continue ends the run early.
        """
        self._set_status(action=f"Boss Rush: gate {gate} cleared...")
        wanted_image = BOSS_RUSH_FIGHT_BOSS_IMAGE if want_boss else BOSS_RUSH_CONTINUE_IMAGE
        other_image = BOSS_RUSH_CONTINUE_IMAGE if want_boss else BOSS_RUSH_FIGHT_BOSS_IMAGE
        wanted_label = "Fight Boss" if want_boss else "Continue"
        started = time.time()
        last_seen = started
        choice = None
        only_other_since = None
        while time.time() - started < BOSS_RUSH_POST_GATE_TIMEOUT:
            if self._checkpoint(stop_event):
                return None
            now = time.time()

            if self._boss_rush_find(hwnd, BOSS_RUSH_CARD_IMAGE) is not None:
                last_seen = now
                self._take_boss_rush_card(hwnd, gate)
                self._interruptible_sleep(BOSS_RUSH_CLICK_SETTLE, stop_event)
                continue

            wanted = self._boss_rush_find(hwnd, wanted_image)
            if wanted is not None:
                last_seen = now
                only_other_since = None
                debug_path = self._debug_save(hwnd, wanted_image, wanted)
                suffix = f" Debug: {debug_path}" if debug_path else ""
                self._log(f"[Macro] Boss Rush: gate {gate} done -- pressing {wanted_label} "
                          f'(score {wanted["score"]:.2f}).{suffix}')
                if not wm.activate_window(hwnd):
                    self._log(f"[Macro] Couldn't confirm focus before pressing {wanted_label} -- "
                              "the click may not register.")
                vision.click_match(self._mouse, hwnd, wanted)
                choice = BOSS_CHOICE if want_boss else CONTINUE_CHOICE
                self._interruptible_sleep(BOSS_RUSH_CLICK_SETTLE, stop_event)
                continue

            if self._boss_rush_find(hwnd, other_image) is not None:
                last_seen = now
                if only_other_since is None:
                    only_other_since = now
                elif now - only_other_since >= BOSS_RUSH_BUTTON_SETTLE:
                    self._log(f'[Macro] Boss Rush: after gate {gate} only "{other_image}" is '
                              f'showing, never "{wanted_image}" -- that crop isn\'t matching '
                              "your screen. Not pressing the wrong button; abandoning this run.")
                    self._save_debug_screenshot_unconditional(hwnd, "boss_rush_choice_not_found")
                    return None
            else:
                only_other_since = None
                if now - last_seen >= BOSS_RUSH_POST_GATE_QUIET:
                    if choice is not None:
                        return choice
                    if gate < BOSS_RUSH_MIN_BOSS_GATE:
                        return CONTINUE_CHOICE

            self._interruptible_sleep(BOSS_RUSH_POST_GATE_POLL, stop_event)

        self._log(f"[Macro] Boss Rush: the screens after gate {gate} didn't resolve within "
                  f"{BOSS_RUSH_POST_GATE_TIMEOUT:.0f}s"
                  + ("" if choice else f' -- "{wanted_image}" never showed up')
                  + ". Abandoning this run.")
        self._save_debug_screenshot_unconditional(hwnd, "boss_rush_after_gate_timeout")
        return None

    # ── The boss ────────────────────────────────────────────────────────────

    def _fight_boss_rush_boss(self, hwnd, stop_event: threading.Event, task: dict,
                              default_walk_paths: dict, first_repeat: bool,
                              webhook: dict = None):
        """Place every unit again in the empty boss arena, start, fight.

        Ends on the ordinary Victory/Defeat screen, so it returns what a
        normal match does and _run_task takes it from there.
        """
        boss_task = self._boss_rush_boss_task(task)
        self._set_status(action="Boss Rush: entering the boss fight...")
        # The arena's own Start Game is the only sign it has loaded. Placing
        # before that would click into the teleport.
        _, match = self._find_start_game_button(hwnd, stop_event, BOSS_RUSH_BOSS_ARENA_TIMEOUT)
        if self._checkpoint(stop_event):
            return None
        if match is None:
            self._log(f"[Macro] Boss Rush: no Start Game in the boss arena after "
                      f"{BOSS_RUSH_BOSS_ARENA_TIMEOUT:.0f}s -- placing anyway.")

        macro = boss_task.get("macro")
        self._log("[Macro] Boss Rush: boss arena -- placing every unit again"
                  + (f' with "{macro}".' if macro else " (no Macro Operation set)."))
        if not self._run_prestart(hwnd, stop_event, boss_task, default_walk_paths,
                                  first_repeat, team_check=True):
            return None
        if self._checkpoint(stop_event):
            return None
        if not self._press_start_game(hwnd, stop_event, boss_task, webhook):
            return None

        self._set_status(action="Boss Rush: boss fight...")
        self._log("[Macro] Boss Rush: fighting the boss.")
        battle_blocks = self._begin_battle(boss_task)
        return self._wait_for_match_result(
            hwnd, stop_event, battle_blocks, first_repeat, boss_task.get("macro"),
            boss_task.get("mode"), self._wants_close_popup_watch(boss_task), webhook, boss_task)
