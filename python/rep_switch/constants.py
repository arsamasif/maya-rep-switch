"""Shared constants for the rep_switch package.

Holds the representation types, status values, Maya node and command names
and the default context rules. Nothing in here imports Maya.

"""

import os

ALEMBIC = "alembic"
USD = "usd"
GPU_CACHE = "gpuCache"
MAYA_REF = "mayaRef"

# Order matters: the index is the enum value stored on the Maya node.
REP_TYPES = (ALEMBIC, USD, GPU_CACHE, MAYA_REF)

UNLOADED = "unloaded"
LOADED = "loaded"
MISSING = "missing"
ERROR = "error"

# Order matters: the index is the enum value stored on the Maya node.
STATUS_VALUES = (UNLOADED, LOADED, MISSING, ERROR)

NODE_TYPE = "repAsset"
COMMAND_NAME = "repSwitch"

# Ids from the 0x00000-0x7ffff block Autodesk reserves for local plug-ins.
# Register a real block before shipping the node outside one studio.
NODE_ID = 0x0007F3A0
MATRIX_ID = 0x0007F3A1

CONTEXT_ENV = "REP_SWITCH_CONTEXT"
RULES_ENV = "REP_SWITCH_RULES"
DEFAULT_CONTEXT = "layout"
BATCH_CONTEXT = "farm"

# Each context lists tokens in order of preference. A token matches a
# representation by name first, then by type.
DEFAULT_RULES = {
    "layout": ("proxy", GPU_CACHE, USD, "render"),
    "anim": ("proxy", GPU_CACHE, MAYA_REF),
    "lighting": ("render", USD, ALEMBIC),
    "farm": ("render", ALEMBIC, USD, MAYA_REF),
}

EXTENSION_TYPES = {
    ".ma": MAYA_REF,
    ".mb": MAYA_REF,
    ".abc": ALEMBIC,
    ".usd": USD,
    ".usda": USD,
    ".usdc": USD,
    ".usdz": USD,
}

# Icons live in the repo's icons/ folder. Maya's Outliner shows
# out_repAsset.png for the node type (the module file puts icons/ on
# XBMLANGPATH); the per-state icons are shown by the panel and the
# Attribute Editor.
ICON_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir, "icons"))
ICON_UNLOADED = "out_repAsset.png"
ICON_MISSING = "repAsset_missing.png"
ICON_BY_TYPE = {
    MAYA_REF: "repAsset_mayaRef.png",
    ALEMBIC: "repAsset_alembic.png",
    GPU_CACHE: "repAsset_gpuCache.png",
    USD: "repAsset_usd.png",
}

# Outliner text color per loaded type, matching the icon colors. The Outliner
# can't show a different icon per node, but it can color each node's name.
OUTLINER_COLOR_BY_TYPE = {
    MAYA_REF: (0.40, 0.62, 0.94),
    ALEMBIC: (0.93, 0.52, 0.32),
    GPU_CACHE: (0.20, 0.75, 0.52),
    USD: (0.60, 0.55, 0.95),
}
OUTLINER_COLOR_MISSING = (0.92, 0.40, 0.40)
