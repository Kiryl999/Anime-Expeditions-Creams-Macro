# Cream's Macro: Complete User Guide

This guide covers installation, first-time setup, creating a farming routine,
running it safely, troubleshooting, and the commands used by source users and
contributors.

> **Important:** This is an unofficial automation tool. Game updates can move
> buttons or change screens, and using automation may violate Roblox or game
> rules. Use it at your own risk. Test with a short run before leaving it
> unattended, and never share a Discord webhook URL or your `settings.json`.

## 1. Choose an installation method

### Windows release (recommended)

1. Download `Creams-Macro-Anime-Expeditions-Windows.zip` from the
   [latest release](https://github.com/Cweamy/Anime-Expeditions-Creams-Macro/releases/latest).
2. Extract the entire ZIP to a normal folder. Do not run the executable from
   inside the ZIP.
3. Keep the executable and `Assets` folder together.
4. Run the executable. If SmartScreen appears, choose **More info**, verify the
   publisher/source, then choose **Run anyway** only if you trust the download.

Install Tesseract OCR if you want reward and match-stat reading. The rest of
the macro can run without OCR.

### Windows source install

Open PowerShell and run:

```powershell
git clone https://github.com/Cweamy/Anime-Expeditions-Creams-Macro.git
Set-Location Anime-Expeditions-Creams-Macro
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

On later launches:

```powershell
Set-Location Anime-Expeditions-Creams-Macro
.\.venv\Scripts\Activate.ps1
python main.py
```

You can also double-click `run.bat` after installing the dependencies.

### macOS source install (experimental)

In Terminal:

```bash
git clone https://github.com/Cweamy/Anime-Expeditions-Creams-Macro.git
cd Anime-Expeditions-Creams-Macro
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
chmod +x run.sh
./run.sh
```

Grant Terminal or the packaged app **Accessibility**, **Input Monitoring**, and
**Screen Recording** in **System Settings > Privacy & Security**. Roblox runs
beside the macro rather than inside it on macOS. If the windows do not fit,
choose a display setting with more logical screen space.

## 2. Prepare Roblox

1. Start Roblox and join Anime Expeditions.
2. Return to the main lobby before starting the macro.
3. Leave Roblox UI scale and display scaling consistent between recording and
   playback.
4. Avoid covering the Roblox window, changing its size, or moving it while the
   macro is running. The Windows build normally docks it automatically.
5. Run one short test while watching the screen before using repeat counts.

## 3. Configure the macro

### General settings

Open **Settings > General** and check the following:

- Confirm the macro detects the Roblox window.
- Set the Start, Stop, Pause, game-window toggle, and skip-wait hotkeys. The
  defaults are F1 Start, F2 Stop, F5 Pause, and F4 toggle game window.
- Use **Image Manager** if the supplied reference images do not match your
  Roblox rendering. Capture a tight crop of the requested button or label.
- Configure Tesseract only if OCR diagnostics report that it cannot be found.

### Discord webhook (optional)

1. Create a webhook in the desired Discord channel.
2. Paste its URL into the webhook setting and enable notifications.
3. Use the test action before a real run.
4. Treat the URL like a password. Regenerate it in Discord if it is exposed.

Optional **Progress Updates** can send task and challenge start/finish notifications
as the macro moves through the queue.

## 4. Build a reusable macro operation

Open **Macro Manager** and create the actions that should happen before or
during a match. Save the result as a named template.

Common blocks include:

- **Place Unit:** select a slot and position. Use click verification where
  available so rejected placements can be retried.
- **Click / Send Key:** perform a simple UI action or hotkey.
- **Walk Path:** record WASD movement and ability keys, save the path, then add
  it to the operation.
- **Record:** capture a timed mouse-and-keyboard sequence for actions that are
  too complex for individual blocks.
- **Once:** enable this on setup actions that should run only on the first entry
  to a stage, not on every repeated battle.

Keep recordings short and deterministic. Prefer dedicated blocks over a long
recording when possible, because they are easier to adjust after a game update.

### Expedition encounters

Expedition nodes can drop an encounter that has to be walked to and talked to.
The macro handles this itself: when the encounter marker appears it teleports to
spawn, walks that map's route, and interacts. Nothing is needed in your template
beyond your unit placements.

Routes ship for School Grounds, Rose Kingdom, Flower Forest, and East Town. For
any other map the encounter is left alone and logged. To add one, record a walk
from spawn to that map's NPC and map it in
`Assets/default_encounter_walk_paths.json`:

```json
{ "Your Map": "Your recorded path name" }
```

A route that does not fit your spawn stops safely: the interact prompt has to be
found before anything is clicked, so a walk that lands somewhere wrong logs and
gives up rather than clicking at the world.

### Placing a unit you cannot afford yet (Expedition)

Pre Start runs **before** the round begins, so no income has arrived while it
is running. Placing a unit there only *stages* it: nothing is really on the
board until the round starts, and anything the purse cannot cover at that
moment is silently dropped. Expedition starts you with far less than a unit
costs, so a team can end up a unit or two short for the whole match while the
log reports every placement as fine.

Pre Start cannot detect this. Verification has nothing to read yet -- before
the round, no unit is deployed, so a check there reports failure for every
unit whether or not it would have worked.

Put the units you cannot afford up front in the **Battle** phase instead, with
a wait in front of them:

```
Pre Start:  Place Unit #1        (cheap -- affordable immediately)
            Place Unit #2
Battle:     Wait for Wave -> 2
            Place Unit #3
            Place Unit #4
```

Battle blocks run once per match, in order, one block per poll -- so
consecutive blocks land roughly a second apart, and the round keeps playing
around them.

**Use "Wait for Wave", not "Wait".** They are not interchangeable here:

- **Wait for Wave** is checked between polls and gives the loop back in
  between, so upgrade cards still get picked, wave Continues still get
  clicked, and Expedition encounters are still handled while it waits.
- **Wait (ms)** sleeps in place. Everything else in the match loop stops for
  the whole duration -- a 60-second Wait in the Battle phase means a minute
  with no card selection, no Continue clicks and no result detection. Fine
  for a few hundred milliseconds between two clicks; not for waiting out
  income.

Waiting on a wave is also the more reliable condition, since it tracks what
actually pays out rather than guessing how long that takes on a given map.

## 5. Create the task queue

Open **Task**, add tasks in the order they should run, and configure each one:

1. Choose Story, Raid, Expedition, or another supported mode.
2. Select its map, stage or act, difficulty, and Solo or Matchmaking.
3. Set a small repeat count for the first test.
4. Assign the saved Macro Manager operation to the task.
5. Save the queue or export it if you want a backup/shareable setup.

### Raid maps

Both raid stories -- **Spirit City** and **Snowy Castle** -- sit in the same
Play -> Raid carousel, have the same 3 Acts, and are locked to Hard in-game,
so they are picked exactly like each other from the Map dropdown.

Snowy Castle is new enough that no reference image ships for it. Capture its
name label once via **Settings > General > Image Manager > Map Names** (the
folder name has to be exactly `Snowy Castle`); crop only the bold white map
name under the card art, not the thumbnail and not the whole card. Until that
crop exists the map search fails immediately without even scrolling the
carousel -- there is no image to match -- and the task stops after 3 retries
from the lobby with a "no reference image" message in the log naming the
missing folder.

If the crop exists but the card still isn't found, that looks different: the
macro scrolls through the whole carousel three times first and then says the
label never matched. Add a second crop to the same folder in that case rather
than replacing the first -- every .png in the folder is tried.

### Portal mode (event portals)

Portals are activated from the **inventory**, not from Play, so this mode has
its own navigation: lobby -> Inventory -> Portals tab -> the portal's card ->
**Activate Portal** -> Start. There is no stage, no difficulty, and no
Solo/Matchmaking choice. Every repeat goes back to the lobby and activates a
portal again, because a portal is spent by the run that used it.

The event is new enough that no reference images ship for it. Capture these
under **Settings > General > Image Manager > Capture Roblox** before running a
portal task -- the folder name has to match exactly:

| Image | What to crop |
| --- | --- |
| `nav_inventory` | the lobby's Inventory/Items button |
| `portal_tab` | the Portals tab inside the inventory |
| `portal_summer` | the portal's own card (one image per portal offered) |
| `portal_activate` | the **Activate Portal** button |
| `portal_card_ready` | something visible *only* while the 3 cards offered after a win are pickable -- the heading, the countdown, or one card's frame |
| `portal_card_slot` | optional: one card's frame, cropped so all three match |

As a portal run ends the event offers 3 new portal cards and takes the offer
away again after about 15 seconds. That happens **before the Victory screen
appears**, not after it, so the macro watches for it from inside the match
rather than after the result -- one attempt per run.

**Portal Card** in the Task Builder picks which one to take. Where the three
sit on screen comes from `portal_card_slot` when that crop exists (all three
are located automatically, left to right); otherwise set the points under
**Settings > Debug > Macro Coordinates > Portal Cards**, using **Pick** on a
live capture rather than estimating them. The macro confirms the choice window
actually closed after the click -- if it did not, the log says so instead of
continuing into a portal that was never chosen.

If your `portal_card_ready` crop is a portal *name*, also fill in **Portal Card
Search Area** (x, y, width, height) in the same Settings section. The same name
can appear in the HUD or on another card, and restricting the search to the
strip the cards occupy is what makes a match mean "the cards are up" rather
than "that word is somewhere on screen". All four values have to be set for it
to apply; leave them empty to search the whole screen.

Adding another portal takes two edits that must match: an entry in
`PORTAL_IMAGES`/`PORTAL_ORDER` (`core/runner_constants.py`) and the same string
in `TASK_DATA.portal.maps` (`ui/app.js`). `tests/test_portal_mode.py` fails if
they drift apart.

For challenges, open **Challenge** separately. Enable Daily and/or the desired
Regular Challenge slots, select Solo or Matchmaking, and assign an operation
for each map that may appear. Challenge automation runs before the normal task
queue.

Regular Challenge picks the map for you, so every Story map needs its own
Macro Operation assigned -- including **Crimson Shore**, the 7th map. Two
separate crops are involved and they come from different screens:

| Folder | Cropped from | Used for |
| --- | --- | --- |
| `Assets/maps/Crimson Shore` | the Play > Story card carousel | picking the map yourself in a task |
| `Assets/ui/Crimson Shore` | the in-battle HUD, once you are on the map | Regular Challenge recognizing which map it landed on |

Without the second one, Crimson Shore is skipped by the image search and
detection falls back to reading the map label with OCR. The other maps keep
matching normally -- a map with no crop is skipped, not fatal -- but the OCR
path is the slower and less reliable of the two.

## 6. Start and monitor a run

1. Put the character in the lobby and close unexpected popups.
2. Open **Dashboard** and press **Start**, or use the configured Start hotkey.
3. Watch the first full cycle: navigation, placement, battle, result detection,
   and return/repeat.
4. Use **Pause** only when you need to inspect the current state. Use **Stop**
   before manually moving Roblox or changing task settings.
5. Check the Dashboard log first if a run stops. It normally names the image,
   screen, or recovery step that failed.

## 7. Troubleshooting

### A button or screen is not detected

- Confirm Roblox is visible, at the expected size, and on the expected screen.
- Open **Settings > General > Image Manager** and replace or add a reference
  crop for the name shown in the log.
- Crop tightly, but retain enough unique pixels to avoid matching unrelated UI.
- Remove overlays, notifications, and unusual UI scaling, then test again.

Reference crops are specific to the size the game renders at. `core.vision`
only sweeps +/-10% around a crop's own size, so a crop captured on a different
setup can miss outright rather than score slightly lower. On one machine a
shipped crop peaked at 0.61 where a locally captured crop of the same button
scored 1.00. If a name will not match, capture it yourself in the Image Manager
before adjusting thresholds.

### Two similar states match each other's crop

Templates are matched in greyscale, so two states of the same control that
share a border, background shape, and label can score highly against each
other. Colour differences do not help. On one setup a whole-button crop of an
*unset* control matched the *set* version of that same button at 0.92, over the
0.90 default threshold.

- Crop tightly around the part that actually differs (the glyph or digit)
  rather than the whole button.
- Or raise that name's Match threshold in the Image Manager above the score the
  wrong state reaches.
- Check both directions with the Detect block's **Test now** button: a crop
  should hit on the state it is named for and miss on the other one. Read the
  reported location too -- a miss whose best hit is somewhere unrelated on
  screen is no match at all, not a near miss.

### A Detect block drives an action that must not repeat

Detect treats a missing reference image, an unreadable screen, and an invalid
condition all as *not found*, so every unknown lands in the Else branch. Put
the branch that must not fire by accident behind a positive match:

```
find('quote_off') and not find('quote_on')    -> Then = retry
```

Written the other way round -- retrying whenever a "done" image fails to match
-- every unknown becomes a retry. This matters for controls that cycle rather
than being set, where applying the same value twice is not a no-op.

### Clicks land in the wrong place

- Stop the macro, return Roblox to its normal docked/side-by-side position, and
  restart the app.
- Do not resize Roblox after recording paths or positions.
- Re-record affected placements or paths at the same display scale used for
  normal runs.

### OCR stats or rewards are missing

- Install the desktop Tesseract application; the Python requirements do not
  include the OCR executable.
- Restart the macro after installation.
- Use the debug tools in Settings to test match-stat and reward reading.

### macOS captures are black or input does nothing

- Recheck Accessibility, Input Monitoring, and Screen Recording permissions.
- After changing permissions, fully quit and reopen Terminal/the macro.
- Ensure Roblox fits beside the control panel and is not off-screen.

### Recovery keeps looping

- Press Stop and return to the lobby manually.
- Read the last log entries and refresh the named reference image.
- Reduce the queue to one task and one repeat until the complete cycle succeeds.

## 8. Command reference

Run the app or diagnostics from the repository root:

```powershell
# Start the GUI on Windows
python main.py

# Run CLI input/window diagnostics without the GUI
python main.py --test

# Install runtime and developer dependencies
python -m pip install -r requirements.txt -r requirements-dev.txt

# Run all tests
python -m pytest -q

# Run one test module
python -m pytest -q tests/test_runner_challenge.py

# Lint the Python source
python -m ruff check .
```

Git update commands for a source installation:

```powershell
git status
git pull --ff-only origin main
python -m pip install -r requirements.txt
```

Do not run `git pull` with unsaved local edits. Back up `settings.json`, custom
templates, paths, recordings, and changed `Assets` before making large manual
changes, even though the built-in updater is designed to preserve user data.

## 9. Contributor workflow

Create a branch and verify changes before opening a pull request:

```powershell
git switch -c fix/short-description
python -m pytest -q
python -m ruff check .
git status
git add path\to\changed-file.py tests\test_changed_file.py
git commit -m "fix: short description"
git push -u origin fix/short-description
```

Pull requests should explain the problem, the behavior change, how the change
was tested, and any platform or real-game testing that is still needed.

## 10. Safe unattended-use checklist

- A one-repeat test completed successfully from lobby back to lobby.
- The correct task and operation are assigned.
- Stop and Pause hotkeys work.
- Roblox is unobstructed and will not be resized.
- Discord webhook testing succeeded, if enabled.
- The computer will not sleep and no scheduled restart is pending.
- Repeat counts and resource limits are reasonable.

