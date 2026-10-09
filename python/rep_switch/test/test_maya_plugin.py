"""End-to-end tests for the plug-in, run with ``mayapy -m pytest``.

Loads the plug-in in a standalone session, writes two tiny Maya ASCII files,
switches a repAsset node between them and checks undo and redo. The whole
module is skipped when Maya is not importable.

"""

import os

import pytest

standalone = pytest.importorskip("maya.standalone")

from rep_switch import constants  # noqa: E402
from rep_switch import model  # noqa: E402

PLUGIN_PATH = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        os.pardir,
        os.pardir,
        os.pardir,
        "plug-ins",
        "rep_switch_plugin.py",
    )
)


@pytest.fixture(scope="module")
def cmds():
    """Start Maya, load the plug-in and return maya.cmds."""
    standalone.initialize(name="python")
    from maya import cmds as maya_cmds

    maya_cmds.loadPlugin(PLUGIN_PATH)
    yield maya_cmds
    maya_cmds.file(new=True, force=True)
    maya_cmds.unloadPlugin(os.path.basename(PLUGIN_PATH))


@pytest.fixture
def asset(cmds, tmp_path):
    """Write proxy and render scenes and return an asset pointing at them."""
    proxy = _write_scene(cmds, str(tmp_path / "crate_proxy.ma"), "polyCube", "proxyGeo")
    render = _write_scene(cmds, str(tmp_path / "crate_render.ma"), "polySphere", "renderGeo")
    cmds.file(new=True, force=True)
    cmds.undoInfo(state=True, infinity=True)
    return model.Asset(
        "crate",
        (
            model.Representation("proxy", constants.MAYA_REF, proxy),
            model.Representation("render", constants.MAYA_REF, render),
        ),
    )


@pytest.fixture
def node(cmds, asset):
    """Create a repAsset node for the asset."""
    from rep_switch import maya_scene

    return maya_scene.create_node(asset)


def _write_scene(cmds, path, creator, name):
    cmds.file(new=True, force=True)
    getattr(cmds, creator)(name=name)
    cmds.file(rename=path)
    cmds.file(save=True, type="mayaAscii", force=True)
    return path


def _loaded_geo(cmds, node):
    return sorted(
        path.rsplit(":", 1)[-1]
        for path in cmds.listRelatives(node, allDescendents=True, type="transform") or []
        if ":" in path
    )


def test_node_round_trips_asset(cmds, node, asset):
    from rep_switch import maya_scene

    assert cmds.nodeType(node) == constants.NODE_TYPE
    assert maya_scene.read_asset(node) == asset
    assert maya_scene.get_status(node) == constants.UNLOADED


def test_switch_between_references_with_undo(cmds, node):
    cmds.repSwitch(asset=[node], representation="proxy")
    assert _loaded_geo(cmds, node) == ["proxyGeo"]
    assert cmds.repSwitch(asset=[node], query=True) == ["proxy"]

    cmds.repSwitch(asset=[node], representation="render")
    assert _loaded_geo(cmds, node) == ["renderGeo"]
    assert len(cmds.file(query=True, reference=True)) == 1

    cmds.undo()
    assert _loaded_geo(cmds, node) == ["proxyGeo"]
    assert cmds.getAttr(node + ".loadedRepresentation") == "proxy"

    cmds.redo()
    assert _loaded_geo(cmds, node) == ["renderGeo"]
    assert cmds.getAttr(node + ".status") == constants.STATUS_VALUES.index(constants.LOADED)


def test_switch_all_and_context(cmds, node):
    cmds.repSwitch(all=True, representation="proxy")
    assert _loaded_geo(cmds, node) == ["proxyGeo"]
    cmds.repSwitch(all=True, context="farm")
    assert _loaded_geo(cmds, node) == ["renderGeo"]


def test_unknown_representation_fails_cleanly(cmds, node):
    with pytest.raises(RuntimeError):
        cmds.repSwitch(asset=[node], representation="hero")
    assert cmds.getAttr(node + ".loadedRepresentation") in (None, "")


@pytest.fixture
def all_types(cmds, tmp_path):
    """Write one file per representation type and return an asset using them."""
    for plugin in ("gpuCache", "AbcExport", "AbcImport", "mayaUsdPlugin"):
        try:
            cmds.loadPlugin(plugin, quiet=True)
        except RuntimeError:
            pytest.skip("Maya plug-in {0} is not available".format(plugin))
    folder = str(tmp_path).replace("\\", "/")
    render = _write_scene(cmds, folder + "/render.ma", "polySphere", "renderGeo")

    cmds.file(new=True, force=True)
    proxy = cmds.polyCube(name="proxyGeo")[0]
    cmds.gpuCache(proxy, startTime=1, endTime=1, directory=folder, fileName="proxy")

    cmds.file(new=True, force=True)
    anim = cmds.polyCube(name="animGeo")[0]
    cmds.setKeyframe(anim, attribute="translateY", time=1, value=0)
    cmds.setKeyframe(anim, attribute="translateY", time=5, value=2)
    cmds.AbcExport(j="-frameRange 1 5 -root |animGeo -file {0}/anim.abc".format(folder))

    cmds.file(new=True, force=True)
    cmds.select(cmds.polyCone(name="stageGeo")[0])
    cmds.mayaUSDExport(file=folder + "/stage.usda", selection=True)

    cmds.file(new=True, force=True)
    return model.Asset(
        "prop",
        (
            model.Representation("proxy", constants.GPU_CACHE, folder + "/proxy.abc"),
            model.Representation("anim", constants.ALEMBIC, folder + "/anim.abc"),
            model.Representation("render", constants.MAYA_REF, render),
            model.Representation("stage", constants.USD, folder + "/stage.usda"),
        ),
    )


