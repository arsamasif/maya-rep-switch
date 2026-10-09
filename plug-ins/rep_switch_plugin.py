"""Maya plug-in entry point for rep_switch.

Registers the ``repAsset`` transform node and the ``repSwitch`` command.
Load it with ``cmds.loadPlugin("rep_switch_plugin.py")`` once the plug-ins
folder is on ``MAYA_PLUG_IN_PATH`` and ``python`` is on ``PYTHONPATH`` (the
Rez package sets both). The plug-in uses the Python API 1.0 because
``MPxTransform`` only exists there.

"""

import os
import sys

from maya import OpenMayaMPx


def _python_root():
    """Return the repo's ``python`` folder next to ``plug-ins``.

    Maya runs Python plug-ins without setting ``__file__``, so the plug-in
    path comes from this function's code object instead.

    Returns:
        str: Absolute path of the ``python`` folder.

    """
    plugin_dir = os.path.dirname(os.path.abspath(_python_root.__code__.co_filename))
    return os.path.normpath(os.path.join(plugin_dir, os.pardir, "python"))


try:
    import rep_switch  # noqa: F401
except ImportError:
    sys.path.append(_python_root())

from rep_switch import __version__  # noqa: E402
from rep_switch import maya_command  # noqa: E402
from rep_switch import maya_menu  # noqa: E402
from rep_switch import maya_node  # noqa: E402

VENDOR = "Arsam Ali"


def initializePlugin(plugin_object):
    """Register the node, the command and the right-click menu items.

    Args:
        plugin_object (OpenMaya.MObject): Plug-in object passed in by Maya.

    """
    fn_plugin = OpenMayaMPx.MFnPlugin(plugin_object, VENDOR, __version__, "Any")
    node = maya_node.RepAssetNode
    matrix = maya_node.RepAssetMatrix
    fn_plugin.registerTransform(
        node.kTypeName,
        node.kTypeId,
        node.creator,
        node.initialize,
        matrix.creator,
        matrix.kTypeId,
    )
    command = maya_command.RepSwitchCommand
    fn_plugin.registerCommand(command.kName, command.creator, command.create_syntax)
    maya_menu.register()


def uninitializePlugin(plugin_object):
    """Deregister the command and the node and drop node callbacks.

    Args:
        plugin_object (OpenMaya.MObject): Plug-in object passed in by Maya.

    """
    fn_plugin = OpenMayaMPx.MFnPlugin(plugin_object)
    maya_menu.unregister()
    fn_plugin.deregisterCommand(maya_command.RepSwitchCommand.kName)
    maya_node.remove_callbacks()
    fn_plugin.deregisterNode(maya_node.RepAssetNode.kTypeId)
