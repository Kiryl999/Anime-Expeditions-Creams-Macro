auto_play_on

The game's Auto Play button while it is ON -- it reads "Auto Playing". Used
by a Macro Operation with Macro Manager > Pre Start > Auto Play switched on
(core/runner_auto_play.py): Start Game is only pressed once this shows, and
during the round the button is watched so it can be switched back on.

Seeing this is what keeps the macro from clicking: the button toggles, and a
click while it is on switches Auto Play off. Its counterpart is
Assets/ui/auto_play_off/ ("Auto Play"), which is what the macro clicks.

One crop ships with the macro. If it does not match on your setup -- over
Remote Desktop in particular -- add another: drop one or more PNG crops here
(any filename ending .png), or save one via Settings > General > Image
Manager under this exact name. Crop the text "Auto Playing" with a little of
the green around it, without the gear icon. Multiple files are treated as
interchangeable variants of this image and all tried when matching. Capture
crops at the reference window size (1152x756). See Assets/ui/README.txt.

Not the same as Assets/ui/auto_play/, which is free for Detect blocks.
