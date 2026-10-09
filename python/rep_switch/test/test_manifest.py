"""Tests for rep_switch.manifest."""

import json
import os

import pytest

from rep_switch import constants
from rep_switch import manifest
from rep_switch.test import conftest

YAML_MANIFEST = """\
asset: treeA
default: proxy
representations:
  proxy: {type: gpuCache, path: geo/treeA_proxy.abc}
  render: geo/treeA_render.ma
  stage:
    path: $REP_TEST_ROOT/treeA.usda
"""


def test_read_yaml_mapping_form(tmp_path, monkeypatch):
    monkeypatch.setenv("REP_TEST_ROOT", "/published")
    path = tmp_path / "treeA.yaml"
    path.write_text(YAML_MANIFEST)

    (asset,) = manifest.read_manifest(str(path))

    assert asset.name == "treeA"
    assert asset.default == "proxy"
    assert asset.names == ("proxy", "render", "stage")
    assert asset.get("proxy").rep_type == constants.GPU_CACHE
    assert asset.get("render").rep_type == constants.MAYA_REF
    assert asset.get("render").file_path == os.path.join(str(tmp_path), "geo", "treeA_render.ma")
    assert asset.get("stage").file_path == os.path.normpath("/published/treeA.usda")


def test_read_json_list_form(tmp_path):
    document = {
        "assets": [
            {"asset": "rockA", "representations": [{"name": "proxy", "path": "/abs/rock.abc"}]},
            {"asset": "rockB", "representations": [{"name": "render", "path": "rockB.ma"}]},
        ]
    }
    path = tmp_path / "rocks.json"
    path.write_text(json.dumps(document))

    assets = manifest.read_manifest(str(path))

    assert [asset.name for asset in assets] == ["rockA", "rockB"]
    assert assets[0].get("proxy").rep_type == constants.ALEMBIC
    assert assets[0].get("proxy").file_path == os.path.normpath("/abs/rock.abc")


@pytest.mark.parametrize("suffix", [".json", ".yaml"])
def test_write_then_read_round_trip(tmp_path, suffix):
    assets = [conftest.make_asset("treeA", default="render"), conftest.make_asset("treeB")]
    path = str(tmp_path / ("scene" + suffix))

    manifest.write_manifest(path, assets)

    assert manifest.read_manifest(path) == assets


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="Missing manifest"):
        manifest.read_manifest(str(tmp_path / "nope.yaml"))


def test_unsupported_extension(tmp_path):
    path = tmp_path / "asset.txt"
    path.write_text("asset: x")
    with pytest.raises(manifest.ManifestError, match="Unsupported"):
        manifest.read_manifest(str(path))


def test_invalid_json_is_a_manifest_error(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json")
    with pytest.raises(manifest.ManifestError, match="Cannot parse"):
        manifest.read_manifest(str(path))


@pytest.mark.parametrize(
    "document, message",
    [
        ([], "must be a mapping"),
        ({"name": "x"}, "'asset' or an 'assets'"),
        ({"assets": {"a": 1}}, "must be a list"),
        ({"asset": "x"}, "no representations"),
        ({"asset": "x", "representations": "a.ma"}, "list or mapping"),
        ({"asset": "x", "representations": [{"name": "p", "path": "a.obj"}]}, "Cannot infer"),
        ({"asset": "x", "representations": {"p": 3}}, "Bad representation"),
        ({"asset": "x", "default": "q", "representations": {"p": "a.ma"}}, "not defined"),
    ],
)
def test_malformed_documents(document, message):
    with pytest.raises(manifest.ManifestError, match=message):
        manifest.parse_manifest(document)


def test_duplicate_assets_rejected():
    entry = {"asset": "x", "representations": {"p": "a.ma"}}
    with pytest.raises(manifest.ManifestError, match="defined twice"):
        manifest.parse_manifest({"assets": [entry, entry]})


def test_relative_paths_kept_without_base_dir():
    (asset,) = manifest.parse_manifest({"asset": "x", "representations": {"p": "geo/a.ma"}})
    assert asset.get("p").file_path == os.path.normpath("geo/a.ma")
