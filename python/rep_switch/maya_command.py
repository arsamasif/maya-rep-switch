"""The ``repSwitch`` command (Maya Python API 1.0, like the node).

Usage from Python::

    cmds.repSwitch(asset=["treeA_rep"], representation="render")
    cmds.repSwitch(all=True, representation="proxy")
    cmds.repSwitch(all=True, context="farm")
    cmds.repSwitch(all=True)    # context from $REP_SWITCH_CONTEXT, else layout/farm
    cmds.repSwitch(asset=["treeA_rep"], query=True)   # -> ["render"]

Without ``-asset`` or ``-all`` the command works on the selected repAsset
nodes. A switch builds a ``planner.SwitchPlan`` up front, so ``undoIt``
simply runs the inverse plan and ``redoIt`` runs the plan again.

"""

from maya import OpenMaya
from maya import OpenMayaMPx

from rep_switch import constants
from rep_switch import maya_scene
from rep_switch import maya_switch
from rep_switch import planner
from rep_switch import resolver

ASSET_FLAG = ("-a", "-asset")
REPRESENTATION_FLAG = ("-r", "-representation")
CONTEXT_FLAG = ("-ctx", "-context")
ALL_FLAG = ("-all", "-allAssets")


class RepSwitchCommand(OpenMayaMPx.MPxCommand):
    """Switch, or query, the representation of repAsset nodes."""

    kName = constants.COMMAND_NAME

    def __init__(self):
        OpenMayaMPx.MPxCommand.__init__(self)
        self._plan = None

    @classmethod
    def creator(cls):
        """Return a new command instance for Maya."""
        return OpenMayaMPx.asMPxPtr(cls())

    @staticmethod
    def create_syntax():
        """Build the command syntax.

        Returns:
            OpenMaya.MSyntax: Syntax with the asset, representation, context and
            all flags, query enabled.

        """
        syntax = OpenMaya.MSyntax()
        syntax.addFlag(ASSET_FLAG[0], ASSET_FLAG[1], OpenMaya.MSyntax.kString)
        syntax.makeFlagMultiUse(ASSET_FLAG[0])
        # Keep the -asset value in query mode, e.g. repSwitch -q -asset treeA.
        syntax.makeFlagQueryWithFullArgs(ASSET_FLAG[0], False)
        syntax.addFlag(REPRESENTATION_FLAG[0], REPRESENTATION_FLAG[1], OpenMaya.MSyntax.kString)
        syntax.addFlag(CONTEXT_FLAG[0], CONTEXT_FLAG[1], OpenMaya.MSyntax.kString)
        syntax.addFlag(ALL_FLAG[0], ALL_FLAG[1], OpenMaya.MSyntax.kNoArg)
        syntax.enableQuery(True)
        return syntax

    def isUndoable(self):
        """Only switches that changed something go on the undo queue."""
        return self._plan is not None and not self._plan.is_empty

    def doIt(self, args):
        """Parse the arguments, build the plan and run it."""
        database = OpenMaya.MArgDatabase(self.syntax(), args)
        use_all = database.isFlagSet(ALL_FLAG[0])
        nodes = self._target_nodes(database, use_all)
        if database.isQuery():
            self._query(nodes)
            return
        self._plan = self._build_plan(database, nodes, use_all)
        self.redoIt()

    def redoIt(self):
        """Run the plan and return the switched nodes as the result."""
        switched = maya_switch.execute(self._plan)
        # Flag assets whose files are missing, so the panel shows them in red
        # instead of a plain "unloaded".
        for node, reason in self._plan.skipped.items():
            if reason.startswith("missing file") and not maya_scene.read_state(node).loaded:
                maya_scene.set_status(node, constants.MISSING)
        self.clearResult()
        for node in switched:
            self.appendToResult(node)

    def undoIt(self):
        """Restore the previous representations by running the inverse plan."""
        maya_switch.execute(self._plan.inverse())

    def _target_nodes(self, database, use_all):
        if use_all:
            return maya_scene.list_nodes()
        tokens = _multi_use_strings(database, ASSET_FLAG[0])
        if not tokens:
            nodes = maya_scene.selected_nodes()
            if not nodes:
                raise RuntimeError("Select repAsset nodes or pass -asset / -all")
            return nodes
        nodes = []
        for token in tokens:
            found = maya_scene.find_nodes(token)
            if not found:
                raise RuntimeError("No repAsset node or asset named '{0}'".format(token))
            nodes.extend(node for node in found if node not in nodes)
        return nodes

    def _query(self, nodes):
        self.clearResult()
        for node in nodes:
            self.appendToResult(maya_scene.get_active(node))

    def _build_plan(self, database, nodes, use_all):
        states = maya_switch.states(nodes)
        if database.isFlagSet(REPRESENTATION_FLAG[0]):
            token = database.flagArgumentString(REPRESENTATION_FLAG[0], 0)
            plan = planner.plan_switch_all(states, token)
        else:
            # No -representation: use -context, else $REP_SWITCH_CONTEXT, else
            # "farm" in batch mode and "layout" in the UI.
            if database.isFlagSet(CONTEXT_FLAG[0]):
                context = database.flagArgumentString(CONTEXT_FLAG[0], 0)
            else:
                batch = OpenMaya.MGlobal.mayaState() != OpenMaya.MGlobal.kInteractive
                context = resolver.detect_context(batch=batch)
            try:
                rules = resolver.rules_from_environ()
                plan = planner.plan_for_context(states, context, rules)
            except resolver.ResolveError as error:
                raise RuntimeError(str(error)) from error
        _report_skipped(plan, strict=not use_all)
        return plan


def _report_skipped(plan, strict):
    if not plan.skipped:
        return
    lines = ["{0}: {1}".format(node, reason) for node, reason in sorted(plan.skipped.items())]
    if strict:
        raise RuntimeError("Cannot switch " + "; ".join(lines))
    for line in lines:
        OpenMaya.MGlobal.displayWarning("repSwitch skipped " + line)


def _multi_use_strings(database, flag):
    values = []
    for index in range(database.numberOfFlagUses(flag)):
        arg_list = OpenMaya.MArgList()
        database.getFlagArgumentList(flag, index, arg_list)
        values.append(arg_list.asString(0))
    return values