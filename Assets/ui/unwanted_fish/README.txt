unwanted_fish -- the fish that get thrown away

One crop PER unwanted fish, all tried as interchangeable variants of this
one name: a hit on ANY .png in here means the slot holds junk, and the macro
drags that slot onto the bin right of slot 6 (core/runner.py,
_tick_fish_inventory). Adding a fish to the junk list is dropping another
crop in here -- no code change.

The counterpart is Assets/ui/wanted_fish/, whose icons are LEFT-CLICKED once
to cash them in. An icon must not sit in both folders: unwanted is asked
first, so a duplicate would be binned.

Crop the icon AS IT RENDERS IN THE INVENTORY SLOT, tightly, with as little
of the slot frame as possible -- the frame is the same for every fish, so
including it makes them all look alike to the search.

NOTE on the crops that were already here: booster_fish.png and
mirror_fish.png are full slot icons (~55x58) and are the right shape for
this. tome.png, tome_rare.png and tome_legend.png are small text labels
(30x12 to 62x24) left over from before this folder was wired up to
anything. Text that small over busy art matches easily where it shouldn't,
and a false hit here BINS A FISH -- if a paying fish goes missing, re-crop
those three as icons or remove them.
