"""Shared pytest fixtures for the core tests.

Builds small assets and a fake file system predicate so resolver and planner
tests do not touch the disk.

Also creates the Qt application before any test starts Maya: under
``mayapy``, ``maya.standalone`` would otherwise create a ``QCoreApplication``
and the panel test could not build widgets.

"""

import importlib.util
import os

import pytest

from rep_switch import constants
from rep_switch import model

if importlib.util.find_spec("PySide6") or importlib.util.find_spec("PySide2"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6 import QtWidgets
    except ImportError:
        from PySide2 import QtWidgets
    QT_APP = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def make_asset(name="treeA", default=""):
    """Build a three representation asset used across tests.

    Args:
        name (str): Asset name.
        default (str): Default representation name.

    Returns:
        model.Asset: Asset with proxy (gpuCache), render (mayaRef) and
        layout (usd) representations.

    """
    reps = (
        model.Representation("proxy", constants.GPU_CACHE, "/show/{0}/proxy.abc".format(name)),
        model.Representation("render", constants.MAYA_REF, "/show/{0}/render.ma".format(name)),
        model.Representation("stage", constants.USD, "/show/{0}/stage.usd".format(name)),
    )
    return model.Asset(name=name, representations=reps, default=default)


@pytest.fixture
def asset():
    """model.Asset: The standard three representation asset."""
    return make_asset()


@pytest.fixture
def exists_except():
    """Return a factory for file predicates that report given paths missing."""

    def _factory(*missing):
        missing_set = set(missing)
        return lambda path: path not in missing_set

    return _factory
