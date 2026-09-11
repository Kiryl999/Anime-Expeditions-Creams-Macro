# Changelog

All notable changes to Anime Expeditions (Cream's Macro) are documented here.

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
