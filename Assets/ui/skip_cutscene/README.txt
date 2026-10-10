skip_cutscene

The "Skip Cutscene" button of a cutscene over the round -- a secret-unit
reveal once a portal or raid round is won. Every Portals and every Raid task
(any map, any Act) looks for this button every 2 seconds during the round
and clicks it once when it shows (core/runner.py,
_click_skip_cutscene_if_found). What is left then is a lone "Game Results"
button (Assets/ui/game_results/), which the macro clicks to open the Victory
screen. A raid goes on from there as from any Victory screen (Repeat Stage,
or Leave on the last repeat); a portal round goes on with "Select Portal"
(Assets/ui/select_new_portal/), or leaves on a task's last repeat.

This replaced the "Click anywhere to close" watch Spirit City and Snowy
Castle Act 3 used to have.

Drop one or more PNG crops here (any filename ending .png), or save one via
Settings > General > Image Manager under this exact name. Crop the button's
text "Skip Cutscene" with a little of the button around it. Multiple files
are treated as interchangeable variants of this image and all tried when
matching. Capture crops at the reference window size (1152x756). See
Assets/ui/README.txt.

While this folder holds no image, the watch does nothing.
