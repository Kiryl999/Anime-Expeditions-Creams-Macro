skip_cutscene

The "Skip Cutscene" button of a secret-unit reveal. Some portal rounds can
drop a secret unit once won, and its reveal plays a cutscene instead of the
three-portal offer. A Portals task looks for this button every 2 seconds
during the round and clicks it once when it shows (core/runner.py,
_click_skip_cutscene_if_found). What is left then is a lone "Game Results"
button (Assets/ui/game_results/), which the macro clicks to open the Victory
screen; there it goes on with "Select Portal" (Assets/ui/select_new_portal/),
or leaves on a task's last repeat.

Drop one or more PNG crops here (any filename ending .png), or save one via
Settings > General > Image Manager under this exact name. Crop the button's
text "Skip Cutscene" with a little of the button around it. Multiple files
are treated as interchangeable variants of this image and all tried when
matching. Capture crops at the reference window size (1152x756). See
Assets/ui/README.txt.

While this folder holds no image, the watch does nothing.
