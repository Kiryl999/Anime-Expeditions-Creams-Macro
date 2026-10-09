auto_play_off

The game's Auto Play button while it is OFF -- it reads "Auto Play". Used by
a Macro Operation with Macro Manager > Pre Start > Auto Play switched on
(core/runner_auto_play.py): the macro clicks the button only when this shows
and Assets/ui/auto_play_on/ ("Auto Playing") does not, so a click can never
switch Auto Play off.

One crop ships with the macro. If it does not match on your setup -- over
Remote Desktop in particular -- add another: drop one or more PNG crops here
(any filename ending .png), or save one via Settings > General > Image
Manager under this exact name. Crop the text "Auto Play" with a little of
the green around it, without the gear icon. Multiple files are treated as
interchangeable variants of this image and all tried when matching. Capture
crops at the reference window size (1152x756). See Assets/ui/README.txt.

Not the same as Assets/ui/auto_play/, which is free for Detect blocks.
