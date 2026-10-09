"""Read and write repAsset nodes with maya.cmds.

Converts between the attributes on a ``repAsset`` node and the core
``model.Asset`` / ``planner.AssetState`` objects, and tracks the nodes a
loaded representation created through the ``loadedContent`` message array.

"""

import os

from maya import cmds

from rep_switch import constants
from rep_switch import model
from rep_switch import panel_model
from rep_switch import planner

REPS_ATTR = "representations"
CONTENT_ATTR = "loadedContent"


def list_nodes():
    """Return every repAsset node in the scene.

    Returns:
        list: Long DAG paths.

    """
    return cmds.ls(type=constants.NODE_TYPE, long=True) or []


def selected_nodes():
    """Return selected repAsset nodes, including parents of selected children.

    Returns:
        list: Long DAG paths without duplicates, in selection order.

    """
    found = []
    for path in cmds.ls(selection=True, long=True) or []:
        candidates = [path] + (cmds.listRelatives(path, allParents=True, fullPath=True) or [])
        for candidate in candidates:
            if cmds.nodeType(candidate) == constants.NODE_TYPE and candidate not in found:
                found.append(candidate)
                break
    return found


def find_nodes(token):
    """Find repAsset nodes by node name or by asset name.

    Args:
        token (str): A node name/path, or the value of ``assetName``.

    Returns:
        list: Long DAG paths, empty when nothing matches.

    """
    if cmds.objExists(token) and cmds.nodeType(token) == constants.NODE_TYPE:
        return cmds.ls(token, long=True)
    return [node for node in list_nodes() if _get_string(node, "assetName") == token]


def create_node(asset, name=None, parent=None):
    """Create a repAsset node holding an asset definition.

    Args:
        asset (model.Asset): Asset to store on the node.
        name (str): Optional node name, defaults to ``<asset>_rep``.
        parent (str): Optional parent transform.

    Returns:
        str: Long path of the new node.

    """
    kwargs = {"name": name or "{0}_rep".format(asset.name)}
    if parent:
        kwargs["parent"] = parent
    node = cmds.ls(cmds.createNode(constants.NODE_TYPE, **kwargs), long=True)[0]
    write_asset(node, asset)
    return node


def write_asset(node, asset):
    """Replace the asset definition stored on a node.

    Args:
        node (str): repAsset node.
        asset (model.Asset): Asset to store.

    """
    _set_string(node, "assetName", asset.name)
    _set_string(node, "defaultRepresentation", asset.default)
    for index in cmds.getAttr("{0}.{1}".format(node, REPS_ATTR), multiIndices=True) or []:
        cmds.removeMultiInstance("{0}.{1}[{2}]".format(node, REPS_ATTR, index), b=True)
    for index, rep in enumerate(asset.representations):
        plug = "{0}.{1}[{2}]".format(node, REPS_ATTR, index)
        cmds.setAttr(plug + ".repName", rep.name, type="string")
        cmds.setAttr(plug + ".repType", constants.REP_TYPES.index(rep.rep_type))
        cmds.setAttr(plug + ".repFile", rep.file_path, type="string")


def read_asset(node):
    """Read the asset definition stored on a node.

    Args:
        node (str): repAsset node.

    Returns:
        model.Asset: The asset.

    Raises:
        ValueError: If the stored data is incomplete.

    """
    reps = []
    for index in cmds.getAttr("{0}.{1}".format(node, REPS_ATTR), multiIndices=True) or []:
        plug = "{0}.{1}[{2}]".format(node, REPS_ATTR, index)
        reps.append(
            model.Representation(
                name=cmds.getAttr(plug + ".repName") or "",
                rep_type=constants.REP_TYPES[cmds.getAttr(plug + ".repType")],
                file_path=cmds.getAttr(plug + ".repFile") or "",
            )
        )
    name = _get_string(node, "assetName") or node.rsplit("|", 1)[-1]
    default = _get_string(node, "defaultRepresentation")
    return model.Asset(name=name, representations=reps, default=default)


