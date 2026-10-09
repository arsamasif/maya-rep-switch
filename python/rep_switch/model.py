"""Representation data model.

An ``Asset`` owns an ordered set of ``Representation`` entries, each one a
file of a given type (alembic, usd, gpuCache or mayaRef). The classes are
frozen dataclasses so plans and resolutions can hold them safely.

"""

import dataclasses
import os
import re

from rep_switch import constants

_INVALID_NAME_CHARS = re.compile(r"[^A-Za-z0-9_]")


@dataclasses.dataclass(frozen=True)
class Representation:
    """One loadable version of an asset, for example a proxy or a render rep.

    Attributes:
        name (str): Unique name within the asset, e.g. ``"proxy"``.
        rep_type (str): One of ``constants.REP_TYPES``.
        file_path (str): Path of the file that backs the representation.

    """

    name: str
    rep_type: str
    file_path: str

    def __post_init__(self):
        if not self.name:
            raise ValueError("Representation needs a name")
        if self.rep_type not in constants.REP_TYPES:
            raise ValueError(
                "Unknown representation type '{0}' for '{1}', expected one of {2}".format(
                    self.rep_type, self.name, ", ".join(constants.REP_TYPES)
                )
            )
        if not self.file_path:
            raise ValueError("Representation '{0}' has no file path".format(self.name))
        # Normalize so the same file compares equal however it was spelled,
        # e.g. "/show/a.ma" from code and "\show\a.ma" read back on Windows.
        object.__setattr__(self, "file_path", os.path.normpath(self.file_path))

    def matches(self, token):
        """Tell if a rule token selects this representation.

        Args:
            token (str): Representation name or type.

        Returns:
            bool: True when the token equals the name or the type.

        """
        return token in (self.name, self.rep_type)

    def to_dict(self):
        """Serialize to a plain dict, the inverse of ``from_dict``.

        Returns:
            dict: Keys ``name``, ``type`` and ``path``.

        """
        return {"name": self.name, "type": self.rep_type, "path": self.file_path}

    @classmethod
    def from_dict(cls, data):
        """Build a representation from a manifest style dict.

        Args:
            data (dict): Keys ``name``, ``path`` and optionally ``type``. When
                ``type`` is missing it is inferred from the file extension.

        Returns:
            Representation: The new representation.

        Raises:
            ValueError: If a required key is missing or the type is unknown.

        """
        path = data.get("path") or ""
        rep_type = data.get("type") or infer_type(path)
        return cls(name=data.get("name") or "", rep_type=rep_type, file_path=path)


@dataclasses.dataclass(frozen=True)
class Asset:
    """An asset and every representation it can be switched to.

    Attributes:
        name (str): Asset name, e.g. ``"treeA"``.
        representations (tuple): ``Representation`` entries in declared order.
        default (str): Name of the representation to use when no rule
            applies. Empty means "first declared".

    """

    name: str
    representations: tuple = ()
    default: str = ""

    def __post_init__(self):
        if not self.name:
            raise ValueError("Asset needs a name")
        object.__setattr__(self, "representations", tuple(self.representations))
        names = [rep.name for rep in self.representations]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(
                "Asset '{0}' has duplicate representations: {1}".format(
                    self.name, ", ".join(duplicates)
                )
            )
        if self.default and self.default not in names:
            raise ValueError(
                "Default representation '{0}' is not defined on asset '{1}'".format(
                    self.default, self.name
                )
            )

    @property
    def names(self):
        """tuple: Representation names in declared order."""
        return tuple(rep.name for rep in self.representations)

    def get(self, name):
        """Return the representation with the given name.

        Args:
            name (str): Representation name.

        Returns:
            Representation: The matching representation.

        Raises:
            KeyError: If the asset has no such representation.

        """
        for rep in self.representations:
            if rep.name == name:
                return rep
        raise KeyError("Asset '{0}' has no representation '{1}'".format(self.name, name))

    def find(self, token):
        """Return every representation a token selects, names before types.

        Args:
            token (str): Representation name or type.

        Returns:
            list: Matching ``Representation`` objects, best match first.

        """
        by_name = [rep for rep in self.representations if rep.name == token]
        by_type = [
            rep for rep in self.representations if rep.rep_type == token and rep not in by_name
        ]
        return by_name + by_type

    def default_representation(self):
        """Return the default representation, or None for an empty asset.

        Returns:
            Representation: The explicit default, else the first declared one.

        """
        if self.default:
            return self.get(self.default)
        return self.representations[0] if self.representations else None

    def to_dict(self):
        """Serialize to a plain dict suitable for a manifest.

        Returns:
            dict: Keys ``asset``, ``default`` (when set) and ``representations``.

        """
        data = {"asset": self.name}
        if self.default:
            data["default"] = self.default
        data["representations"] = [rep.to_dict() for rep in self.representations]
        return data


def infer_type(file_path):
    """Guess the representation type from a file extension.

    ``.abc`` maps to alembic; a gpuCache must be declared explicitly because it
    shares the extension.

    Args:
        file_path (str): Path to inspect.

    Returns:
        str: The inferred type.

    Raises:
        ValueError: If the extension is not recognized.

    """
    extension = os.path.splitext(file_path)[1].lower()
    try:
        return constants.EXTENSION_TYPES[extension]
    except KeyError:
        raise ValueError(
            "Cannot infer representation type from '{0}', set 'type' explicitly".format(
                file_path
            )
        ) from None


def namespace_for(asset_name, rep_name):
    """Build a Maya-safe namespace for an asset representation.

    Args:
        asset_name (str): Asset name.
        rep_name (str): Representation name.

    Returns:
        str: Namespace made of letters, digits and underscores only.

    """
    namespace = _INVALID_NAME_CHARS.sub("_", "{0}_{1}".format(asset_name, rep_name))
    if namespace[0].isdigit():
        namespace = "_" + namespace
    return namespace
