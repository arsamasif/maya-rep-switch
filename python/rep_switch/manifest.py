"""Read and write asset manifests.

A manifest is a JSON or YAML document that describes one asset, or a list of
assets, and their representations. Relative file paths resolve against the
manifest's folder and environment variables are expanded, so a manifest can
live next to the published files it points at.

Accepted shapes::

    asset: treeA
    default: proxy
    representations:
      proxy:  {type: gpuCache, path: treeA_proxy.abc}
      render: {path: treeA_render.ma}

    assets:
      - asset: treeA
        representations:
          - {name: proxy, type: gpuCache, path: treeA_proxy.abc}

"""

import json
import os

from rep_switch import model

JSON_EXTENSIONS = (".json",)
YAML_EXTENSIONS = (".yaml", ".yml")


class ManifestError(ValueError):
    """Raised when a manifest cannot be read or is malformed."""


def read_manifest(path):
    """Read every asset described by a manifest file.

    Args:
        path (str): Path to a ``.json``, ``.yaml`` or ``.yml`` manifest.

    Returns:
        list: ``model.Asset`` objects in file order.

    Raises:
        FileNotFoundError: If the manifest does not exist.
        ManifestError: If the document is malformed.

    """
    if not os.path.isfile(path):
        raise FileNotFoundError("Missing manifest: {0}".format(path))
    data = _load_document(path)
    return parse_manifest(data, base_dir=os.path.dirname(os.path.abspath(path)))


def parse_manifest(data, base_dir=""):
    """Turn an already loaded manifest document into assets.

    Args:
        data (dict): Parsed JSON or YAML document.
        base_dir (str): Folder that relative file paths resolve against.
            Empty keeps relative paths as they are.

    Returns:
        list: ``model.Asset`` objects.

    Raises:
        ManifestError: If the document is malformed.

    """
    if not isinstance(data, dict):
        raise ManifestError("Manifest must be a mapping, got {0}".format(type(data).__name__))
    if "assets" in data:
        entries = data["assets"]
        if not isinstance(entries, list):
            raise ManifestError("'assets' must be a list")
    elif "asset" in data:
        entries = [data]
    else:
        raise ManifestError("Manifest needs an 'asset' or an 'assets' key")
    assets = [_parse_asset(entry, base_dir) for entry in entries]
    _check_unique_assets(assets)
    return assets


def write_manifest(path, assets):
    """Write assets to a manifest file, choosing the format by extension.

    Args:
        path (str): Destination ``.json``, ``.yaml`` or ``.yml`` path.
        assets (list): ``model.Asset`` objects.

    Raises:
        ManifestError: If the extension is not supported.

    """
    document = {"assets": [asset.to_dict() for asset in assets]}
    extension = os.path.splitext(path)[1].lower()
    if extension in JSON_EXTENSIONS:
        text = json.dumps(document, indent=2) + "\n"
    elif extension in YAML_EXTENSIONS:
        text = _yaml_module().safe_dump(document, sort_keys=False)
    else:
        raise ManifestError("Unsupported manifest extension: {0}".format(path))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def _load_document(path):
    extension = os.path.splitext(path)[1].lower()
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    try:
        if extension in JSON_EXTENSIONS:
            return json.loads(text)
        if extension in YAML_EXTENSIONS:
            return _yaml_module().safe_load(text)
    except ValueError as error:
        raise ManifestError("Cannot parse {0}: {1}".format(path, error)) from error
    raise ManifestError("Unsupported manifest extension: {0}".format(path))


def _yaml_module():
    try:
        import yaml
    except ImportError as error:
        raise ManifestError("PyYAML is required for YAML manifests") from error
    return yaml


def _parse_asset(entry, base_dir):
    if not isinstance(entry, dict):
        raise ManifestError("Asset entry must be a mapping: {0!r}".format(entry))
    name = entry.get("asset")
    if not name:
        raise ManifestError("Asset entry has no 'asset' name: {0!r}".format(entry))
    reps = [_parse_representation(item, base_dir, name) for item in _rep_entries(entry, name)]
    try:
        return model.Asset(name=name, representations=reps, default=entry.get("default") or "")
    except ValueError as error:
        raise ManifestError(str(error)) from error


def _rep_entries(entry, asset_name):
    raw = entry.get("representations")
    if not raw:
        raise ManifestError("Asset '{0}' has no representations".format(asset_name))
    if isinstance(raw, dict):
        return [_named_entry(name, value, asset_name) for name, value in raw.items()]
    if isinstance(raw, list):
        return raw
    raise ManifestError("Representations of '{0}' must be a list or mapping".format(asset_name))


def _named_entry(name, value, asset_name):
    if isinstance(value, str):
        return {"name": name, "path": value}
    if isinstance(value, dict):
        return dict(value, name=name)
    raise ManifestError("Bad representation '{0}' on asset '{1}'".format(name, asset_name))


def _parse_representation(item, base_dir, asset_name):
    if not isinstance(item, dict):
        raise ManifestError("Bad representation entry on '{0}': {1!r}".format(asset_name, item))
    data = dict(item)
    if data.get("path"):
        data["path"] = _resolve_path(data["path"], base_dir)
    try:
        return model.Representation.from_dict(data)
    except ValueError as error:
        raise ManifestError("Asset '{0}': {1}".format(asset_name, error)) from error


def _resolve_path(path, base_dir):
    expanded = os.path.expanduser(os.path.expandvars(path))
    if base_dir and not _is_rooted(expanded):
        expanded = os.path.join(base_dir, expanded)
    return os.path.normpath(expanded)


def _is_rooted(path):
    # Python 3.13 no longer treats "/show/x" as absolute on Windows because it
    # has no drive. A leading separator still means "not relative" here.
    return os.path.isabs(path) or path.startswith(("/", "\\"))


def _check_unique_assets(assets):
    seen = set()
    for asset in assets:
        if asset.name in seen:
            raise ManifestError("Asset '{0}' is defined twice".format(asset.name))
        seen.add(asset.name)
