"""Tests for rep_switch.planner."""

import pytest

from rep_switch import planner
from rep_switch.test import conftest


def _states(*loaded):
    return [
        planner.AssetState(
            "|node{0}".format(index), conftest.make_asset("asset{0}".format(index)), rep
        )
        for index, rep in enumerate(loaded)
    ]


def _always(_path):
    return True


def test_switch_from_nothing_only_loads():
    states = _states("")
    plan = planner.plan_switch(states, {"|node0": "render"}, _always)
    assert [(a.kind, a.representation.name) for a in plan.actions] == [("load", "render")]
    assert plan.switched_nodes == ("|node0",)


def test_unloads_come_before_loads():
    states = _states("proxy", "proxy")
    plan = planner.plan_switch_all(states, "render", _always)
    assert [a.kind for a in plan.actions] == ["unload", "unload", "load", "load"]
    assert plan.summary() == {"load": 2, "unload": 2, "unchanged": 0, "skipped": 0}


def test_already_loaded_is_unchanged():
    states = _states("render", "proxy")
    plan = planner.plan_switch_all(states, "render", _always)
    assert plan.unchanged == ("|node0",)
    assert plan.switched_nodes == ("|node1",)


def test_nodes_without_target_are_ignored():
    states = _states("proxy", "proxy")
    plan = planner.plan_switch(states, {"|node1": "render"}, _always)
    assert {a.node for a in plan.actions} == {"|node1"}


def test_unknown_token_is_skipped():
    plan = planner.plan_switch(_states("proxy"), {"|node0": "hero"}, _always)
    assert plan.is_empty
    assert "no representation 'hero'" in plan.skipped["|node0"]


def test_missing_file_is_skipped():
    plan = planner.plan_switch(_states("proxy"), {"|node0": "render"}, lambda path: False)
    assert plan.is_empty
    assert plan.skipped["|node0"].startswith("missing file")


def test_undefined_loaded_representation_is_skipped():
    plan = planner.plan_switch(_states("legacy"), {"|node0": "render"}, _always)
    assert plan.is_empty
    assert "'legacy' is not defined" in plan.skipped["|node0"]


def test_unknown_node_raises():
    with pytest.raises(planner.PlanError, match="No asset state"):
        planner.plan_switch(_states(""), {"|ghost": "proxy"}, _always)


def test_inverse_restores_previous_state():
    states = _states("proxy", "")
    plan = planner.plan_switch_all(states, "render", _always)
    inverse = plan.inverse()
    assert [(a.kind, a.node, a.representation.name) for a in inverse.actions] == [
        ("unload", "|node1", "render"),
        ("unload", "|node0", "render"),
        ("load", "|node0", "proxy"),
    ]
    assert inverse.inverse() == planner.SwitchPlan(plan.actions, plan.unchanged)


def test_plan_for_context_resolves_each_asset():
    states = _states("", "render")
    missing_proxy = states[0].asset.get("proxy").file_path

    plan = planner.plan_for_context(states, "layout", file_exists=lambda p: p != missing_proxy)

    loads = {a.node: a.representation.name for a in plan.loads}
    assert loads == {"|node0": "stage", "|node1": "proxy"}
    assert [a.node for a in plan.unloads] == ["|node1"]


def test_plan_for_context_skips_unresolvable():
    plan = planner.plan_for_context(_states(""), "farm", file_exists=lambda p: False)
    assert plan.is_empty
    assert "context 'farm'" in plan.skipped["|node0"]
