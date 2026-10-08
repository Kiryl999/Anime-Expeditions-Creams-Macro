unwanted_fish -- the fish that are left alone

One crop PER unwanted fish, all tried as interchangeable variants of this
one name: a hit on ANY .png in here means the slot holds a fish the macro
must not touch -- it is never clicked and never moved (core/runner.py,
_tick_fish_inventory). Unwanted is asked first, so a fish that also looks
like a wanted one is still left alone. Adding a fish to this list is
dropping another crop in here -- no code change.

The macro used to drag these onto the bin right of slot 6. That is gone:
an unwanted fish now stays in its slot. Once all six slots are full the
game cashes every fish in by itself.

The counterpart is Assets/ui/wanted_fish/, whose icons are LEFT-CLICKED once
to cash them in. An icon must not sit in both folders: unwanted is asked
first, so a duplicate would never be cashed in. This folder may be empty --
then every wanted hit is clicked.

Crop the icon AS IT RENDERS IN THE INVENTORY SLOT, tightly, with as little
of the slot frame as possible -- the frame is the same for every fish, so
including it makes them all look alike to the search.

NOTE on the crops that were already here: booster_fish.png and
mirror_fish.png are full slot icons (~55x58) and are the right shape for
this. tome.png, tome_rare.png and tome_legend.png are small text labels
(30x12 to 62x24) left over from before this folder was wired up to
anything. Text that small over busy art matches easily where it shouldn't,
and a false hit here keeps a paying fish from being cashed in -- if one
stays in its slot, re-crop those three as icons or remove them.
