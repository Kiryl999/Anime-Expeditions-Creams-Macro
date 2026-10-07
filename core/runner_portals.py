"""Portals: a mode-agnostic way to search for and activate a portal.

From the lobby, open the Inventory (nav_inv), switch to the Portals tab
(normal_portals_nav), and pick the task's portal on the picker there. The
picker selection drives off the PORTAL_SEARCHES regions (search box + the
portal-card list).

That picker is only the way IN. A won round ends on the game's three-portal
offer, and the portal taken there starts its round by itself -- see
_carry_on_after_portal_win. It used to end on a Victory screen whose "Select
Portal" button reopened the picker; the game's October 2026 update dropped
both.

The Summer event's own "Portal Mode" card used to be a second way in; it was
retired, since every portal -- Summer or not -- is reachable from here.
"""
import re
import threading
import time

from . import config
from . import keys
from . import pacing
from . import vision
from .runner_constants import *  # noqa: F401,F403 -- the shared constants namespace


def _portal_slug(query: str) -> str:
    """The Portal Name as an image name: lowercase, anything but letters and
    digits turned into underscores ("Winter Rift" -> "winter_rift")."""
    return "".join(c if c.isalnum() else "_" for c in query.strip().lower()).strip("_")


def _portal_name_image(query: str) -> str:
    """The name-crop folder for a Portal Name (see PORTAL_NAME_IMAGE_PREFIX),
    or None when the query leaves nothing to name it by.

    A trailing word "portal" is dropped, so "summer" and "Summer Portal" --
    both fine to type into the game's search -- share one folder,
    portal_name_summer, rather than each needing its own crop.
    """
    slug = re.sub(r"(?:^|_)portal$", "", _portal_slug(query))
    return f"{PORTAL_NAME_IMAGE_PREFIX}{slug}" if slug else None


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
        """Click into the portal picker's search box and make sure it is empty.

        Aiming. A saved point (Settings > Debug > Macro Coordinates > "Portal
        Search") wins outright. Otherwise the shipped `portal_search` crop is
        matched inside PORTAL_SEARCHES["search"] and its CENTRE is clicked --
        but that crop is the placeholder word "Search...", 47x10px at the LEFT
        end of the bar, so its centre is near the left edge of the input and
        lands outside it entirely on a layout where the bar sits differently.
        Reported live as "clicks too far left". Nothing here can measure the
        real field, which is exactly why the override exists rather than a
        different hardcoded number.

        Clearing. Only when the box may hold text. The game draws the
        "Search..." placeholder only while the box is empty -- and that
        placeholder IS the shipped crop, so a box found by it has nothing to
        clear. A saved point gets the same check first (see
        _portal_search_is_empty). Clearing a box that is already empty cost
        33 keys and a Macro Speed pause on every single pick.

        When it does clear: END, then backspaces -- NOT the Ctrl+A + Delete
        used by every other input in this codebase. Those type into a box the
        click certainly landed in; this one can miss, and a Ctrl that misses
        reaches Roblox, where it toggles the camera and leaves the rest of the
        run fighting the view. Backspace and END are inert when they miss.
        END, not HOME: backspace deletes to the LEFT of the cursor, so it has
        to start from the end of the text.
        """
        point = self._optional_cxy("portal_search")
        if point is not None:
            self._log(f"[Macro] Using the manual portal-search click point "
                      f"({point[0]}, {point[1]}).")
            # Looked at before the click, while nothing has touched the box.
            empty = self._portal_search_is_empty(hwnd, point)
            self._click_ref(hwnd, point[0], point[1])
        elif self._click_found_image(hwnd, "portal_search", EVENT_SCREEN_TIMEOUT, stop_event,
                                      region=PORTAL_SEARCHES.get("search")) is None:
            self._log("[Macro] Couldn't find the portal search box. If it is visibly on screen, "
                      "set its click point under Settings > Debug > Macro Coordinates "
                      '("Portal Search") -- the shipped crop is the "Search..." placeholder and '
                      "does not survive every layout.")
            return False
        else:
            empty = True
        if self._checkpoint(stop_event):
            return False
        if empty:
            return True

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

    def _portal_search_is_empty(self, hwnd, point) -> bool:
        """Whether the search box at a saved click point shows its "Search..."
        placeholder, i.e. holds no text that would need clearing.

        A saved point usually means the built-in search region does not fit
        this layout -- that is what the point is for -- so the placeholder is
        looked for in a band around the point instead
        (PORTAL_SEARCH_PLACEHOLDER_BAND). One look, no waiting: a miss only
        means the box gets cleared as before.
        """
        left, right, half_height = PORTAL_SEARCH_PLACEHOLDER_BAND
        x0, y0 = max(0, point[0] - left), max(0, point[1] - half_height)
        x1 = min(config.FIXED_WIN_W, point[0] + right)
        y1 = min(config.FIXED_WIN_H, point[1] + half_height)
        if x1 <= x0 or y1 <= y0:
            return False
        try:
            return vision.find_image(hwnd, "portal_search",
                                     region=(x0, y0, x1 - x0, y1 - y0)) is not None
        except vision.TemplateNotFound:
            return False

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

        Waited for rather than looked at once -- the picker is still
        filtering for a moment after the name is typed.

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
                          f'first pass, and the {PORTAL_NAME_IMAGE_PREFIX} name crops that skip the '
                          f'search only look inside that area too. Set the box under Settings > '
                          f'Debug > Macro Coordinates ("Portal Card List") to get those seconds back.')
                return match, name
        except vision.TemplateNotFound as exc:
            # Only when NOT ONE candidate has a crop on disk.
            self._log(f"[Macro] {exc}")
        return None, None

    def _find_portal_name(self, hwnd, stop_event: threading.Event, name_image: str,
                          timeout: float):
        """Look for the wanted portal's NAME on the card list, and return
        where to click its card -- or None.

        Boxed to the card list and never widened to the whole window the way
        _find_portal_card is: this runs before the list is filtered, so a
        stray "Summer Portal" anywhere else on screen must not count.
        Re-looked until the spot holds still, since the picker may still be
        sliding in, then moved up off the text onto the card's art
        (PORTAL_NAME_CLICK_RISE).
        """
        region = self._portal_list_region()
        try:
            match = vision.wait_for_image(hwnd, name_image, region=region,
                                          timeout=timeout, stop_event=stop_event)
        except vision.TemplateNotFound:
            return None
        if match is None:
            return None
        match = self._settled_match_any(hwnd, (name_image,), stop_event, first=match, region=region)
        return dict(match, cy=max(0, match["cy"] - PORTAL_NAME_CLICK_RISE))

    def _select_portal_on_picker(self, hwnd, stop_event: threading.Event,
                                 query: str = "summer") -> bool:
        """Pick the `query` portal on an already-open portal picker, then
        activate -- driven by the PORTAL_SEARCHES regions (search box +
        portal-card list).

        The portals look alike in the picker -- the same frame and art, only
        the name printed on the card differs -- so the NAME is what decides
        which card is clicked, never the art:

        * With a crop of the portal's name (portal_name_<query>, see
          PORTAL_NAME_IMAGE_PREFIX), the card list is looked at first, and a
          portal that is already listed is clicked without searching at all.
          The search box, the typing and the wait for the filter are the
          slow part of every pick.
        * Otherwise -- or when the name is not listed -- `query` is typed into
          the picker's search, and only then is a card looked for: by its
          name if there is a crop of it, else by the generic card crops,
          which are only safe once the game has filtered the list by name.
          (Skipping the search for a generic crop is what used to click
          whichever portal sat at the front -- several PORTAL_CARD_IMAGE
          crops show no name at all.)
        """
        self._set_status(action="Selecting portal...")

        # "<query>_portal" then "<query>" first, so a portal whose card needs
        # its own crop can get one (Settings > General > Image Manager).
        # PORTAL_CARD_IMAGE stays last as the generic card for every portal,
        # which is only safe because the list has been filtered by the typed
        # name by the time it is looked for.
        slug = _portal_slug(query)
        candidates = [n for n in (f"{slug}_portal", slug, PORTAL_CARD_IMAGE) if n]
        candidates = list(dict.fromkeys(candidates))  # de-dup, keep priority order

        name_image = _portal_name_image(query)
        has_name_crop = name_image is not None and bool(vision.template_variant_paths(name_image))

        match = None
        if has_name_crop:
            match = self._find_portal_name(hwnd, stop_event, name_image, PORTAL_NAME_PEEK_TIMEOUT)
            if match is not None:
                self._log(f'[Macro] The "{query}" portal is already listed ("{name_image}", '
                          f'score {match["score"]:.2f}) -- clicking it without searching.')
            if self._checkpoint(stop_event):
                return False

        if match is None:
            # Focus + clear the search box, then type. Was a blind click on
            # the region centre with no check that anything was hit at all.
            if not self._focus_portal_search(hwnd, stop_event):
                self._spam_back_until_gone(hwnd, stop_event)
                return False
            if has_name_crop or name_image is None:
                self._log(f'[Macro] Searching the portal picker for "{query}".')
            else:
                self._log(f'[Macro] Searching the portal picker for "{query}". (A crop of just the '
                          f'name on its card, saved as "{name_image}" via Settings > General > Image '
                          f'Manager, lets an already-listed portal be clicked without searching.)')
            self._keyboard.type_text(query)
            if has_name_crop:
                # The name cannot match a different portal, so it is taken the
                # moment the filtered card shows up -- no need to sit out the
                # filter first, which the generic crops below have to.
                match = self._find_portal_name(hwnd, stop_event, name_image, SETTLE_DELAY)
            else:
                self._interruptible_sleep(SETTLE_DELAY, stop_event)
            if self._checkpoint(stop_event):
                return False

            if match is not None:
                self._log(f'[Macro] Found the "{query}" portal card by its name '
                          f'(score {match["score"]:.2f}) -- clicking it.')
            else:
                match, found_name = self._find_portal_card(hwnd, stop_event, tuple(candidates))
                if match is None:
                    self._log(f'[Macro] No "{query}" portal card found, on the picker or anywhere on '
                              f'screen (searched for {", ".join(candidates)}). Check that the Portal '
                              f'Name matches the name on the portal. If the card is visible, add a crop '
                              f'of it to "{PORTAL_CARD_IMAGE}" via Settings > General > Image Manager '
                              f'-- best just the portal art without its name, so the one crop fits '
                              f'every portal.')
                    # Taken before backing out, while the filtered list is
                    # still up: it shows at once whether the search matched
                    # nothing, the text never reached the box, or the card is
                    # there and no crop fits.
                    self._save_debug_screenshot_unconditional(hwnd, "portal_card_not_found")
                    self._spam_back_until_gone(hwnd, stop_event)
                    return False
                missed = f' "{name_image}" did not match it.' if has_name_crop else ""
                self._log(f'[Macro] Found the "{query}" portal card via "{found_name}" '
                          f'(score {match["score"]:.2f}) -- clicking it.{missed}')
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

    def _carry_on_after_portal_win(self, hwnd, stop_event: threading.Event,
                                   keep_playing: bool) -> bool:
        """After a won portal round: wait for the next round, then play it
        (keep_playing) or leave it for the lobby.

        A won round ends on the three-portal offer alone. The portal taken
        there (runner._take_portal_offer_if_found) starts its round by
        itself, so with repeats left that round simply IS the next repeat,
        and _run_task picks it up at Pre Start. When the task is done, or the
        lobby is wanted between repeats, the round is left with the in-match
        To Lobby button -- there is no result screen with Leave Stage to use
        anymore. It is waited for first all the same: To Lobby on the old
        round, mid-transition, is not a leave anyone can count on.
        """
        if not self._wait_for_next_portal_round(hwnd, stop_event):
            return False
        if keep_playing:
            self._log("[Macro] The next portal round is up -- continuing this task's repeats.")
            return True
        return self._leave_match_to_lobby(hwnd, stop_event, reason="Portals")

    def _wait_for_next_portal_round(self, hwnd, stop_event: threading.Event) -> bool:
        """Wait for the round the taken portal starts. Its Start Game button
        is the sign: it is only on screen before a round has begun, so the
        round just won can't be mistaken for it.

        Takes the middle portal again while the offer is still up -- a click
        the game never got (routine over Remote Desktop) would otherwise
        leave the pick to the offer's timer, which takes one at random.
        """
        self._set_status(action="Waiting for the next portal round...")
        deadline = time.time() + PORTAL_NEXT_ROUND_TIMEOUT
        while time.time() < deadline:
            # Pause first: right after the pick the offer may still be
            # closing, and it is not worth a second click.
            self._interruptible_sleep(PORTAL_NEXT_ROUND_POLL_INTERVAL, stop_event)
            if self._checkpoint(stop_event):
                return False
            _, start_match = self._find_start_game_button(hwnd)
            if start_match is not None:
                return True
            self._take_portal_offer_if_found(hwnd)
        self._log(f"[Macro] The next portal round never showed its Start Game within "
                  f"{PORTAL_NEXT_ROUND_TIMEOUT:.0f}s of taking the portal.")
        self._save_debug_screenshot_unconditional(hwnd, "portal_next_round_timeout")
        return False
