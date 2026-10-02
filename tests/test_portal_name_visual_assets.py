"""The shipped portal NAME crop has to tell portals apart by name alone.

That is the whole reason it may be looked for before the picker is searched
(see PortalsOp._select_portal_on_picker): the portals share one hourglass art
on differently tinted cards, and a crop that matched another portal's card
would click that portal. Checked against the real card crops on disk -- the
Summer cards of several tiers, and the one Infernal card we have.
"""
from pathlib import Path

import cv2
import numpy as np
import pytest

from core import vision

NAME = "portal_name_summer"

# Picker cards showing the full "Summer Portal" label, on four tier tints.
SUMMER_CARDS = (
    "portal_card/portal.png",            # Tier 5, teal
    "portal_card/portal_card.png",       # Tier 5, pink
    "portal_card/portal_card_alt3.png",  # Tier 3, purple
    "portal_card/portal_card_alt7.png",  # gold
    "portal_card/portal_card_alt8.png",  # Tier 4, gold
)
INFERNAL_CARD = "portal_offer/portal_offer_alt5.png"  # Tier 2, "Infernal Portal"


def _gray(relative: str):
    image = cv2.imread(str(Path(vision.UI_ASSETS_DIR, relative)), cv2.IMREAD_GRAYSCALE)
    assert image is not None, relative
    return image


def _match(haystack):
    vision.clear_template_cache()
    try:
        return vision.find_in_gray_multiscale(haystack, NAME)
    finally:
        vision.clear_template_cache()


def test_the_summer_name_crop_ships():
    assert vision.template_variant_paths(NAME), f"{NAME} is missing from Assets/ui"


@pytest.mark.parametrize("card", SUMMER_CARDS)
def test_the_summer_name_is_found_on_every_tier(card):
    match = _match(_gray(card))
    assert match is not None
    assert match["score"] >= vision.DEFAULT_THRESHOLD


def test_the_summer_name_is_not_found_on_the_infernal_card():
    assert _match(_gray(INFERNAL_CARD)) is None


def test_the_summer_name_does_not_match_a_blank_screen():
    assert _match(np.zeros((756, 1152), dtype=np.uint8)) is None
