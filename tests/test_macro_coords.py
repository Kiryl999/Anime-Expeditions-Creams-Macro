import main


def test_team_button_coordinate_override_can_be_saved_and_cleared(monkeypatch):
    state = {}
    monkeypatch.setattr(main.cfg, "load", lambda: dict(state))

    def update(patch):
        state.update(patch)
        return dict(state)

    monkeypatch.setattr(main.cfg, "update", update)
    api = object.__new__(main.Api)

    assert api.set_macro_coords({"team_button_x": 438, "team_button_y": 570})["saved"] == [
        "team_button_x", "team_button_y"
    ]
    coords = api.get_macro_coords()
    assert coords["team_button_x"] == 438
    assert coords["team_button_y"] == 570

    assert api.clear_macro_coord("team_button")["ok"] is True
    coords = api.get_macro_coords()
    assert coords["team_button_x"] is None
    assert coords["team_button_y"] is None
    assert api.clear_macro_coord("screen_middle")["ok"] is False


def test_a_region_override_clears_all_four_of_its_values(monkeypatch):
    """portal_list is a BOX, not a point. Clearing only x/y would leave w/h
    holding stale numbers on screen while the readers -- which need all four
    -- already treat the box as unset."""
    state = {}
    monkeypatch.setattr(main.cfg, "load", lambda: dict(state))

    def update(patch):
        state.update(patch)
        return dict(state)

    monkeypatch.setattr(main.cfg, "update", update)
    api = object.__new__(main.Api)

    api.set_macro_coords({"portal_list_x": 533, "portal_list_y": 208,
                          "portal_list_w": 343, "portal_list_h": 88})
    assert api.get_macro_coords()["portal_list_w"] == 343

    cleared = api.clear_macro_coord("portal_list")
    assert cleared["ok"] is True
    assert sorted(cleared["cleared"]) == [
        "portal_list_h", "portal_list_w", "portal_list_x", "portal_list_y"]
    coords = api.get_macro_coords()
    assert all(coords[f"portal_list_{axis}"] is None for axis in ("x", "y", "w", "h"))


def test_clearing_a_prefix_leaves_the_other_optional_ones_alone():
    """The clear is driven by a prefix match, so a prefix that is a substring
    of another must not sweep it up."""
    optional = [key for key, value in main.MACRO_COORD_DEFAULTS.items() if value is None]
    for prefix in main.Api.OPTIONAL_COORD_PREFIXES:
        owned = [k for k in optional if k.startswith(f"{prefix}_")]
        assert owned, f"{prefix} has no optional coordinates"
        for other in main.Api.OPTIONAL_COORD_PREFIXES:
            if other != prefix:
                assert not any(k.startswith(f"{other}_") for k in owned), \
                    f"{prefix} would also clear {other}"
