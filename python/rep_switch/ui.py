"""Qt panel that lists repAsset nodes and switches their representations.

The widget is a thin view over ``panel_model``: rows, button choices and
labels all come from there. Every switch goes through ``cmds.repSwitch`` so
it lands on Maya's undo queue. Works with PySide6 (Maya 2025+) and falls back
to PySide2 (Maya 2024).

Open it with::

    from rep_switch import ui
    ui.show()

"""

from maya import OpenMayaUI
from maya import cmds

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance

from rep_switch import manifest
from rep_switch import maya_scene
from rep_switch import maya_switch
from rep_switch import panel_model
from rep_switch import resolver

WINDOW_OBJECT_NAME = "repSwitchPanel"
COLUMNS = ("Asset", "Representation", "Status", "Node")

_PANEL = None


class RepSwitchPanel(QtWidgets.QWidget):
    """Table of repAsset nodes with per-row dropdowns and switch-all buttons."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName(WINDOW_OBJECT_NAME)
        self.setWindowTitle("Representation Switcher")
        self.setWindowFlags(QtCore.Qt.Window)
        self.resize(640, 380)

        self._table = QtWidgets.QTableWidget(0, len(COLUMNS))
        self._table.setHorizontalHeaderLabels(COLUMNS)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._table.itemSelectionChanged.connect(self._select_in_scene)

        self._button_row = QtWidgets.QHBoxLayout()
        self._context_combo = QtWidgets.QComboBox()
        self._context_combo.addItems(sorted(resolver.rules_from_environ()))
        resolve_button = QtWidgets.QPushButton("Resolve all")
        resolve_button.clicked.connect(self._resolve_context)
        refresh_button = QtWidgets.QPushButton("Refresh")
        refresh_button.clicked.connect(self.refresh)
        add_button = QtWidgets.QPushButton("Add from manifest...")
        add_button.clicked.connect(self._add_from_manifest)
        self._message = QtWidgets.QLabel()

        context_row = QtWidgets.QHBoxLayout()
        context_row.addWidget(QtWidgets.QLabel("Context:"))
        context_row.addWidget(self._context_combo)
        context_row.addWidget(resolve_button)
        context_row.addStretch()
        context_row.addWidget(add_button)
        context_row.addWidget(refresh_button)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self._table)
        layout.addLayout(self._button_row)
        layout.addLayout(context_row)
        layout.addWidget(self._message)
        self.refresh()

    def refresh(self):
        """Re-read the scene and rebuild the table and buttons."""
        nodes = maya_scene.list_nodes()
        statuses = {node: maya_scene.get_status(node) for node in nodes}
        rows = panel_model.build_rows(maya_switch.states(nodes), statuses)
        self._fill_table(rows)
        self._fill_buttons(rows)

    def _fill_table(self, rows):
        self._table.blockSignals(True)
        self._table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            asset_item = _item(row.asset, row.node)
            asset_item.setIcon(QtGui.QIcon(maya_scene.icon_path(row.node)))
            self._table.setItem(index, 0, asset_item)
            self._table.setCellWidget(index, 1, self._make_combo(row))
            status = _item(row.label, row.node)
            if row.needs_attention:
                status.setForeground(QtCore.Qt.red)
            self._table.setItem(index, 2, status)
            self._table.setItem(index, 3, _item(row.node.rsplit("|", 1)[-1], row.node))
        self._table.resizeColumnsToContents()
        self._table.blockSignals(False)

    def _make_combo(self, row):
        combo = QtWidgets.QComboBox()
        if not row.active:
            combo.addItem("")
        combo.addItems(list(row.choices))
        combo.setCurrentText(row.active)
        combo.currentTextChanged.connect(lambda text, node=row.node: self._switch([node], text))
        return combo

    def _fill_buttons(self, rows):
        while self._button_row.count():
            widget = self._button_row.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        self._button_row.addWidget(QtWidgets.QLabel("Switch all to:"))
        for choice in panel_model.switch_all_choices(rows):
            offering, active = panel_model.coverage(rows, choice)
            button = QtWidgets.QPushButton(choice)
            tooltip = "{0} of {1} assets offer it, {2} already use it"
            button.setToolTip(tooltip.format(offering, len(rows), active))
            button.clicked.connect(lambda checked=False, name=choice: self._switch_all(name))
            self._button_row.addWidget(button)
        self._button_row.addStretch()

    def _switch(self, nodes, choice):
        if not choice:
            return
        self._run(lambda: cmds.repSwitch(asset=nodes, representation=choice))

    def _switch_all(self, choice):
        self._run(lambda: cmds.repSwitch(all=True, representation=choice))

    def _resolve_context(self):
        context = self._context_combo.currentText()
        self._run(lambda: cmds.repSwitch(all=True, context=context))

    def _run(self, call):
        try:
            switched = call() or []
        except RuntimeError as error:
            self._message.setText(str(error))
        else:
            self._message.setText(f"Switched {len(switched)} asset(s)")
        # Rebuild after the signal returns: the combo that fired is replaced.
        QtCore.QTimer.singleShot(0, self.refresh)

    def _add_from_manifest(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Asset manifest", "", "Manifests (*.json *.yaml *.yml)"
        )
        if path:
            self.add_from_manifest(path)

    def add_from_manifest(self, path):
        """Create a repAsset node for every asset in a manifest file.

        Args:
            path (str): JSON or YAML manifest.

        Returns:
            list: The created nodes, empty if the file could not be read.

        """
        try:
            assets = manifest.read_manifest(path)
        except (OSError, manifest.ManifestError) as error:
            self._message.setText(str(error))
            return []
        nodes = [maya_scene.create_node(asset) for asset in assets]
        self._message.setText("Added {0} asset(s) from {1}".format(len(nodes), path.rsplit("/", 1)[-1]))
        self.refresh()
        return nodes

    def _select_in_scene(self):
        nodes = {item.data(QtCore.Qt.UserRole) for item in self._table.selectedItems()}
        if nodes:
            cmds.select(sorted(nodes), replace=True)


def show():
    """Open the panel, replacing an existing one.

    Returns:
        RepSwitchPanel: The panel widget.

    """
    global _PANEL
    if _PANEL is not None:
        _PANEL.close()
        _PANEL.deleteLater()
    _PANEL = RepSwitchPanel(parent=_maya_main_window())
    _PANEL.show()
    return _PANEL


def _maya_main_window():
    pointer = OpenMayaUI.MQtUtil.mainWindow()
    return wrapInstance(int(pointer), QtWidgets.QWidget) if pointer else None



def _item(text, node):
    item = QtWidgets.QTableWidgetItem(text)
    item.setData(QtCore.Qt.UserRole, node)
    item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
    return item
