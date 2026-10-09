"""Tests for rep_switch.model."""

import pytest

from rep_switch import constants
from rep_switch import model
from rep_switch.test import conftest


def test_representation_rejects_unknown_type():
    with pytest.raises(ValueError, match="Unknown representation type"):
        model.Representation("proxy", "fbx", "/a.fbx")


def test_representation_requires_name_and_path():
    with pytest.raises(ValueError, match="needs a name"):
        model.Representation("", constants.USD, "/a.usd")
    with pytest.raises(ValueError, match="no file path"):
        model.Representation("proxy", constants.USD, "")


def test_representation_round_trip():
    rep = model.Representation("render", constants.MAYA_REF, "/a/render.ma")
    assert model.Representation.from_dict(rep.to_dict()) == rep


def test_from_dict_infers_type_from_extension():
    rep = model.Representation.from_dict({"name": "stage", "path": "/a/stage.usdc"})
    assert rep.rep_type == constants.USD


def test_infer_type_rejects_unknown_extension():
    with pytest.raises(ValueError, match="Cannot infer"):
        model.infer_type("/a/thing.obj")


def test_asset_rejects_duplicate_names():
    rep = model.Representation("proxy", constants.GPU_CACHE, "/a.abc")
    with pytest.raises(ValueError, match="duplicate"):
        model.Asset("treeA", (rep, rep))


def test_asset_rejects_unknown_default():
    with pytest.raises(ValueError, match="not defined"):
        conftest.make_asset(default="hero")


def test_find_prefers_names_over_types(asset):
    assert [rep.name for rep in asset.find("proxy")] == ["proxy"]
    assert [rep.name for rep in asset.find(constants.MAYA_REF)] == ["render"]
    assert asset.find("nothing") == []


def test_get_raises_for_unknown(asset):
    with pytest.raises(KeyError):
        asset.get("hero")


def test_default_representation(asset):
    assert asset.default_representation().name == "proxy"
    assert conftest.make_asset(default="render").default_representation().name == "render"
    assert model.Asset("empty").default_representation() is None


@pytest.mark.parametrize(
    "asset_name, rep_name, expected",
    [
        ("treeA", "proxy", "treeA_proxy"),
        ("tree-A v2", "render", "tree_A_v2_render"),
        ("01_rock", "proxy", "_01_rock_proxy"),
    ],
)
def test_namespace_for(asset_name, rep_name, expected):
    assert model.namespace_for(asset_name, rep_name) == expected
