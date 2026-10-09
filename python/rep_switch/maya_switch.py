"""Execute switch plans in a Maya scene.

Runs the actions of a ``planner.SwitchPlan`` through the loaders and keeps
the node attributes (loaded/active representation, status) in sync. Maya's
own undo queue is suspended while a plan runs: the ``repSwitch`` command
undoes a switch by running the inverse plan instead.

"""

import contextlib
import os

from maya import cmds

from rep_switch import constants
from rep_switch import maya_loaders
from rep_switch import maya_scene
from rep_switch import planner


def execute(plan):
    """Run every action of a plan.

    A failing load marks the node ``error`` (or ``missing`` when the file is
    gone) and re-raises, leaving earlier actions applied.

    Args:
        plan (planner.SwitchPlan): Plan to run.

    Returns:
        list: Nodes that were switched to a new representation.

    """
    with undo_suspended():
        for action in plan.actions:
            if action.kind == planner.UNLOAD:
                maya_loaders.unload(action.node)
                maya_scene.mark_loaded(action.node, "")
            else:
                _load(action)
    return list(plan.switched_nodes)


def states(nodes=None):
    """Snapshot repAsset nodes for the planner.

    Args:
        nodes (list): Nodes to read, defaults to every repAsset in the scene.

    Returns:
        list: ``planner.AssetState`` objects.

    """
    nodes = maya_scene.list_nodes() if nodes is None else nodes
    return [maya_scene.read_state(node) for node in nodes]


def switch(nodes, token):
    """Switch nodes to a representation without going through the command.

    Prefer ``cmds.repSwitch`` in tools so the switch is undoable; this is for
    batch scripts where undo does not matter.

    Args:
        nodes (list): repAsset nodes.
        token (str): Representation name or type.

    Returns:
        planner.SwitchPlan: The plan that was executed.

    """
    plan = planner.plan_switch_all(states(nodes), token)
    execute(plan)
    return plan


@contextlib.contextmanager
def undo_suspended():
    """Stop recording undo without flushing the queue, restoring it after."""
    previous = cmds.undoInfo(query=True, stateWithoutFlush=True)
    cmds.undoInfo(stateWithoutFlush=False)
    try:
        yield
    finally:
        cmds.undoInfo(stateWithoutFlush=previous)


def _load(action):
    rep = action.representation
    try:
        maya_loaders.load(action.node, action.asset, rep)
    except Exception:
        failed = constants.ERROR if os.path.isfile(rep.file_path) else constants.MISSING
        maya_scene.set_status(action.node, failed)
        raise
    maya_scene.mark_loaded(action.node, rep.name)
