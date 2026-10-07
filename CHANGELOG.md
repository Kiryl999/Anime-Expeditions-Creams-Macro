# Changelog

All notable changes to Anime Expeditions (Cream's Macro) are documented here.

## [0.21.17] - 2026-10-07

### Fixed
- **Portal runs keep going after the game's October update**: a won portal round now ends on the offer of three new portals alone -- no Victory screen and no Select Portal follow it, and the portal you take there starts its round by itself. The macro still takes the middle portal, now counts that as the win, waits for the new round's Start Game and plays it like any repeat: Pre Start places your units, then Start Game. If the offer is still up because the click did not register, the middle portal is clicked again. On a task's last repeat, or when Challenge, Auto Crafting, Auto Fuel, Auto Shop or the Periodic Roblox Refresh is due, the macro leaves that new round through To Lobby, since there is no Leave Stage screen anymore. Starting a portal from the lobby -- Inventory, Portals tab, search, Activate -- is unchanged. Keep in mind that the round after a win is always the middle portal from the offer, not the Portal Name set in the task. Portal wins reach the match result webhook without a screenshot, as there is no result screen to capture.
- **Camera Setup no longer holds the right mouse button**: over Remote Desktop the camera setup could still take the macro out of Roblox, even with the pointer kept inside the game since 0.21.16. It now tilts the camera through first person instead: it holds I to zoom all the way in, moves the mouse down to look at the ground and holds O to zoom back out, which leaves the camera looking straight down -- half a second each. The normal setup then holds O for 2 seconds as before, so it ends on the same view your Place Unit and Walk Path positions were recorded against. This covers every camera setup: Pre Start, the Expedition camera, the Gold Shop and the Camera Setup buttons under Settings > Debug. The Expedition camera now starts from that close first-person zoom instead of the zoom you entered with, so if units land off on Expedition maps, adjust Settings > Debug > **Expedition Camera Zoom**.

## [0.21.16] - 2026-10-06

### New
- **Camera Setup can be switched off per macro**: on the first entry into a stage the macro sets up the camera before your Pre Start blocks run -- a right-click drag that tilts it top-down, then O to zoom out. That step used to run unseen, which made the pinned Walk Path look like the thing moving the camera. It now has its own row at the top of Pre Start in the Macro Manager, above the Walk Path, with an **On/Off** switch that is saved with the macro. Switched off, the macro skips the camera setup and gives the map 5 seconds to settle before the first block instead, the same as on a repeat. Leave it on for any macro that places units by position -- Place Unit and Walk Path positions are recorded against that view. Off is for macros that don't, e.g. one that only turns on the game's Auto Play. Existing macros keep it on.

### Fixed
- **The camera drag keeps the mouse pointer inside Roblox**: Roblox pulls the pointer back only once per frame while the right button is held, so where the game draws few frames -- over Remote Desktop in particular -- the camera setup's quick drag could carry the pointer out of the game window, and the right button was let go over the log strip or the taskbar instead of the game. The pointer now stays inside the game window for the length of the drag and is freed right after. This covers every camera drag: Pre Start, the Expedition camera, the Gold Shop and the Camera Setup buttons under Settings > Debug.

## [0.21.15] - 2026-10-02

### Improved
- **Portals are clicked by their name instead of always searching**: since 0.21.13 every portal pick typed the Portal Name into the picker's search -- click the box, empty it, type, wait for the list to filter -- which cost a few seconds plus several Macro Speed pauses on every round. The macro now first looks for the portal's name on the cards already listed and clicks that card straight away when it is there. Only when it is not does it search, and then it clicks the card as soon as its name shows up instead of waiting a fixed moment for the list. The name is what tells the portals apart (the art is the same on all of them), so this needs a crop of just the name printed on the card, saved via Settings > General > Image Manager as `portal_name_` plus the Portal Name -- e.g. `portal_name_infernal`. The Summer one is included. A portal without such a crop is searched as before, and the log names the crop it is missing. The name is only looked for inside the portal card list, so if your picker sits elsewhere, set it under Settings > Debug > Macro Coordinates > **Portal Card List**.
- **The portal search box is only emptied when there is something in it**: the 33 key presses that clear it, and the Macro Speed pause after them, are skipped whenever the box shows its "Search..." placeholder -- which is most of the time.

### Changed
- **The `boss_rush_card_alt2` and `boss_rush_card_light_name` reference images are no longer included in the download.**

## [0.21.14] - 2026-09-29

### New
- **Boss Rush**: a new task mode for the Boss Rush gamemode (Play > Boss Rush > District 7). One repeat is one whole run: Start Game at the spawn, then for each gate the macro walks there, presses E, presses Start Game, clears it and takes the middle one of the three cards -- up to the gate you pick under **Boss After Gate** (2-6), where it presses Fight Boss instead of Continue. The units placed in the first gate stay for the later gates; the boss arena starts empty, so the new **Macro Operation (Boss)** places them again ("Same as Gates" reuses the first one). The walks from the spawn to all six District 7 gates ship with the macro, so a new task runs without recording anything; under **Gate Paths** you can record your own walk for any gate instead. A lost gate or boss ends on the normal Defeat screen, and the next repeat starts a fresh run. The crops it needs are included.
- **Switch tasks off without deleting them**: every task in the queue has an on/off switch next to Clone and Remove. A switched-off task keeps its place and all its settings, is greyed out, and the run skips it. The queue count shows how many are off.
- **Auto Fishing clears the fish slots**: a catch no longer just piles up in the 6 fish slots. Fish with a crop in `wanted_fish` are clicked once to cash them in, fish with a crop in `unwanted_fish` are dragged to the bin. Pick the slot row once under Settings > Debug > Macro Coordinates > **Fish Slots**; while it is unset the slots are left alone. Crops for several fish are included.
- **Walk recordings can press E**: the path recorder now records the E (interact) key along with WASD and I/O, so a recorded walk can end by pressing E at whatever it walked up to.
- **Camera Yaw Check** (Settings > Debug): after Camera Setup, save the current camera angle under a label, measure how far a later map entry is turned away from it, and turn it back.
- **Eclipse Quest -- not usable yet**: a task mode for the secret-unit quest line -- take the quest on Crimson Shore, farm the Eclipse event on whichever Story map carries it until the soul stack is full, hand the souls in. It still needs crops that don't ship yet (`quest_accept`, `quest_redeem_sacrifice` or `quest_redeem_redemption`, `souls_full`); until they are there, an Eclipse task says so in the log and is skipped.

### Changed
- **Updated `fishing_xp` and `portal_offer` reference images.**

## [0.21.13.2] - 2026-09-26

### Fixed
- **Portal search starts typing right away**: after clicking into the portal search box, the macro could sit there for around 20 seconds before typing the portal name -- most visible over Remote Desktop. Emptying the box first takes 33 key presses, and each one waited out your Macro Speed delay; at 600ms that adds up to about 20 seconds (at the default 0ms you never saw it). The box is now emptied in about a second, with one Macro Speed pause after it.
- **The portal search box is really emptied**: it was cleared from the wrong end of the text, so anything already in the box stayed there and the portal name was typed after it. It did not show because the box usually opens empty.

## [0.21.13] - 2026-09-26

### New
- **Flaming Monastery map**: the 8th Story map. You can pick it in a task's Story map list, Regular and Daily Challenge recognize it when they land there, and Auto Bounty can send you to it. **Give it a Macro Operation under Story Map Setup, for Auto Challenge and for Auto Bounty** -- both refuse to start while any Story map has none, so after updating they stay off until you do.
- **Type the Auto Fishing water point**: a task's Water Point now has X and Y fields next to Pick, so you can fix a picked point by hand or copy one from another task. Both are needed; clearing a field unsets the point.

### Fixed
- **Portals pick the portal you asked for**: with more than one kind of portal in the game, the macro could click whichever portal sat at the front of the picker without ever typing its name. It skipped the search whenever a portal card already looked listed -- and in the picker the portals look alike apart from the name printed on the card. The Portal Name is now typed into the search on every pick, before any card is looked for, on the way in and after every win.

### Changed
- **One set of portal card crops for every portal**: the `summer_portal` crop folder is now `portal_card`. The list is filtered by name first, so a crop there only has to recognize "a portal card" -- best just the portal art, without the name under it. The art is tinted differently per tier, so if a card is not found, add a crop of that tier's card (Settings > General > Image Manager). When no card is found, the macro now saves a `portal_card_not_found` screenshot of what was on screen.

### Removed
- **Event > Portal**: portals now run only through the **Portals** task (Inventory > Portals tab), which reaches every portal, Summer included. Existing Event > Portal tasks -- in the queue, in presets and in imported files -- turn into a Portals task with the Portal Name "summer" by themselves, and the log says so.

## [0.21.12] - 2026-09-22

### Fixed
- **Portal rounds no longer sit on the Start button**: after picking a portal from your inventory, the round very often never started -- the Start button got pressed a moment too early, or the press did not register and nothing said so. Portals are the only mode that goes straight from "Activate Portal" to the stage screen, with no Select Stage step in between, and that step was what made every other mode wait for the screen to finish opening. The macro now waits for it, makes sure the Start button has stopped moving before clicking it, and checks that both the "Activate Portal" click and the Start click actually registered -- clicking again straight away instead of waiting 20 seconds to find out. Most noticeable over Remote Desktop.
- **The window comes back after a Remote Desktop drop**: the macro's own window could minimize by itself on Remote Desktop -- a brief internet drop is enough, because Windows minimizes a session's windows when the connection goes -- and from then on nothing was clicked at all, since Roblox runs docked inside that window. It could not be restored from the taskbar either. The macro now puts its window back on its own whenever this happens during a run, and says so in the log. There is also a new **Restore Window** hotkey (F8 by default, under Settings > Keybinds) for when no run is going, or when that does not take.

## [0.21.11] - 2026-09-13

### New
- **Tidal Siege restarts in place instead of leaving**: at its wave limit (now "Restart After Wave" on the task), an Event > Infinite task restarts the game from Settings -- Restart Game, then the red Restart confirmation -- and presses Start Game again. Your units stay placed, so there is no leaving, no lobby and no Pre Start in between. Each restart counts as one repeat. It still leaves the stage the old way on the task's last repeat, when Challenge, Crafting, Fuel, Shop or a Roblox refresh is due, or if the restart does not go through (Start Game has to come back for it to count). Story's Infinite keeps leaving as before. Uses the `restart_btn` crop and the new `restart_confirm` crop; if the confirmation is not recognised, the log says how close the crop got and saves a screenshot.
- **Restarts show up on the Scoreboard**: each Tidal Siege restart is counted as a win (session, all-time and run history), so you can see the run is working. Auto Crafting's win count and the result webhook are not affected.

### Fixed
- **Auto Fishing no longer switches itself off for the whole run**: one rod click that did not bring the XP bar up used to disable fishing until the run was started again -- a 9.5-hour run lost all its fishing to it, without another log line. The rod is now watched for the whole round (a look every 30 seconds), only clicked once the bar has been missing on three looks in a row, retried after 3 minutes when a click does not bring it up, and after two failures paused until the next match only.
- **"Rod is already out" while the rod was away**: the XP bar was searched for across the whole window, so something label-like elsewhere could count. It is now only looked for in the bottom-right corner, and every hit is logged with its score and position.

## [0.21.10] - 2026-09-12

### Improved
- **Portal picks skip the search when they can**: the portal picker used to be searched every time -- click the search box, clear it, type the portal name, wait for the list to filter, find the card. When you own only one portal, or the one you want is already at the front, its card is listed straight away. The macro now looks for it first and only searches when it is not there. It still only ever clicks the portal your task asks for, never simply the first one.
- **The post-round portal offer is caught sooner**: it was only looked for after several slower checks in each pass of the match loop, so part of its ~20-second window was gone before the macro even looked. It is now checked first.

### Fixed
- **"Game Results" is no longer clicked during the portal offer**: v0.21.9 started reopening a closed result screen through its "Game Results" button, but that button is also on screen for the whole portal offer at the end of every portal round. It is now only clicked once it has stayed visible for 25 seconds, longer than the offer.
- **Updated `fishing_xp` reference images.**

## [0.21.9] - 2026-09-11

### Fixed
- **A closed result screen no longer stalls a run for 30 minutes**: on a portal round the result panel could end up shut before Victory was read, leaving only a "Game Results" button at the bottom. The run then waited out the whole match timeout over a finished match -- long enough for the game to park you in the AFK Chamber. That button is now clicked to bring the result back. The crop is included.
- **The AFK Chamber and a leftover portal picker no longer get Roblox restarted**: when Play could not be found, the run treated it as a silent disconnect straight away and restarted Roblox. Both screens hide Play without being a disconnect. The lobby check now leaves the AFK Chamber or closes the portal picker first and looks again; a restart only happens if that does not help. The portal picker's close-button crop is included.
- **A restart that never brought Roblox back no longer leaves the run on the Launch Roblox screen**: if the relaunch did not produce a window, that launch stayed "pending" forever and blocked every later restart, including the automatic reopen. It is now given up on after 5 minutes and launched again.
- **Restarts are more reliable**: Roblox was relaunched one second after the old client was killed, whether or not it had actually exited, and some of those relaunches never produced a window. The old client is now waited on until it is really gone.
- **After an automatic reopen the run follows the new window**: it could keep acting on the closed one -- every search missed and every screenshot came back empty -- until a lobby check eventually failed and forced another restart.

## [0.21.8] - 2026-09-09

### New
- **Auto Fishing**: fish passively while a round runs. Turn it on per task, pick the spot on the water to cast at, and set how often to cast (6s by default -- a bite takes 6-12s and an extra click never cancels a cast). The rod is taken out once per round and only when the fishing XP bar says it is not already out, since that button toggles. Casting stops when the round does, and never happens in the same moment as a unit placement or a portal pick, so it cannot drop a unit in the water or steal the post-round portal choice. Needs two crops captured once: `fishing_rod` (the button, bottom-left) and `fishing_xp` (the XP bar, bottom-right). It does **not** move your character -- park it at the water with a Walk Path block in the Macro Operation, which also re-runs after a Challenge interleave.
- Settings kept per task on purpose, so the same Macro Operation can be reused across maps while only one of them fishes.

### Fixed
- **The post-round portal choice now works out of the box**: v0.21.7 added it but shipped no reference image, so it did nothing until one was captured. The crop is included.

## [0.21.7] - 2026-09-09

### New
- **Portal runs take the middle portal instead of letting the timer decide**: a won portal round offers three new portals for about 20 seconds before the Victory screen appears, and picks one at random when that runs out. The offer is now watched for from inside the match -- after the result there is nothing left to choose -- and taken with a middle-of-screen click, which is the middle card. This is the same mechanism Expedition already uses for its "select an upgrade!" cards. It needs one crop you capture yourself: something visible **only** while the offer is up (its heading or countdown), saved as `portal_offer` under Settings > General > Image Manager. Without it nothing changes and the offer times out as before. One attempt per round, because the Victory screen's unit portraits sit near that same spot.

## [0.21.6] - 2026-09-09

### Fixed
- **The "Click anywhere to close" panel is actually dismissed**: the cursor moved to the panel and nothing happened -- the click neither took window focus first (as every other click path in the runner does) nor approached with the hover-in movement some Roblox buttons need before a click registers at all. It now does both, and then checks whether the panel really went away: if it is still up, the middle of the screen is clicked once instead, since the panel's text can sit in a strip that is not itself the input catcher. A failed dismissal used to be invisible -- the panel hides the Victory screen, so the run just polled a covered result until the 30-minute match timeout with nothing in the log to explain it.
- **Portal cards are found even when the picker sits elsewhere**: the card search was boxed into `PORTAL_SEARCHES["portals"]`, a hardcoded region measured on one layout. A setup whose search field sits ~189px right of the shipped one puts the whole card list past that box's right edge, so every post-victory pick failed with "No portal card found" while the card was plainly on screen. The region is now a hint, not a boundary -- searched first (it still disambiguates when several portals are listed), then widened to the whole window, which is safe because the typed query has already filtered the list. The widening is logged so a mismatched region stays visible instead of silently costing runs.
- **The card is waited for, not glanced at**: the search was a single one-shot look. The post-victory picker opens over the result screen and is still filtering for a moment, so a slow frame read as "not there". Both portal lead-ins now share one search with a timeout.

### New
- **Portal Card List box** (Settings > Debug > Macro Coordinates): set the area the portal cards are searched in. **Pick** now takes two clicks for a box -- the top-left corner, then the opposite one -- and writes x, y, width and height. Auto keeps the built-in box, which still works everywhere thanks to the whole-window fallback, but pays that fallback's timeout on every single portal pick when the box does not fit; setting it once makes the first pass hit instead. The log line that reports the widening now names the box it searched and says how many seconds each pick is losing.

## [0.21.3] - 2026-09-09

### Fixed
- **Portal search no longer presses Ctrl**: the picker's search box was cleared with Ctrl+A + Delete. That is safe only for a click that landed -- when the click missed, the Ctrl went to Roblox instead and changed the camera view, which nothing in the run recovers from. Both portal lead-ins now clear with Home + backspaces, which do nothing at all when they miss.
- **Portal search aims at the field, not the placeholder**: the click is matched against the shipped `portal_search` crop, which is the 47x10 placeholder word "Search..." at the left end of the bar -- so its center sits near the left edge of the input and lands outside it on layouts where the bar sits differently, and the query was typed into nothing.

### New
- **Portal Search Box coordinate** (Settings > Debug > Macro Coordinates): pick a point inside the search field when the automatic aim misses, the same Auto-or-fixed shape the Teams button uses. Auto keeps the previous crop-matching behavior.

## [0.21.2] - 2026-09-09

### Changed
- **Updates now come from this fork**: the in-app updater and the bootstrapper pointed at the upstream repository, so the first upstream release numbered above this one would have been offered as an update and swapped this build for theirs -- silently dropping everything that only exists here (the extra maps, the extra crops, the Snowy Castle close-panel fix). Both now read this fork's releases, as does the "download the latest .zip" link in the troubleshooting panel. Upstream releases are no longer offered directly; picking them up means merging upstream in and cutting a release here.
- **One manual install is needed to switch over**: the currently installed build has the old target compiled in, so it cannot find this release on its own. Install this version's zip by hand once -- every update after it is automatic.

## [0.21.1] - 2026-09-09

### Fixed
- **Snowy Castle Act 3 no longer stalls on the Iron Wolf reveal**: the secret unit's full-screen "Click anywhere to close" panel hides the Victory screen completely, and the macro only ever watched for that panel on Spirit City Act 3 -- so a run that drew Iron Wolf polled a covered result screen until the 30-minute match timeout. The watch now covers both raid Acts that can throw one (`CLOSE_POPUP_RAID_MAPS`), and stays off elsewhere since it costs an image search per poll. Unlike Spirit City's cutscene, Iron Wolf is a drop and can land at any moment in the round. If the shipped `click_anywhere_to_close` crops do not match it on your setup, add one of your own to that folder -- they include the background behind the text, which differs per screen.

## [0.21.0] - 2026-09-09

### New
- **Crimson Shore map**: the 7th Story map, added everywhere a Story map has to be listed -- the Task Builder's Story picker, Auto Challenge's Regular Challenge map setup, and Auto Bounty's destination list. Needs two crops captured before use: its carousel name label under `Assets/maps/Crimson Shore/` (to pick it) and its in-map label under `Assets/ui/Crimson Shore/` (so Regular Challenge can tell it landed there); an OCR alias covers the Daily Challenge label in the meantime.
- **Raid: Snowy Castle**: the second raid story is now selectable as a Raid map, alongside Spirit City. It shares the carousel, the 3 Acts and the Hard-locked difficulty with the first one, so the only thing it needs is its own name-label crop under `Assets/maps/Snowy Castle/` (Settings > General > Image Manager > Map Names).

### Improved
- **Victory detection**: three more `victory` crops, for setups where the shipped ones do not match. Every .png in that folder is tried as a variant of the same search, so extra crops only widen what is recognized.
- **Auto Play reference image**: an `auto_play` crop ships under `Assets/ui`, so a Detect block can key off the game's own Auto Playing indicator by name -- put the guarded action in the block's ELSE branch to skip it while auto play is running.

## [0.20.0] - 2026-09-09

### New
- **Summer event**: Event mode now runs the Summer event instead of Villian Invasion. Its own lobby entry (Event -> Summer -> gamemode card) leads to two kinds, picked in the Task Builder's Event field: **Infinite & Fishing** (unlimited waves, so it takes a **Stop After Wave** target and wants an Autoplay Macro Operation) and **Portal Mode**, which picks and activates a portal on the way in and selects the next one after every win.
- **Portals mode**: a new Task Queue mode that runs a portal from the Inventory instead of the event -- lobby -> Inventory -> Portals tab -> search -> activate, then the usual Solo/Matchmaking tail, picking a fresh portal after each win. Its **Portal Name** field is the search query *and* names the reference crop, looked up as `<name>_portal`, then `<name>`, then the shipped `summer_portal` -- so running a portal other than Summer only takes adding a crop under that name in Settings > General > Image Manager.
- **Drag block** (Macro Manager > Setup): press at one point, move to another while held, then release -- a swipe for UI a raw Click cannot reach. Both endpoints get their own position picker, and per-block **Steps** and **Duration (ms)** let the drag be slowed until the game stops reading it as a click. Allowed in Pre Start and every battle phase.
- **Examples picker**: Macro Manager gains an **Examples** button listing bundled routines with a description and per-phase block count. Picking one copies it into your own templates, so an example can never be saved over or deleted by accident.

### Improved
- **Expedition -- play on when extraction will not take**: in a matchmaking lobby the confirm can never register while other players keep going, and the run used to re-attempt the whole extract chain at every remaining checkpoint. After a few failed attempts it stops asking and plays the match out, still continuing each checkpoint. The counter resets per match.
- **Expedition -- notice a Victory the party caused**: the wave watcher only ever looked for `defeat`, so a party's extraction ended the match while the run kept clicking at checkpoints that no longer existed until the result timeout. `victory` is now checked alongside it.
- **Expedition encounters -- take the Continue when there is one**: an encounter that offers its own Continue is now cleared by that single click before any teleport, route or dialogue is attempted. It works on every map rather than the four with a bundled route, and cannot strand the character the way a recorded walk can.
- **Expedition encounters on unmapped maps**: a map with no recorded encounter route now gets one look at that Continue instead of being written off. With neither a Continue nor a route it still says so and leaves the encounter alone.
- **Expedition encounter dialogue** is now driven by the option's label text rather than four fixed coordinates -- the buttons move between clients and recolour between encounters, so position and colour both failed to pin them down.
- **Auto Challenge priority**: runs after each finished task, so the :00/:30 challenge resets are taken mid-run instead of waiting for the whole queue.
- **Wait for Wave** now releases once the counter has been unreadable past a ceiling, whether or not a reward card was seen. Cards drop for kills, so a run going badly produced none and stranded every block behind the wait -- including the deferred unit placements that would have earned them.

### Fixed
- Tower navigation now reaches the Tower screen reliably.
- Event tasks saved against the retired Villian Invasion Acts are migrated to an event kind on load and logged, instead of stopping the run on an Act that no longer exists.

### Removed
- **Villian Invasion**, along with its Acts, its relic-gated Act 4 auto-divert (the Act 4 on-drop / runs / macro / play-mode task settings), and their reference crops.

## [0.19.1] - 2026-08-13

### Improved
- **Auto Fuel interval control**: the minutes/hours fields now remain available while Auto is selected, so a custom refill wait can be entered instead of being locked to the automatic 8-hour Max interval.
- **Expedition encounters**: added native encounter handling, routes, and screen references for East Town, Flower Forest, Rose Kingdom, and School Grounds.
- **Expedition reliability**: improved checkpoint, wave counter, Repeat Stage, Start Game, upgrade-card, and unit re-placement handling.
- **Navigation recovery**: widened card searches, added lobby re-sync, and exits the AFK Chamber when it blocks progress.
- **macOS**: stabilized code-signing identity across updates and fixed the Macro Manager panel rendering blank while the macro runs.

### Fixed
- Villian Invasion navigation now opens the event card before selecting the game mode.
- East Town is now available in the Challenge and Bounty Story map list.

## [0.19.0] - 2026-08-11

### New
- **East Town map**: added to the expedition and story map lists.
- **Tower game mode**: Play -> Tower -> Select Stage -> Start (solo). Wins advance floors with `Next_Floor`; defeats retry with `Repeat_Floor`. Supports Normal and Traitless Tower. No map dropdown in the builder; Rose Kingdom is the internal default.
- **Auto Fuel custom interval**: set any refill interval in minutes or hours (e.g. 30 minutes, 1 hour), or leave it on Auto to keep the per-amount default behavior.

### Improved
- **Event mode**: waits for the Event gamemode screen, clicks a user-configurable card coordinate, then image-clicks the Event Gamemode button.
- **Disconnect recovery**: kills a stuck Roblox client before deep-link relaunch, still respecting the multi-window guard.
- **File dialogs**: cancelled or failed native file dialogs now return clean results instead of rejected JS promises.
- **Auto Upgrade Unit**: bounded wait for the unit info panel before searching `priority_upgrade`, so slow-rendering panels are no longer skipped. New `quote_on` / `quote_off` reference images for user-built Detect conditions.
- **OCR overhaul**:
  - Auto Bounty wave OCR: wave-anchored parsing with card-local crops and contrast voting. Clipped wave numbers (`6`, `6C`) now resolve to `60` instead of ending the run at wave 6.
  - Optional RapidOCR engine layer (separate `requirements-rapidocr.txt`, Python 3.13-safe) with a RapidOCR -> Windows OCR -> Tesseract fallback chain.
  - Windows OCR output is always filtered by the config whitelist, preserving stats/wave/shop reads.
  - Daily Challenge map OCR keeps the HUD-anchored crop primary and adds a fixed relative top-right crop as fallback.
- **Packaging**: PyInstaller keeps `winsdk`/`winrt` collection and adds RapidOCR data only when installed.

### Fixed
- Auto Bounty no longer exits early on wave-60 bounties when OCR clips the trailing zero.
- Challenge map OCR recovers when the Daily Challenge HUD label is not found.
