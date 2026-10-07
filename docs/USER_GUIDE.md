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

The **Camera Setup** row at the top of Pre Start is part of the template: on
the first entry into a stage the macro tilts the camera top-down and zooms out
before any block runs. Place Unit and Walk Path positions depend on that view,
so leave it **On** for any operation that places units by position. Switch it
**Off** only for operations that do not, for example one that just turns on the
game's Auto Play.

The camera setup zooms in with I, looks down with the mouse and zooms back out
with O. Roblox zooms a step per frame, so where it runs at fewer frames per
second -- over Remote Desktop, for example -- the same key press zooms less far.
If the camera does not end up looking straight down and fully zoomed out there,
hold the keys longer under **Settings > Debug > Camera Setup Timing**.

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

### Monster Clash

**Monster Clash** is the Battle Event in the Events menu. A task goes Events >
Monster Clash > Play Event > Play - Choose Stage > Select Stage > Start, always
Solo, and plays the map with its Macro Operation. Sometimes a cleared map spawns a
helicopter instead of the Victory screen -- all that shows is the **Game
Results** button. The macro then waits about 15 seconds, presses E to board it,
and plays the second map it flies to, placing the units again with the task's
**Macro Operation (Helicopter)** ("Same as above" reuses the first one). One
repeat is one such run. Either map's result screen only leads back to the
lobby, so every repeat goes in through the Events menu again. The crops for
the way in ship with the macro -- `monster_clash` (the entry in the Events
menu), `monster_clash_play_event` and `monster_clash_choose_stage`; if one does
not match on your setup, add another crop under the same name in the Image
Manager. A task whose crop folder is left empty is skipped with a note in the
log.

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

For challenges, open **Challenge** separately. Enable Daily and/or the desired
Regular Challenge slots, select Solo or Matchmaking, and assign an operation
for each map that may appear. Challenge automation runs before the normal task
queue.

Regular Challenge picks the map for you, so every Story map needs its own
Macro Operation assigned -- including **Crimson Shore** (the 7th map) and
**Flaming Monastery** (the 8th). Auto Challenge and Auto Bounty will not start
while any Story map is left without one. Each map needs two separate crops,
and they come from different screens:

| Folder | Cropped from | Used for |
| --- | --- | --- |
| `Assets/maps/<Map>` | the Play > Story card carousel | picking the map yourself in a task |
| `Assets/ui/<Map>` | the in-battle HUD, once you are on the map | Regular Challenge recognizing which map it landed on |

Without the second one, the map is skipped by the image search and
detection falls back to reading the map label with OCR. The other maps keep
matching normally -- a map with no crop is skipped, not fatal -- but the OCR
path is the slower and less reliable of the two.

The **World Boss** (Events > World Boss > Ancient One) sits in the same
Challenge section. It can be played once per hour, and Enter Encounter only
works in the first 10 minutes after the full hour. With it switched on, the
macro steps out of its task at the first break between repeats from :00 to :09
-- like a ready Challenge -- to play it, always Solo, then carries on. Past :09
it leaves that hour alone; a round that is still running then means the hour is
missed, so the longer a single round takes, the more hours get missed. It runs on one map, so it has its own Macro Operation
instead of the Story map list, and it cannot be switched on until one is
assigned. Its way there uses two crops that ship with the macro,
`world_boss_ancient_one` (the World Boss entry in the Events menu) and
`world_boss_enter_encounter` (the Enter Encounter button); if one does not match
on your setup, add another crop under the same name in the Image Manager. One try per hour is all it gets: a win, a
loss or an entry that fails all rest it until the next full hour.

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

