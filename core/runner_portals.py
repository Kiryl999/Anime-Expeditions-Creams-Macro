"""Portals: a mode-agnostic way to search for and activate a portal.

From the lobby, open the Inventory (nav_inv), switch to the Portals tab
(normal_portals_nav), and pick the task's portal on the picker there. The
same picker opens again from the Victory screen's "Select Portal" button to
queue up the next one. The picker selection drives off the PORTAL_SEARCHES
regions (search box + the portal-card list), so it works however the picker
was opened.

The Summer event's own "Portal Mode" card used to be a second way in; it was
retired, since every portal -- Summer or not -- is reachable from here.
"""
import threading
import time

from . import keys
from . import pacing
from . import vision
from .runner_constants import *  # noqa: F401,F403 -- the shared constants namespace


class PortalsOp:
    def _run_portal_selection_from_inventory(self, hwnd, stop_event: threading.Event,
                                              query: str = "summer") -> bool:
        """Lobby -> Inventory -> Portals tab -> search `query` -> click the
        tier card -> activate, as one restartable unit.

        The game-agnostic lead-in: unlike the Event kind (reached through the
        event gamemode), the portal picker here is opened from the Inventory's
        Portals tab. On any failure it backs out to the lobby so the retry
        loop starts clean, same as every other nav method.
        """
        if not self._ensure_lobby(hwnd, stop_event):
            return False
        if self._click_found_image(hwnd, "nav_inv", EVENT_SCREEN_TIMEOUT, stop_event) is None:
            self._spam_back_until_gone(hwnd, stop_event)
            return False
        if self._checkpoint(stop_event):
            return False
        time.sleep(SETTLE_DELAY)

        if self._click_found_image(hwnd, "normal_portals_nav", EVENT_SCREEN_TIMEOUT, stop_event) is None:
            self._spam_back_until_gone(hwnd, stop_event)
            return False
        if self._checkpoint(stop_event):
            return False
        time.sleep(SETTLE_DELAY)

        return self._select_portal_on_picker(hwnd, stop_event, query)

    def _focus_portal_search(self, hwnd, stop_event: threading.Event) -> bool:
        """Click into the portal picker's search box and empty it.

        Aiming. A saved point (Settings > Debug > Macro Coordinates > "Portal
        Search") wins outright. Otherwise the shipped `portal_search` crop is
        matched inside PORTAL_SEARCHES["search"] and its CENTRE is clicked --
        but that crop is the placeholder word "Search...", 47x10px at the LEFT
        end of the bar, so its centre is near the left edge of the input and
        lands outside it entirely on a layout where the bar sits differently.
        Reported live as "clicks too far left". Nothing here can measure the
        real field, which is exactly why the override exists rather than a
        different hardcoded number.

        Clearing. END, then backspaces -- NOT the Ctrl+A + Delete used by
        every other input in this codebase. Those type into a box the click
        certainly landed in; this one can miss, and a Ctrl that misses reaches
        Roblox, where it toggles the camera and leaves the rest of the run
        fighting the view. Backspace and END are inert when they miss. END,
        not HOME: backspace deletes to the LEFT of the cursor, so it has to
        start from the end of the text.
        """
        point = self._optional_cxy("portal_search")
        if point is not None:
            self._log(f"[Macro] Using the manual portal-search click point "
                      f"({point[0]}, {point[1]}).")
            self._click_ref(hwnd, point[0], point[1])
        elif self._click_found_image(hwnd, "portal_search", EVENT_SCREEN_TIMEOUT, stop_event,
                                      region=PORTAL_SEARCHES.get("search")) is None:
            self._log("[Macro] Couldn't find the portal search box. If it is visibly on screen, "
                      "set its click point under Settings > Debug > Macro Coordinates "
                      '("Portal Search") -- the shipped crop is the "Search..." placeholder and '
                      "does not survive every layout.")
            return False
        if self._checkpoint(stop_event):
            return False

        # Unpaced per key, one Macro Speed pause after the lot -- the same
        # rule Keyboard.type_text follows per character. Paced, these 33 keys
        # paid the pause 33 times -- ~20s of an idle-looking search box at a
        # 600ms Macro Speed (reported live on a Remote Desktop setup) -- for
        # keys a text box takes as fast as they come.
        self._keyboard.tap(keys.VK_END, pace=False)
        for _ in range(PORTAL_SEARCH_CLEAR_KEYS):
            self._keyboard.tap(keys.VK_BACK, pace=False)
        pacing.action_pause()
        return True

    def _portal_list_region(self):
        """The box to look for portal cards in, in the docked window's
        1152x756 reference space.

        A saved override (Settings > Debug > Macro Coordinates > "Portal Card
        List") wins; otherwise the built-in PORTAL_SEARCHES["portals"]. All
        four values have to be set for an override to count -- a half-filled
        box is treated as unset rather than guessed at, the same rule the
        other optional coordinates use.
        """
        values = [self._coords.get(f"portal_list_{axis}") for axis in ("x", "y", "w", "h")]
        if all(v not in (None, "") for v in values):
            try:
                x, y, w, h = (int(v) for v in values)
            except (TypeError, ValueError):
                pass
            else:
                if w > 0 and h > 0:
                    return (x, y, w, h)
        return tuple(int(v) for v in PORTAL_SEARCHES["portals"])

    def _find_portal_card(self, hwnd, stop_event: threading.Event, candidates: tuple):
        """Locate a portal card on the picker, region first then whole window.

        PORTAL_SEARCHES["portals"] is a hardcoded box, and a box is only ever
        right for the layout it was measured on. Confirmed live: a setup whose
        search field sits 189px right of the shipped one puts the card list
        past that box's right edge entirely, so every card search failed with
        "No portal card found" while the card was plainly on screen -- and the
        same crop matched fine when the picker was reached the other way.

        So the box is treated as a hint, not a boundary: it is searched first
        (it disambiguates when several portals are on screen), and only if
        nothing is there does the search widen to the whole window. Widening
        is safe here because the query has already filtered the list down.

        Waited for rather than looked at once -- the post-victory picker opens
        over the result screen and is still filtering for a moment.

        Returns (match, name), or (None, None) when nothing was found.
        """
        region = self._portal_list_region()
        try:
            match, name = vision.wait_for_image_any(
                hwnd, candidates, region=region,
                timeout=PORTAL_CARD_TIMEOUT, stop_event=stop_event)
            if match is not None:
                return match, name
            if stop_event is not None and stop_event.is_set():
                return None, None

            match, name = vision.wait_for_image_any(
                hwnd, candidates, timeout=PORTAL_CARD_TIMEOUT, stop_event=stop_event)
            if match is not None:
                self._log(f'[Macro] Portal card "{name}" was found outside the searched list area '
                          f'{region} -- your picker sits somewhere it does not cover. The pick still '
                          f'works, but every one of them now wastes {PORTAL_CARD_TIMEOUT:.0f}s on that '
                          f'first pass. Set the box under Settings > Debug > Macro Coordinates '
                          f'("Portal Card List") to get those seconds back.')
                return match, name
        except vision.TemplateNotFound as exc:
            # Only when NOT ONE candidate has a crop on disk.
            self._log(f"[Macro] {exc}")
        return None, None

    def _select_portal_on_picker(self, hwnd, stop_event: threading.Event,
                                 query: str = "summer") -> bool:
        """Search an already-open portal picker for `query`, click the matching
        card, then activate -- driven by the PORTAL_SEARCHES regions (search
        box + portal-card list) so it's agnostic to how the picker was
        reached (the Inventory Portals tab, or the Victory screen's Select
        Portal). `query` is what gets typed into the search box, and it also
        names the card crop to look for first (see the candidate list below).

        The search is typed EVERY time, never skipped for a card that already
        looks listed. The portals look alike in the picker -- the same frame
        and art, only the name printed on the card differs -- so an image
        match cannot tell one portal from another reliably (several shipped
        PORTAL_CARD_IMAGE crops show no name at all). The game's own search
        filters by that name; once it has, whichever portal card is left is
        the one that was asked for.
        """
        self._set_status(action="Selecting portal...")

        # "<query>_portal" then "<query>" first, so a portal whose card needs
        # its own crop can get one (Settings > General > Image Manager).
        # PORTAL_CARD_IMAGE stays last as the generic card for every portal,
        # which is only safe because the list has been filtered by the typed
        # name by the time it is looked for.
        slug = "".join(c if c.isalnum() else "_" for c in query.strip().lower()).strip("_")
        candidates = [n for n in (f"{slug}_portal", slug, PORTAL_CARD_IMAGE) if n]
        candidates = list(dict.fromkeys(candidates))  # de-dup, keep priority order

        # Focus + clear the search box, then type. Was a blind click on the
        # region centre with no check that anything was hit at all.
        if not self._focus_portal_search(hwnd, stop_event):
            self._spam_back_until_gone(hwnd, stop_event)
            return False
        self._log(f'[Macro] Searching the portal picker for "{query}".')
        self._keyboard.type_text(query)
        self._interruptible_sleep(SETTLE_DELAY, stop_event)
        if self._checkpoint(stop_event):
            return False

        match, found_name = self._find_portal_card(hwnd, stop_event, tuple(candidates))
        if match is None:
            self._log(f'[Macro] No "{query}" portal card found, on the picker or anywhere on screen '
                      f'(searched for {", ".join(candidates)}). Check that the Portal Name matches the '
                      f'name on the portal. If the card is visible, add a crop of it to '
                      f'"{PORTAL_CARD_IMAGE}" via Settings > General > Image Manager -- best just the '
                      f'portal art without its name, so the one crop fits every portal.')
            # Taken before backing out, while the filtered list is still up:
            # it shows at once whether the search matched nothing, the text
            # never reached the box, or the card is there and no crop fits.
            self._save_debug_screenshot_unconditional(hwnd, "portal_card_not_found")
            self._spam_back_until_gone(hwnd, stop_event)
            return False
        self._log(f'[Macro] Found the "{query}" portal card via "{found_name}" '
                  f'(score {match["score"]:.2f}) -- clicking it.')
        vision.click_match(self._mouse, hwnd, match)
        if self._checkpoint(stop_event):
            return False
        self._interruptible_sleep(SETTLE_DELAY, stop_event)

        # Confirm (Activate Portal on entry; the picker's Select button)
        # lives in the portal_activate folder.
        #
        # Verified rather than fire-and-forget: this is the last click before
        # the stage screen, and nothing downstream would ever notice it had
        # been dropped -- the run would just wait out SOLO_START_TIMEOUT on a
        # Start button that was never going to appear, because the picker was
        # still up. `nav_start` counts as proof too, for the layouts where the
        # picker stays drawn behind the stage screen for a moment.
        if not self._click_and_verify_gone(hwnd, stop_event, "portal_activate",
                                           EVENT_SCREEN_TIMEOUT, success_name="nav_start"):
            self._spam_back_until_gone(hwnd, stop_event)
            return False
        return not self._checkpoint(stop_event)

    def _select_portal_post_victory(self, hwnd, stop_event: threading.Event,
                                    query: str = "summer") -> bool:
        """Post-victory: click the Victory screen's "Select Portal" button,
        then pick the next portal with `query` on the same picker the entry
        uses (see _select_portal_on_picker).
        """
        self._set_status(action="Clicking Select Portal...")
        if self._click_found_image(hwnd, "select_new_portal", EVENT_SCREEN_TIMEOUT, stop_event) is None:
            self._spam_back_until_gone(hwnd, stop_event)
            return False
        if self._checkpoint(stop_event):
            return False
        time.sleep(SETTLE_DELAY)
        return self._select_portal_on_picker(hwnd, stop_event, query)
