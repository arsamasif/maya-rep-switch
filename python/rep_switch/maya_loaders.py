"""Load and unload representations under a repAsset node.

One loader per representation type:

- mayaRef: file reference, grouped and parented under the node.
- alembic: file reference through the Alembic translator, same layout.
- gpuCache: a ``gpuCache`` shape parented directly under the node.
- usd: a ``mayaUsdProxyShape`` parented directly under the node.

Every loader returns the nodes it created; the caller connects them to the
node's ``loadedContent`` array, which is all ``unload`` needs to clean up.

"""

import os

from maya import cmds

from rep_switch import constants
from rep_switch import maya_scene
from rep_switch import model

REQUIRED_PLUGINS = {
    constants.ALEMBIC: "AbcImport",
    constants.GPU_CACHE: "gpuCache",
    constants.USD: "mayaUsdPlugin",
}
REFERENCE_FILE_TYPES = {".ma": "mayaAscii", ".mb": "mayaBinary", ".abc": "Alembic"}


def load(node, asset_name, rep):
    """Load a representation under a repAsset node.

    Args:
        node (str): repAsset node.
        asset_name (str): Asset name, used for namespaces and node names.
        rep (model.Representation): Representation to load.

    Returns:
        list: Names of the nodes created, already connected to the node.

    Raises:
        FileNotFoundError: If the representation file does not exist.

    """
    if not os.path.isfile(rep.file_path):
        raise FileNotFoundError("Missing representation file: {0}".format(rep.file_path))
    plugin = REQUIRED_PLUGINS.get(rep.rep_type)
    if plugin:
        _ensure_plugin(plugin)
    loader = _LOADERS[rep.rep_type]
    created = loader(node, asset_name, rep)
    maya_scene.connect_content(node, created)
    return created


def unload(node):
    """Remove everything the loaded representation created.

    References are removed first so their group nodes are empty when they
    get deleted.

    Args:
        node (str): repAsset node.

    """
    content = maya_scene.content_nodes(node)
    references = [name for name in content if cmds.nodeType(name) == "reference"]
    for reference in references:
        cmds.file(referenceNode=reference, removeReference=True)
    leftovers = [name for name in content if name not in references and cmds.objExists(name)]
    if leftovers:
        cmds.delete(leftovers)


def _load_reference(node, asset_name, rep):
    # The group is our own node, not one made by ``file -groupReference``.
    # Maya treats that group as part of the reference, and removing the
    # reference after the group was parented under the repAsset node also
    # deleted the repAsset node.
    namespace = model.namespace_for(asset_name, rep.name)
    group = cmds.group(empty=True, name=_unique_name(namespace + "_grp"), parent=node)
    extension = os.path.splitext(rep.file_path)[1].lower()
    file_type = REFERENCE_FILE_TYPES.get(extension, "mayaAscii")
    if rep.rep_type == constants.ALEMBIC:
        file_type = "Alembic"
    new_nodes = cmds.file(
        rep.file_path,
        reference=True,
        type=file_type,
        namespace=namespace,
        returnNewNodes=True,
    )
    references = cmds.ls(new_nodes, type="reference")
    if not references:
        cmds.delete(group)
        raise RuntimeError("Referencing created no reference node: {0}".format(rep.file_path))
    top_nodes = cmds.ls(new_nodes, assemblies=True, long=True)
    if top_nodes:
        cmds.parent(top_nodes, group)
    return [references[0], group]


def _load_gpu_cache(node, asset_name, rep):
    transform, shape = _create_shape("gpuCache", node, asset_name, rep)
    cmds.setAttr(shape + ".cacheFileName", rep.file_path, type="string")
    return [transform]


def _load_usd(node, asset_name, rep):
    transform, shape = _create_shape("mayaUsdProxyShape", node, asset_name, rep)
    cmds.setAttr(shape + ".filePath", rep.file_path, type="string")
    cmds.connectAttr("time1.outTime", shape + ".time", force=True)
    return [transform]


def _create_shape(node_type, node, asset_name, rep):
    # The shape gets its own transform under the repAsset node. A shape
    # parented straight under the node would take the node with it when it
    # is deleted on unload, because Maya removes a transform whose only
    # shape is deleted.
    base = model.namespace_for(asset_name, rep.name)
    transform = cmds.createNode("transform", name=_unique_name(base), parent=node)
    shape = cmds.createNode(node_type, name=_unique_name(base + "Shape"), parent=transform)
    return transform, shape


def _unique_name(base):
    name = base
    counter = 1
    while cmds.objExists(name):
        name = "{0}{1}".format(base, counter)
        counter += 1
    return name


def _ensure_plugin(name):
    if not cmds.pluginInfo(name, query=True, loaded=True):
        cmds.loadPlugin(name, quiet=True)


_LOADERS = {
    constants.MAYA_REF: _load_reference,
    constants.ALEMBIC: _load_reference,
    constants.GPU_CACHE: _load_gpu_cache,
    constants.USD: _load_usd,
}
