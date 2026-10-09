"""Qt-free model behind the switcher panel.

Turns asset states into table rows and works out which "switch all to"
buttons to offer. The Qt widget in ``ui`` only renders what this module
returns, so all of the panel's decisions are covered by plain pytest.

"""

import collections
import dataclasses

from rep_switch import constants


@dataclasses.dataclass(frozen=True)
class Row:
    """One line of the switcher table.

    Attributes:
        node (str): Scene node name.
        asset (str): Asset name.
        choices (tuple): Representation names offered in the dropdown.
        active (str): Loaded representation name, empty when none.
        status (str): One of ``constants.STATUS_VALUES``.

    """

    node: str
    asset: str
    choices: tuple
    active: str
    status: str

    @property
    def label(self):
        """str: Short text for the status column."""
        if not self.active:
            return self.status
        return "{0} ({1})".format(self.active, self.status)

    @property
    def needs_attention(self):
        """bool: True when the status is missing or error."""
        return self.status in (constants.MISSING, constants.ERROR)


def build_rows(states, statuses=None):
    """Build table rows from asset states.

    Args:
        states (list): ``planner.AssetState`` snapshots.
        statuses (dict): Optional node name to status. Nodes without an entry
            are ``loaded`` when something is loaded, else ``unloaded``.

    Returns:
        list: ``Row`` objects sorted by asset then node name.

    """
    statuses = statuses or {}
    rows = []
    for state in states:
        fallback = constants.LOADED if state.loaded else constants.UNLOADED
        rows.append(
            Row(
                node=state.node,
                asset=state.asset.name,
                choices=state.asset.names,
                active=state.loaded,
                status=statuses.get(state.node, fallback),
            )
        )
    return sorted(rows, key=lambda row: (row.asset.lower(), row.node))


def switch_all_choices(rows, limit=4):
    """Pick the representation names worth a "switch all to" button.

    Names offered by more assets come first; ties keep first appearance.

    Args:
        rows (list): ``Row`` objects.
        limit (int): Maximum number of buttons.

    Returns:
        list: Representation names.

    """
    counts = collections.Counter()
    first_seen = {}
    for row in rows:
        for name in row.choices:
            counts[name] += 1
            first_seen.setdefault(name, len(first_seen))
    ordered = sorted(counts, key=lambda name: (-counts[name], first_seen[name]))
    return ordered[:limit]


def coverage(rows, choice):
    """Count how many rows offer a representation and how many already use it.

    Args:
        rows (list): ``Row`` objects.
        choice (str): Representation name.

    Returns:
        tuple: ``(offering, active)`` counts, handy for button tooltips.

    """
    offering = sum(1 for row in rows if choice in row.choices)
    active = sum(1 for row in rows if row.active == choice)
    return offering, active

def icon_for(status, rep_type=""):
    """Return the icon file for a node's status and loaded type.

    Args:
        status (str): One of ``constants.STATUS_VALUES``.
        rep_type (str): Type of the loaded representation, if any.

    Returns:
        str: Icon file name.

    """
    if status in (constants.MISSING, constants.ERROR):
        return constants.ICON_MISSING
    if status == constants.LOADED and rep_type in constants.ICON_BY_TYPE:
        return constants.ICON_BY_TYPE[rep_type]
    return constants.ICON_UNLOADED

def outliner_color_for(status, rep_type=""):
    """Return the Outliner text color for a node, or None for the default.

    Args:
        status (str): One of ``constants.STATUS_VALUES``.
        rep_type (str): Type of the loaded representation, if any.

    Returns:
        tuple: RGB floats, or None when nothing is loaded.

    """
    if status in (constants.MISSING, constants.ERROR):
        return constants.OUTLINER_COLOR_MISSING
    if status == constants.LOADED:
        return constants.OUTLINER_COLOR_BY_TYPE.get(rep_type)
    return None
