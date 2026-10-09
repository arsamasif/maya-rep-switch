# -*- coding: utf-8 -*-
name = "rep_switch"

version = "1.0.0"

authors = ["Arsam Ali"]

description = "Switchable asset representations (mayaRef, alembic, gpuCache, USD) for Maya."

requires = ["python-3", "pyyaml"]

tests = {
    "unit": {"command": "pytest {root}/python/rep_switch/test", "requires": ["pytest"]},
    "maya": {"command": "mayapy -m pytest {root}/python/rep_switch/test/test_maya_plugin.py"},
}


def commands():
    env.PYTHONPATH.append("{root}/python")
    env.MAYA_PLUG_IN_PATH.append("{root}/plug-ins")
    env.MAYA_SCRIPT_PATH.append("{root}/scripts")
