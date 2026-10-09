"""Compute what to load and unload when switching representations.

The planner works on ``AssetState`` snapshots (node name, asset, currently
loaded representation) and produces a ``SwitchPlan``: an ordered list of
unload and load actions plus the assets it skipped and why. All unloads come
before all loads so peak memory stays low when a whole scene switches.

Plans are invertible, which is how the ``repSwitch`` command implements undo.

"""

import dataclasses
import os

from rep_switch import resolver

LOAD = "load"
UNLOAD = "unload"


class PlanError(ValueError):
    """Raised when a plan cannot be built or inverted."""


@dataclasses.dataclass(frozen=True)
class AssetState:
    """Snapshot of one asset node in the scene.

    Attributes:
        node (str): Scene node name.
        asset (model.Asset): Asset definition stored on the node.
        loaded (str): Name of the loaded representation, empty when none.

    """

    node: str
    asset: object
    loaded: str = ""


@dataclasses.dataclass(frozen=True)
class Action:
    """A single load or unload step.

    Attributes:
        kind (str): ``LOAD`` or ``UNLOAD``.
        node (str): Scene node the action applies to.
        asset (str): Asset name, used for namespaces.
        representation (model.Representation): Representation loaded or
            unloaded.

    """

    kind: str
    node: str
    asset: str
    representation: object

    def inverse(self):
        """Return the action that undoes this one.

        Returns:
            Action: Same representation, opposite kind.

        """
        kind = UNLOAD if self.kind == LOAD else LOAD
        return dataclasses.replace(self, kind=kind)


@dataclasses.dataclass(frozen=True)
class SwitchPlan:
    """Ordered actions for a switch, plus what was left alone.

    Attributes:
        actions (tuple): ``Action`` objects, unloads first.
        unchanged (tuple): Nodes already on their target representation.
        skipped (dict): Node name to the reason it was not switched.

    """

    actions: tuple = ()
    unchanged: tuple = ()
    skipped: dict = dataclasses.field(default_factory=dict)

    @property
    def is_empty(self):
        """bool: True when the plan does nothing."""
        return not self.actions

    @property
    def loads(self):
        """tuple: Load actions in order."""
        return tuple(action for action in self.actions if action.kind == LOAD)

    @property
    def unloads(self):
        """tuple: Unload actions in order."""
        return tuple(action for action in self.actions if action.kind == UNLOAD)

    @property
    def switched_nodes(self):
        """tuple: Nodes that end up with a new representation, in order."""
        return tuple(action.node for action in self.loads)

    def inverse(self):
        """Return the plan that restores the state before this one ran.

        Returns:
            SwitchPlan: Inverted actions in reverse order.

        """
        actions = tuple(action.inverse() for action in reversed(self.actions))
        return SwitchPlan(actions=actions, unchanged=self.unchanged)

    def summary(self):
        """Count the plan's contents for logs and UI messages.

        Returns:
            dict: Keys ``load``, ``unload``, ``unchanged`` and ``skipped``.

        """
        return {
            LOAD: len(self.loads),
            UNLOAD: len(self.unloads),
            "unchanged": len(self.unchanged),
            "skipped": len(self.skipped),
        }


def plan_switch(states, targets, file_exists=os.path.isfile):
    """Plan switching nodes to explicit representations.

    Args:
        states (list): ``AssetState`` snapshots.
        targets (dict): Node name to token (representation name or type).
            Nodes not in ``targets`` are left alone.
        file_exists (callable): Predicate on a file path.

    Returns:
        SwitchPlan: The plan.

    Raises:
        PlanError: If a target names a node that has no state.

    """
    by_node = {state.node: state for state in states}
    unknown = sorted(set(targets) - set(by_node))
    if unknown:
        raise PlanError("No asset state for nodes: {0}".format(", ".join(unknown)))
    chosen = {}
    skipped = {}
    for state in states:
        if state.node not in targets:
            continue
        rep, reason = _pick(state.asset, targets[state.node], file_exists)
        if rep is None:
            skipped[state.node] = reason
        else:
            chosen[state.node] = rep
    return _build_plan(states, chosen, skipped)


def plan_switch_all(states, token, file_exists=os.path.isfile):
    """Plan switching every node that defines a token to that token.

    Nodes whose asset has no matching representation are skipped, which is
    what a "switch all to proxy" button wants.

    Args:
        states (list): ``AssetState`` snapshots.
        token (str): Representation name or type.
        file_exists (callable): Predicate on a file path.

    Returns:
        SwitchPlan: The plan.

    """
    targets = {state.node: token for state in states}
    return plan_switch(states, targets, file_exists)


def plan_for_context(states, context, rules=None, file_exists=os.path.isfile):
    """Plan switching every node to what the context rules resolve.

    Args:
        states (list): ``AssetState`` snapshots.
        context (str): Context name, e.g. ``"layout"`` or ``"farm"``.
        rules (dict): Optional rules, see ``resolver.resolve``.
        file_exists (callable): Predicate on a file path.

    Returns:
        SwitchPlan: The plan.

    Raises:
        resolver.ResolveError: If the context has no rule.

    """
    chosen = {}
    skipped = {}
    for state in states:
        resolution = resolver.resolve(state.asset, context, rules, file_exists)
        if resolution.ok:
            chosen[state.node] = resolution.representation
        else:
            skipped[state.node] = "no representation available for context '{0}'".format(
                context
            )
    return _build_plan(states, chosen, skipped)


def _pick(asset, token, file_exists):
    candidates = asset.find(token)
    if not candidates:
        return None, "asset '{0}' has no representation '{1}'".format(asset.name, token)
    for rep in candidates:
        if file_exists(rep.file_path):
            return rep, ""
    return None, "missing file {0}".format(candidates[0].file_path)


def _build_plan(states, chosen, skipped):
    unloads = []
    loads = []
    unchanged = []
    for state in states:
        target = chosen.get(state.node)
        if target is None:
            continue
        if target.name == state.loaded:
            unchanged.append(state.node)
            continue
        if state.loaded:
            previous = _loaded_representation(state)
            if previous is None:
                skipped[state.node] = "loaded representation '{0}' is not defined".format(
                    state.loaded
                )
                continue
            unloads.append(Action(UNLOAD, state.node, state.asset.name, previous))
        loads.append(Action(LOAD, state.node, state.asset.name, target))
    return SwitchPlan(actions=tuple(unloads + loads), unchanged=tuple(unchanged), skipped=skipped)


def _loaded_representation(state):
    try:
        return state.asset.get(state.loaded)
    except KeyError:
        return None