def read_state(node):
    """Snapshot a node for the planner.

    Args:
        node (str): repAsset node.

    Returns:
        planner.AssetState: Node, asset and loaded representation.

    """
    return planner.AssetState(
        node=node, asset=read_asset(node), loaded=_get_string(node, "loadedRepresentation")
    )


def get_status(node):
    """Return the status string of a node.

    Args:
        node (str): repAsset node.

    Returns:
        str: One of ``constants.STATUS_VALUES``.

    """
    return constants.STATUS_VALUES[cmds.getAttr(node + ".status")]


def set_status(node, status):
    """Set the status of a node.

    Args:
        node (str): repAsset node.
        status (str): One of ``constants.STATUS_VALUES``.

    """
    cmds.setAttr(node + ".status", constants.STATUS_VALUES.index(status))
    update_outliner_color(node)


def update_outliner_color(node):
    """Color the node's name in the Outliner by what is loaded.

    Args:
        node (str): repAsset node.

    Returns:
        tuple: The RGB color that was set, or None for the default color.

    """
    color = panel_model.outliner_color_for(get_status(node), _loaded_type(node))
    cmds.setAttr(node + ".useOutlinerColor", color is not None)
    if color is not None:
        cmds.setAttr(node + ".outlinerColor", *color)
    return color


def icon_name(node):
    """Return the icon file for a node's status and loaded type.

    Used by the panel and the Attribute Editor. (The Outliner only shows one
    icon per node type, ``out_repAsset.png``, whatever the state.)

    Args:
        node (str): repAsset node.

    Returns:
        str: Icon file name.

    """
    return panel_model.icon_for(get_status(node), _loaded_type(node))


def icon_path(node):
    """Return the full path of the node's state icon.

    Args:
        node (str): repAsset node.

    Returns:
        str: Path inside the repo's ``icons`` folder, with forward slashes.

    """
    return os.path.join(constants.ICON_DIR, icon_name(node)).replace("\\", "/")


def get_active(node):
    """Return the representation the node is asked to show.

    Args:
        node (str): repAsset node.

    Returns:
        str: ``activeRepresentation`` value, empty when unset.

    """
    return _get_string(node, "activeRepresentation")


def mark_loaded(node, rep_name):
    """Record that a representation is loaded, or that nothing is.

    Sets ``loadedRepresentation`` first so the node's attribute callback sees
    active and loaded agree and does not schedule another switch.

    Args:
        node (str): repAsset node.
        rep_name (str): Loaded representation name, empty for none.

    """
    _set_string(node, "loadedRepresentation", rep_name)
    _set_string(node, "activeRepresentation", rep_name)
    set_status(node, constants.LOADED if rep_name else constants.UNLOADED)


def content_nodes(node):
    """Return the nodes created by the loaded representation.

    Args:
        node (str): repAsset node.

    Returns:
        list: Node names connected to ``loadedContent``.

    """
    plug = "{0}.{1}".format(node, CONTENT_ATTR)
    return cmds.listConnections(plug, source=True, destination=False) or []


def connect_content(node, created):
    """Connect created nodes to ``loadedContent`` so they can be unloaded later.

    Args:
        node (str): repAsset node.
        created (list): Node names created by a loader.

    """
    for name in created:
        cmds.connectAttr(
            name + ".message", "{0}.{1}".format(node, CONTENT_ATTR), nextAvailable=True
        )


def _loaded_type(node):
    loaded = _get_string(node, "loadedRepresentation")
    if not loaded:
        return ""
    try:
        return read_asset(node).get(loaded).rep_type
    except (KeyError, ValueError):
        return ""


def _get_string(node, attr):
    return cmds.getAttr("{0}.{1}".format(node, attr)) or ""


def _set_string(node, attr, value):
    cmds.setAttr("{0}.{1}".format(node, attr), value or "", type="string")
