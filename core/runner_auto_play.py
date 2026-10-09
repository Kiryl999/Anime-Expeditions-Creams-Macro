"""The game's Auto Play, switched on and kept on, as one mixin.

For a Macro Operation with Macro Manager > Pre Start > Auto Play switched on
(saved as ``blocks.auto_play``): Start Game is only pressed once the in-match
button reads "Auto Playing", and during the round the button is watched so
Auto Play goes straight back on if it went off.

The button toggles, which is what all of this is shaped around. It used to be
left to Detect + Click blocks -- click unless "Auto Playing" shows -- and over
Remote Desktop a second click then landed while the label was still catching
up with the first, switching Auto Play straight back off. So here a click
needs positive evidence of OFF: "Auto Play" (AUTO_PLAY_OFF_IMAGE) on screen and
"Auto Playing" (AUTO_PLAY_ON_IMAGE) not, both read from one frame. After a
click the macro waits for "Auto Playing" instead of clicking again.

Split out of core/runner.py like the other *Ops classes -- see core/runner.py,
which composes the mixins (MacroRunner). Methods here run with MacroRunner's
full self: shared state and helpers (_log, _checkpoint, _interruptible_sleep,
...) resolve normally.
"""
import threading
import time

from . import vision
from .runner_constants import *  # noqa: F401,F403 -- the shared constants namespace


