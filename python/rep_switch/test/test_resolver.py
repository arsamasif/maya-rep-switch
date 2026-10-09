"""Tests for rep_switch.resolver."""

import json

import pytest

from rep_switch import constants
from rep_switch import resolver
from rep_switch.test import conftest


def test_layout_prefers_proxy(asset, exists_except):
    resolution = resolver.resolve(asset, "layout", file_exists=exists_except())
    assert resolution.ok
    assert resolution.representation.name == "proxy"
    assert resolution.reason == resolver.RULE
    assert resolution.skipped == ()


def test_farm_prefers_render(asset, exists_except):
    resolution = resolver.resolve(asset, "farm", file_exists=exists_except())
    assert resolution.representation.name == "render"


def test_missing_file_falls_through_to_next_token(asset, exists_except):
    exists = exists_except(asset.get("proxy").file_path)
    resolution = resolver.resolve(asset, "layout", file_exists=exists)
    assert resolution.representation.name == "stage"
    assert resolution.reason == resolver.RULE
    assert resolution.skipped[0][0] == "proxy"
    assert "missing file" in resolution.skipped[0][1]


def test_type_token_matches_by_type(asset, exists_except):
    rules = {"review": (constants.USD,)}
    resolution = resolver.resolve(asset, "review", rules, exists_except())
    assert resolution.representation.name == "stage"


def test_default_used_when_no_rule_matches(exists_except):
    asset = conftest.make_asset(default="render")
    resolution = resolver.resolve(asset, "x", {"x": ("hero",)}, exists_except())
    assert resolution.representation.name == "render"
    assert resolution.reason == resolver.DEFAULT


def test_fallback_to_any_existing_file(asset, exists_except):
    exists = exists_except(asset.get("proxy").file_path, asset.get("render").file_path)
    resolution = resolver.resolve(asset, "x", {"x": ("render",)}, exists)
    assert resolution.representation.name == "stage"
    assert resolution.reason == resolver.FALLBACK
    assert [name for name, _ in resolution.skipped] == ["render", "proxy"]


def test_each_representation_checked_once(asset):
    calls = []

    def exists(path):
        calls.append(path)
        return False

    resolution = resolver.resolve(asset, "layout", file_exists=exists)
    assert not resolution.ok
    assert resolution.reason == resolver.UNRESOLVED
    assert len(calls) == len(set(calls)) == 3


def test_unknown_context(asset):
    with pytest.raises(resolver.ResolveError, match="known contexts"):
        resolver.resolve(asset, "comp")


def test_resolve_all_keeps_order(exists_except):
    assets = [conftest.make_asset("a"), conftest.make_asset("b")]
    resolutions = resolver.resolve_all(assets, "farm", file_exists=exists_except())
    assert [r.asset for r in resolutions] == ["a", "b"]


@pytest.mark.parametrize(
    "environ, batch, expected",
    [
        ({}, False, "layout"),
        ({}, True, "farm"),
        ({constants.CONTEXT_ENV: "lighting"}, True, "lighting"),
        ({constants.CONTEXT_ENV: "  "}, False, "layout"),
    ],
)
def test_detect_context(environ, batch, expected):
    assert resolver.detect_context(environ, batch) == expected


def test_load_rules_json(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text(json.dumps({"layout": ["proxy"], "farm": ["render", "usd"]}))
    assert resolver.load_rules(str(path)) == {"layout": ("proxy",), "farm": ("render", "usd")}


def test_load_rules_yaml(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("layout: [proxy, gpuCache]\n")
    assert resolver.load_rules(str(path)) == {"layout": ("proxy", "gpuCache")}


def test_load_rules_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        resolver.load_rules(str(tmp_path / "rules.json"))


@pytest.mark.parametrize(
    "data", [{}, [], {"layout": []}, {"layout": "proxy"}, {"layout": ["proxy", 3]}]
)
def test_validate_rules_rejects_bad_data(data):
    with pytest.raises(resolver.ResolveError):
        resolver.validate_rules(data)


def test_rules_from_environ(tmp_path):
    assert resolver.rules_from_environ({}) == constants.DEFAULT_RULES
    path = tmp_path / "rules.json"
    path.write_text(json.dumps({"review": ["render"]}))
    rules = resolver.rules_from_environ({constants.RULES_ENV: str(path)})
    assert rules == {"review": ("render",)}