def test_switch_through_every_representation_type(cmds, all_types):
    # Unloading a gpuCache or USD shape used to delete the repAsset node too,
    # because Maya removes a transform whose only shape is deleted.
    from rep_switch import maya_scene

    node = maya_scene.create_node(all_types)
    expected = {
        "proxy": "gpuCache",
        "anim": "transform",
        "render": "transform",
        "stage": "mayaUsdProxyShape",
    }
    for rep in ("proxy", "anim", "render", "stage", "proxy"):
        cmds.repSwitch(asset=[node], representation=rep)
        assert cmds.objExists(node)
        assert cmds.repSwitch(asset=[node], query=True) == [rep]
        assert maya_scene.get_status(node) == constants.LOADED
        types = {cmds.nodeType(child) for child in cmds.listRelatives(node, allDescendents=True) or []}
        assert expected[rep] in types
    cmds.undo()
    assert cmds.repSwitch(asset=[node], query=True) == ["stage"]


def test_context_comes_from_the_environment(cmds, node, monkeypatch):
    # proxy/render both are Maya references here; "anim" prefers proxy and
    # "farm" prefers render in the default rules.
    monkeypatch.setenv(constants.CONTEXT_ENV, "anim")
    cmds.repSwitch(asset=[node])
    assert cmds.repSwitch(asset=[node], query=True) == ["proxy"]
    monkeypatch.setenv(constants.CONTEXT_ENV, "farm")
    cmds.repSwitch(all=True)
    assert cmds.repSwitch(asset=[node], query=True) == ["render"]


def test_drop_installer_writes_module_and_loads_plugin(cmds, tmp_path, monkeypatch):
    import importlib.util

    from rep_switch import install

    repo = os.path.normpath(os.path.join(os.path.dirname(PLUGIN_PATH), os.pardir))
    modules = str(tmp_path / "modules")
    monkeypatch.setattr(install, "user_modules_dir", lambda: modules)
    spec = importlib.util.spec_from_file_location(
        "install_rep_switch", os.path.join(repo, "install_rep_switch.py")
    )
    dropped = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dropped)

    dropped.onMayaDroppedPythonFile()

    with open(os.path.join(modules, "rep_switch.mod"), encoding="utf-8") as handle:
        assert handle.read() == install.module_text(repo)
    assert cmds.pluginInfo(install.PLUGIN_FILE, query=True, loaded=True)
    assert install.add_shelf_button() is None


def test_panel_adds_assets_from_a_manifest(cmds, asset, tmp_path):
    pytest.importorskip("PySide6")
    from rep_switch import manifest
    from rep_switch import ui

    path = str(tmp_path / "crate.json")
    manifest.write_manifest(path, [asset])
    panel = ui.RepSwitchPanel()
    nodes = panel.add_from_manifest(path)
    assert len(nodes) == 1
    assert panel._table.rowCount() == 1
    assert panel._table.item(0, 0).text() == "crate"
    assert panel.add_from_manifest(str(tmp_path / "missing.json")) == []
    assert "Missing manifest" in panel._message.text()
    panel.close()


def test_assets_with_missing_files_are_flagged(cmds, tmp_path):
    from rep_switch import maya_scene

    cmds.file(new=True, force=True)
    ghost = model.Asset(
        "ghost", (model.Representation("proxy", constants.MAYA_REF, str(tmp_path / "gone.ma")),)
    )
    node = maya_scene.create_node(ghost)
    cmds.repSwitch(all=True, representation="proxy")
    assert maya_scene.get_status(node) == constants.MISSING


def test_state_icon_follows_the_representation(cmds, all_types):
    from rep_switch import maya_scene
    from rep_switch import maya_menu

    node = maya_scene.create_node(all_types)
    assert maya_scene.icon_name(node) == "out_repAsset.png"
    icons = {}
    for rep in ("proxy", "anim", "render", "stage"):
        cmds.repSwitch(asset=[node], representation=rep)
        icons[rep] = maya_scene.icon_name(node)
        assert os.path.isfile(maya_scene.icon_path(node))
        rep_type = all_types.get(rep).rep_type
        assert cmds.getAttr(node + ".useOutlinerColor")
        assert tuple(round(v, 2) for v in cmds.getAttr(node + ".outlinerColor")[0]) == (
            constants.OUTLINER_COLOR_BY_TYPE[rep_type]
        )
    assert icons == {
        "proxy": "repAsset_gpuCache.png",
        "anim": "repAsset_alembic.png",
        "render": "repAsset_mayaRef.png",
        "stage": "repAsset_usd.png",
    }
    cmds.undo()
    assert maya_scene.icon_name(node) == "repAsset_mayaRef.png"

    content = cmds.listRelatives(node, allDescendents=True, fullPath=True)[0]
    assert maya_menu.owning_node(content) == node
    assert maya_menu.owning_node(cmds.polyCube()[0]) == ""