class AutoPlayOps:
    def _auto_play_enabled(self, task: dict) -> bool:
        """Whether the task's Macro Operation has Auto Play switched on. Off
        unless the template says so -- every template saved before the switch
        existed keeps whatever its own blocks did."""
        macro_name = (task or {}).get("macro")
        if not macro_name:
            return False
        from . import templates as tpl
        blocks = tpl.load_template(macro_name).get("blocks") or {}
        return isinstance(blocks, dict) and blocks.get("auto_play") is True

    def _read_auto_play(self, hwnd):
        """("on" | "off" | None, match) from ONE frame.

        Both crops are matched against the same capture, so the answer
        describes one moment. When both clear their threshold the better
        score wins: a crop of "Auto Play" can score high on "Auto Playing"
        (the shorter label is inside the longer one), never the other way
        round. Raises vision.TemplateNotFound when either crop is missing.
        """
        for name in (AUTO_PLAY_ON_IMAGE, AUTO_PLAY_OFF_IMAGE):
            vision.load_template_grays(name)
        frame = vision.capture_game_gray(hwnd)
        if frame is None:
            return None, None
        on = vision.find_in_gray_multiscale(
            frame, AUTO_PLAY_ON_IMAGE, threshold=vision.threshold_for(AUTO_PLAY_ON_IMAGE))
        off = vision.find_in_gray_multiscale(
            frame, AUTO_PLAY_OFF_IMAGE, threshold=vision.threshold_for(AUTO_PLAY_OFF_IMAGE))
        if on is not None and (off is None or on["score"] >= off["score"]):
            return "on", on
        if off is not None:
            return "off", off
        return None, None

    def _await_auto_play(self, hwnd, stop_event: threading.Event, settle: float, timeout: float):
        """Look until the button says which way it is.

        "On" counts on the first look -- it is the one state that is never
        clicked, so there is nothing to double-check. "Off" counts only once
        `settle` has passed and the last two looks both read it. Returns
        (state, match), or (None, None) when it never got clear within
        `timeout` or the run was stopped.
        """
        started = time.time()
        off_looks = 0
        while True:
            state, match = self._read_auto_play(hwnd)
            if state == "on":
                return state, match
            off_looks = off_looks + 1 if state == "off" else 0
            if off_looks >= 2 and time.time() - started >= settle:
                return state, match
            if time.time() - started >= timeout:
                return None, None
            self._interruptible_sleep(AUTO_PLAY_LOOK_INTERVAL, stop_event)
            if stop_event.is_set():
                return None, None

    def _auto_play_before_start(self, hwnd, stop_event: threading.Event, task: dict,
                                webhook: dict = None) -> bool:
        """Switch Auto Play on before Start Game, when the macro asks for it.

        Fast on the usual paths: already on (a portal's next round) costs one
        look; off costs half a second of looking, one click and the moment the
        label takes to change. A click that does not take is clicked again
        after AUTO_PLAY_VERIFY_SETTLE, up to AUTO_PLAY_START_CLICKS clicks. If
        Auto Play still is not on then -- or the button never shows -- the
        round starts anyway, with a warning: a hung Start Game would cost more
        than one round without Auto Play.

        Returns False only when the run was stopped.
        """
        if not self._auto_play_enabled(task):
            return True
        self._set_status(action="Switching Auto Play on...")
        try:
            state, match = self._await_auto_play(hwnd, stop_event, AUTO_PLAY_OFF_SETTLE,
                                                 AUTO_PLAY_FIND_TIMEOUT)
            clicks = 0
            while state == "off" and clicks < AUTO_PLAY_START_CLICKS:
                clicks += 1
                self._log(f"[Macro] Auto Play is off -- switching it on "
                          f"(click {clicks}/{AUTO_PLAY_START_CLICKS}).")
                vision.click_match(self._mouse, hwnd, match)
                state, match = self._await_auto_play(hwnd, stop_event, AUTO_PLAY_VERIFY_SETTLE,
                                                     AUTO_PLAY_VERIFY_SETTLE + 1.0)
        except vision.TemplateNotFound as exc:
            self._log(f"[Macro] Auto Play: {exc} Starting the round without checking it.")
            return not self._checkpoint(stop_event)
        if self._checkpoint(stop_event):
            return False
        if state == "on":
            self._log("[Macro] Auto Play is on." if clicks else "[Macro] Auto Play is already on.")
            return True
        what = (f"still off after {clicks} click(s)" if state == "off"
                else "button not found (auto_play_on / auto_play_off)")
        self._log(f"[Macro] Auto Play: {what} -- starting the round anyway.")
        screenshot_path = self._save_debug_screenshot_unconditional(hwnd, "auto_play_not_on")
        self._send_event_webhook(
            webhook, task, "Auto Play Not On",
            f"Auto Play {what} -- the round started without it.", 0xE8935A, screenshot_path)
        return not self._checkpoint(stop_event)

    # ── Mid-round ───────────────────────────────────────────────────────────

    def _reset_auto_play_watch(self) -> None:
        """Fresh watch per match. The first look waits one interval: Start
        Game was only pressed once Auto Play read on."""
        self._auto_play_watch = {
            "next_look": time.time() + AUTO_PLAY_WATCH_INTERVAL,
            "off_looks": 0,
            "clicks": 0,
            "paused": False,
        }

    def _tick_auto_play(self, hwnd) -> bool:
        """One step of the mid-round watch, called from the match poll loop
        when nothing else clicked this tick. Returns whether it clicked.

        Never blocks the poll: "off" has to be read on two polls in a row
        (about a second apart) before the button is clicked, and after a
        click the next look waits AUTO_PLAY_VERIFY_SETTLE for the label to
        catch up. Clicks that never bring it on stop after
        AUTO_PLAY_WATCH_MAX_CLICKS until the next match.
        """
        watch = getattr(self, "_auto_play_watch", None)
        if watch is None or watch["paused"]:
            return False
        now = time.time()
        if now < watch["next_look"]:
            return False
        try:
            state, match = self._read_auto_play(hwnd)
        except vision.TemplateNotFound as exc:
            self._log(f"[Macro] Auto Play: {exc} Not watching it this match.")
            watch["paused"] = True
            return False
        if state != "off":
            if state == "on" and watch["clicks"]:
                self._log("[Macro] Auto Play is back on.")
                watch["clicks"] = 0
            watch["off_looks"] = 0
            watch["next_look"] = now + AUTO_PLAY_WATCH_INTERVAL
            return False
        watch["off_looks"] += 1
        if watch["off_looks"] < 2:
            return False  # confirmed on the next poll
        if watch["clicks"] >= AUTO_PLAY_WATCH_MAX_CLICKS:
            self._log(f"[Macro] Auto Play is still off after {watch['clicks']} clicks -- "
                      f"leaving it for the rest of this match.")
            watch["paused"] = True
            return False
        watch["clicks"] += 1
        watch["off_looks"] = 0
        self._log(f"[Macro] Auto Play went off mid-round -- switching it back on "
                  f"(click {watch['clicks']}/{AUTO_PLAY_WATCH_MAX_CLICKS}).")
        vision.click_match(self._mouse, hwnd, match)
        watch["next_look"] = now + AUTO_PLAY_VERIFY_SETTLE
        return True
