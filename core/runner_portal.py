"""Portal event: Inventory -> Portals tab -> portal -> Activate Portal ->
Start, plus the 3-card pick the event puts up as a run ends.

Split out the same way core/runner_expedition.py is -- a mixin providing part
of MacroRunner's behavior (see core/runner.py, which composes the mixins).
Methods here run with MacroRunner's full self: shared state and helpers
(_log, _coords, _checkpoint, _click_found_image, ...) resolve normally.

Portal is its OWN mode rather than another Event stage on purpose: mode
"event" is hardwired to Villian Invasion (nav_event -> Villain_Invasion ->
event_gamemode -> an Act card, see runner._reach_event_act_selected), and
portals are reached through the inventory instead -- a completely different
path with a different confirm button, and an end-of-run card choice that
opens BEFORE the Victory screen rather than after it.
"""
import threading
import time

from . import vision
from . import window as wm
from .runner_constants import *  # noqa: F401,F403 -- the shared constants namespace


class PortalOps:

    # ---------- Navigation ------------------------------------------------

    def _reach_portal_activated(self, hwnd, stop_event: threading.Event, portal: str) -> bool:
        """Lobby -> Inventory -> Portals tab -> the portal's card -> Activate
        Portal, as one restartable unit -- Portal's equivalent of
        _reach_event_act_selected. On any failure it backs out to the lobby
        (_portal_back_out) so the next attempt starts clean, same as the
        map/event/tournament paths do.

        Activate Portal is where this stops: the Start button and the
        teleport wait after it are the shared tail every mode uses (see
        _enter_selected_stage), and Activate Portal is what stands in for the
        nav_select_stage confirm there.
        """
        images = PORTAL_IMAGES.get(portal)
        if images is None:
            self._log(f'[Macro] Unknown Portal "{portal}" -- expected one of {PORTAL_ORDER}.')
            return False
        if isinstance(images, str):
            images = (images,)

        if not self._ensure_lobby(hwnd, stop_event):
            return False
        if self._checkpoint(stop_event):
            return False

        # Each click is a wait-then-click with a focus-safe verify via
        # _click_found_image, and every screen here animates in (the
        # inventory panel, the tab swap, the portal's detail card), so a
        # short settle follows each one before the next is searched for.
        steps = (
            ("nav_inventory", "Inventory"),
            ("portal_tab", "the Portals tab"),
            (images[0], portal),
            ("portal_activate", "Activate Portal"),
        )
        for name, label in steps:
            self._set_status(action=f"Clicking {label}...")
            if self._click_found_image(hwnd, name, PORTAL_SCREEN_TIMEOUT, stop_event) is None:
                if stop_event.is_set():
                    return False
                self._log(f'[Macro] Portal entry stalled at "{name}" -- if that button is visibly on '
                          f'screen, add your own crop of it via Settings > General > Image Manager.')
                self._portal_back_out(hwnd, stop_event)
                return False
            if self._checkpoint(stop_event):
                return False
            time.sleep(SETTLE_DELAY)

        return not self._checkpoint(stop_event)

    def _portal_back_out(self, hwnd, stop_event: threading.Event) -> None:
        """Back out of a half-finished portal entry. The inventory is a modal
        with its own close glyph rather than one of the nested Back screens
        _spam_back_until_gone walks out of, so that gets clicked first (best
        effort -- no crop, no click), then the normal Back spam handles
        whatever else is still stacked underneath."""
        try:
            close = vision.find_image(hwnd, "nav_closeui")
        except vision.TemplateNotFound:
            close = None
        if close is not None:
            self._log("[Macro] Closing the inventory (nav_closeui) after a failed portal entry.")
            vision.click_match(self._mouse, hwnd, close)
            time.sleep(SETTLE_DELAY)
        self._spam_back_until_gone(hwnd, stop_event)

    # ---------- The 3-card pick, offered BEFORE the Victory screen -------

    def _portal_card_region(self):
        """Optional search box for the card window, in the docked window's
        1152x756 reference space, or None for the whole screen.

        Worth setting: the readiness crop is often a portal NAME, and a
        portal name can also appear in the HUD, on the result screen, or on
        another of the three cards. Restricting the search to the strip the
        cards occupy is what makes "this name, HERE" mean "the cards are up"
        rather than "that word is somewhere on screen". All four values have
        to be filled in for it to apply -- a half-set box is treated as
        unset rather than guessed at."""
        values = [self._coords.get(f"portal_card_region_{axis}") for axis in ("x", "y", "w", "h")]
        if any(value in (None, "") for value in values):
            return None
        try:
            x, y, w, h = (int(value) for value in values)
        except (TypeError, ValueError):
            return None
        return (x, y, w, h) if w > 0 and h > 0 else None

    def _portal_cards_available(self, hwnd) -> bool:
        """Whether the 3-card choice is on screen right now.

        Polled from inside the match loop (see runner._wait_for_match_result):
        the offer opens BEFORE the Victory screen does, so waiting for the
        result and looking afterwards misses it entirely. Cheap and silent by
        design -- it runs on every poll of every portal match, so a missing
        crop reads as "not showing" here and is reported once by the caller."""
        if not vision.template_variant_paths(PORTAL_CARD_READY_IMAGE):
            return False
        try:
            return vision.find_image(hwnd, PORTAL_CARD_READY_IMAGE,
                                     region=self._portal_card_region()) is not None
        except vision.TemplateNotFound:
            return False

    def _portal_card_point(self, hwnd, index: int):
        """Where to click for card 1..3, in the docked window's reference
        space. The Settings > Debug override wins if it's set; otherwise the
        point is read off the live screen -- the card frame
        (PORTAL_CARD_SLOT_IMAGE) if that crop exists, else the readiness crop
        itself, which works when it's a per-card frame rather than a single
        heading. Same Auto-or-fixed shape as team_button_x/y: _optional_cxy
        returns None while the fields are empty.

        Returns None when neither route can produce a point -- the caller
        turns that into a "set the coordinates" message rather than clicking
        somewhere arbitrary."""
        point = self._optional_cxy(f"portal_card_{index}")
        if point is not None:
            return point

        region = self._portal_card_region()
        for name in (PORTAL_CARD_SLOT_IMAGE, PORTAL_CARD_READY_IMAGE):
            try:
                matches = vision.find_image_all(hwnd, name, region=region)
            except vision.TemplateNotFound:
                continue
            # Left to right, so card 1 is the leftmost one on screen --
            # find_image_all returns them best-score first, which says
            # nothing about position.
            matches = sorted(matches or [], key=lambda m: m["cx"])
            # All 3 or nothing: fewer matches means this crop isn't the card
            # frame at all (a heading matches once, and its centre is nowhere
            # near a card), so picking the n-th of a partial list would just
            # click confidently in the wrong place.
            if len(matches) >= PORTAL_CARD_COUNT:
                match = matches[index - 1]
                self._log(f'[Macro] Portal card {index} located from "{name}" '
                          f'(score {match["score"]:.2f}).')
                return int(match["cx"]), int(match["cy"])
        return None

    def _pick_portal_card(self, hwnd, stop_event: threading.Event, choice=None) -> bool:
        """Take one of the 3 portal cards, assuming they are on screen NOW
        (_portal_cards_available said so on this poll).

        The offer closes itself after ~15s and there is no second one, so
        this is a single attempt: click the configured point, then confirm
        the window actually went away. Returns whether the card was taken.
        """
        try:
            index = int(str(choice or PORTAL_CARD_CHOICE_DEFAULT))
        except (TypeError, ValueError):
            index = int(PORTAL_CARD_CHOICE_DEFAULT)
        index = min(PORTAL_CARD_COUNT, max(1, index))

        deadline = time.time() + PORTAL_CARD_WINDOW
        point = self._portal_card_point(hwnd, index)
        if point is None:
            self._log(f"[Macro] The portal cards are up but there's no click point for card {index} -- "
                      f'set it in Settings > Debug > Macro Coordinates ("Portal Cards"), or add a '
                      f'"{PORTAL_CARD_SLOT_IMAGE}" crop of one card frame so all 3 can be located '
                      f"automatically.")
            return False

        x, y = point
        left, top, _, _ = wm.get_window_rect_screen(hwnd)
        self._set_status(action=f"Picking portal card {index}...")
        self._log(f"[Macro] Portal cards are up -- picking card {index} at ({x}, {y}).")
        if not wm.activate_window(hwnd):
            self._log("[Macro] Couldn't confirm focus before picking the portal card -- "
                      "the click may not register.")
        self._mouse.click(left + x, top + y)

        # Verified, not assumed: a swallowed click is indistinguishable from
        # a successful one until the window closes itself ~15s later and the
        # run carries on into a portal it never chose. Whatever is left of
        # the budget is what the confirmation gets.
        remaining = max(1.0, deadline - time.time())
        if not self._wait_for_image_gone(hwnd, (PORTAL_CARD_READY_IMAGE,), remaining, stop_event):
            if stop_event is not None and stop_event.is_set():
                return False
            self._log("[Macro] The portal card choice is still on screen after the click -- "
                      "the click didn't register, or the click point is wrong.")
            return False
        self._log(f"[Macro] Portal card {index} taken.")
        return True
