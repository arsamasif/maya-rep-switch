"""Tests for rep_switch.panel_model."""

import os

import pytest

from rep_switch import constants
from rep_switch import model
from rep_switch import panel_model
from rep_switch import planner
from rep_switch.test import conftest


def _state(node, asset, loaded=""):
    return planner.AssetState(node, asset, loaded)


def test_build_rows_sorted_with_default_status():
    states = [
        _state("|b", conftest.make_asset("Zed"), "proxy"),
        _state("|a", conftest.make_asset("alpha")),
    ]
    rows = panel_model.build_rows(states)
    assert [row.asset for row in rows] == ["alpha", "Zed"]
    assert rows[0].status == constants.UNLOADED
    assert rows[1].status == constants.LOADED
    assert rows[1].choices == ("proxy", "render", "stage")


def test_explicit_status_and_labels():
    rows = panel_model.build_rows(
        [_state("|a", conftest.make_asset("a"), "render")], {"|a": constants.MISSING}
    )
    assert rows[0].label == "render (missing)"
    assert rows[0].needs_attention
    unloaded = panel_model.build_rows([_state("|b", conftest.make_asset("b"))])[0]
    assert unloaded.label == "unloaded"
    assert not unloaded.needs_attention


def test_switch_all_choices_ranked_by_coverage():
    only_render = model.Asset(
        "lamp", (model.Representation("render", constants.MAYA_REF, "/lamp.ma"),)
    )
    rows = panel_model.build_rows(
        [_state("|a", conftest.make_asset("a")), _state("|b", only_render)]
    )
    assert panel_model.switch_all_choices(rows) == ["render", "proxy", "stage"]
    assert panel_model.switch_all_choices(rows, limit=1) == ["render"]


def test_coverage_counts():
    rows = panel_model.build_rows(
        [
            _state("|a", conftest.make_asset("a"), "proxy"),
            _state("|b", conftest.make_asset("b"), "render"),
        ]
    )
    assert panel_model.coverage(rows, "proxy") == (2, 1)
    assert panel_model.coverage(rows, "hero") == (0, 0)


@pytest.mark.parametrize("status, rep_type, icon", [
    (constants.LOADED, constants.GPU_CACHE, "repAsset_gpuCache.png"),
    (constants.LOADED, constants.USD, "repAsset_usd.png"),
    (constants.LOADED, constants.MAYA_REF, "repAsset_mayaRef.png"),
    (constants.LOADED, constants.ALEMBIC, "repAsset_alembic.png"),
    (constants.UNLOADED, "", "out_repAsset.png"),
    (constants.MISSING, constants.USD, "repAsset_missing.png"),
    (constants.ERROR, "", "repAsset_missing.png"),
])
def test_icon_for(status, rep_type, icon):
    assert panel_model.icon_for(status, rep_type) == icon


def test_every_icon_ships_with_the_repo():
    icons = os.path.join(os.path.dirname(__file__), "..", "..", "..", "icons")
    names = list(constants.ICON_BY_TYPE.values()) + [constants.ICON_UNLOADED, constants.ICON_MISSING]
    for name in names:
        for suffix in ("", "_150", "_200"):
            stem, extension = os.path.splitext(name)
            assert os.path.isfile(os.path.join(icons, stem + suffix + extension))


def test_outliner_color_for():
    assert panel_model.outliner_color_for(constants.LOADED, constants.USD) == (
        constants.OUTLINER_COLOR_BY_TYPE[constants.USD]
    )
    assert panel_model.outliner_color_for(constants.MISSING) == constants.OUTLINER_COLOR_MISSING
    assert panel_model.outliner_color_for(constants.UNLOADED) is None
    colors = list(constants.OUTLINER_COLOR_BY_TYPE.values()) + [constants.OUTLINER_COLOR_MISSING]
    assert len(set(colors)) == len(colors)
