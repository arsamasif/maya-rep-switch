"""Right-click menu in the viewport for switching representations.

Maya builds the object right-click menu in ``dagMenuProc`` and lets third
parties add items through the ``addRMBBakingMenuItems`` callback hook. The
plug-in registers ``add_menu_items`` there, so right-clicking anything that
belongs to a repAsset node adds a "Representation" submenu with the node's
representations. Picking one runs ``repSwitch``, so it is undoable.

"""

from maya import cmds

from rep_switch import constants
from rep_switch import maya_scene

HOOK = "addRMBBakingMenuItems"
OWNER = "rep_switch"


def register():
    """Add the right-click items to Maya's object menu."""
    cmds.callbacks(addCallback=add_menu_items, hook=HOOK, owner=OWNER)


def unregister():
    """Remove the right-click items again."""
    cmds.callbacks(clearCallbacks=True, hook=HOOK, owner=OWNER)


def owning_node(dag_object):
    """Return the repAsset node an object belongs to.

    Args:
        dag_object (str): Object under the cursor, e.g. a referenced mesh or
            a gpuCache shape below a repAsset node.

    Returns:
        str: Long name of the repAsset node, or "" when there is none.

    """
    if not dag_object or not cmds.objExists(dag_object):
        return ""
    path = cmds.ls(dag_object, long=True)[0]
    parts = path.split("|")
    for depth in range(len(parts), 1, -1):
        candidate = "|".join(parts[:depth])
        if cmds.nodeType(candidate) == constants.NODE_TYPE:
            return candidate
    return ""


def add_menu_items(dag_object):
    """Add the "Representation" submenu for the object's repAsset node.

    Called by Maya while it builds the right-click menu; the current menu
    parent is that menu.

    Args:
        dag_object (str): Object under the cursor.

    """
    node = owning_node(dag_object)
    if not node:
        return
    asset = maya_scene.read_asset(node)
    active = maya_scene.get_active(node)
    cmds.menuItem(divider=True)
    cmds.menuItem(label="Representation ({0})".format(asset.name), subMenu=True)
    cmds.radioMenuItemCollection()
    for rep in asset.representations:
        cmds.menuItem(
            label="{0}  [{1}]".format(rep.name, rep.rep_type),
            radioButton=rep.name == active,
            command=lambda *args, name=rep.name: _switch(node, name),
        )
    cmds.setParent("..", menu=True)


def _switch(node, rep_name):
    try:
        cmds.repSwitch(asset=[node], representation=rep_name)
    except RuntimeError as error:
        cmds.warning("repSwitch: {0}".format(error))
