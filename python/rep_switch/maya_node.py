"""The ``repAsset`` transform node (Maya Python API 1.0).

A transform that stores an asset's representations and parents whatever the
active one loads: a grouped reference, a gpuCache shape or a USD proxy shape.
The node does no work in ``compute``; switching is a side effect and lives in
the ``repSwitch`` command. Editing ``activeRepresentation`` by hand (Attribute
Editor, setAttr) schedules that command through a deferred callback.

API 1.0 is used because ``MPxTransform`` is not exposed in the Python API
2.0, and a plug-in has to use one API for all of its nodes and commands.

"""

import functools

from maya import OpenMaya
from maya import OpenMayaMPx
from maya import cmds

from rep_switch import constants

_CALLBACK_IDS = []


class RepAssetMatrix(OpenMayaMPx.MPxTransformationMatrix):
    """Plain transformation matrix; registered because MPxTransform needs one."""

    kTypeId = OpenMaya.MTypeId(constants.MATRIX_ID)

    @classmethod
    def creator(cls):
        """Return a new matrix instance for Maya."""
        return OpenMayaMPx.asMPxPtr(cls())


class RepAssetNode(OpenMayaMPx.MPxTransform):
    """Transform node holding switchable asset representations."""

    kTypeName = constants.NODE_TYPE
    kTypeId = OpenMaya.MTypeId(constants.NODE_ID)

    asset_name = OpenMaya.MObject()
    representations = OpenMaya.MObject()
    rep_name = OpenMaya.MObject()
    rep_type = OpenMaya.MObject()
    rep_file = OpenMaya.MObject()
    default_representation = OpenMaya.MObject()
    active_representation = OpenMaya.MObject()
    loaded_representation = OpenMaya.MObject()
    status = OpenMaya.MObject()
    loaded_content = OpenMaya.MObject()

    def __init__(self):
        OpenMayaMPx.MPxTransform.__init__(self)

    @classmethod
    def creator(cls):
        """Return a new node instance for Maya."""
        return OpenMayaMPx.asMPxPtr(cls())

    def postConstructor(self):
        """Watch ``activeRepresentation`` so manual edits trigger a switch."""
        callback_id = OpenMaya.MNodeMessage.addAttributeChangedCallback(
            self.thisMObject(), _on_attribute_changed
        )
        _CALLBACK_IDS.append(callback_id)

    @classmethod
    def initialize(cls):
        """Create and add the node attributes."""
        typed = OpenMaya.MFnTypedAttribute()
        enum = OpenMaya.MFnEnumAttribute()

        cls.asset_name = _string_attribute(typed, "assetName", "an")
        cls.rep_name = _string_attribute(typed, "repName", "rpn")
        cls.rep_file = _string_attribute(typed, "repFile", "rpf")
        typed.setUsedAsFilename(True)
        # Short names must not clash with transform attributes such as
        # rotatePivotTranslate (rpt) and displayRotatePivot (drp).
        cls.rep_type = _enum_attribute(enum, "repType", "rty", constants.REP_TYPES)
        cls.representations = _representations_attribute(
            cls.rep_name, cls.rep_type, cls.rep_file
        )
        cls.default_representation = _string_attribute(typed, "defaultRepresentation", "dfr")
        cls.active_representation = _string_attribute(typed, "activeRepresentation", "arp")
        cls.loaded_representation = _string_attribute(typed, "loadedRepresentation", "lrp")
        typed.setHidden(True)
        cls.status = _enum_attribute(enum, "status", "sts", constants.STATUS_VALUES)
        cls.loaded_content = _content_attribute()

        for attribute in (
            cls.asset_name,
            cls.representations,
            cls.default_representation,
            cls.active_representation,
            cls.loaded_representation,
            cls.status,
            cls.loaded_content,
        ):
            cls.addAttribute(attribute)


def remove_callbacks():
    """Remove every callback added by repAsset nodes; called on plug-in unload."""
    for callback_id in _CALLBACK_IDS:
        OpenMaya.MMessage.removeCallback(callback_id)
    del _CALLBACK_IDS[:]


def _string_attribute(fn, long_name, short_name):
    attribute = fn.create(long_name, short_name, OpenMaya.MFnData.kString)
    fn.setStorable(True)
    fn.setKeyable(False)
    return attribute


def _enum_attribute(fn, long_name, short_name, fields):
    attribute = fn.create(long_name, short_name, 0)
    for index, field in enumerate(fields):
        fn.addField(field, index)
    fn.setStorable(True)
    fn.setKeyable(False)
    return attribute


def _representations_attribute(*children):
    fn = OpenMaya.MFnCompoundAttribute()
    attribute = fn.create("representations", "reps")
    for child in children:
        fn.addChild(child)
    fn.setArray(True)
    fn.setStorable(True)
    return attribute


def _content_attribute():
    fn = OpenMaya.MFnMessageAttribute()
    attribute = fn.create("loadedContent", "lc")
    fn.setArray(True)
    # connectAttr -nextAvailable needs indexMatters off, and Maya only
    # honours that on a multi that is not readable.
    fn.setReadable(False)
    fn.setIndexMatters(False)
    fn.setHidden(True)
    return attribute


def _on_attribute_changed(message, plug, other_plug, client_data):
    if not message & OpenMaya.MNodeMessage.kAttributeSet:
        return
    if plug.attribute() != RepAssetNode.active_representation:
        return
    if OpenMaya.MFileIO.isReadingFile() or OpenMaya.MFileIO.isOpeningFile():
        return
    uuid = OpenMaya.MFnDependencyNode(plug.node()).uuid().asString()
    cmds.evalDeferred(functools.partial(_sync_node, uuid))


def _sync_node(uuid):
    nodes = cmds.ls(uuid, long=True)
    if not nodes:
        return
    node = nodes[0]
    active = cmds.getAttr(node + ".activeRepresentation") or ""
    loaded = cmds.getAttr(node + ".loadedRepresentation") or ""
    if active and active != loaded:
        try:
            cmds.repSwitch(asset=[node], representation=active)
        except RuntimeError as error:
            OpenMaya.MGlobal.displayError("repAsset {0}: {1}".format(node, error))
