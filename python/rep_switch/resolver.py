"""Pick a representation per asset for a working context.

Rules map a context ("layout", "farm", ...) to an ordered list of tokens.
A token matches a representation by name or by type. The resolver walks the
tokens, skips representations whose file is missing, then falls back to the
asset default and finally to any representation that exists on disk.

"""

import dataclasses
import json
import os

from rep_switch import constants

RULE = "rule"
DEFAULT = "default"
FALLBACK = "fallback"
UNRESOLVED = "unresolved"


class ResolveError(ValueError):
    """Raised for an unknown context or malformed rules."""


@dataclasses.dataclass(frozen=True)
class Resolution:
    """Outcome of resolving one asset.

    Attributes:
        asset (str): Asset name.
        representation (model.Representation): Chosen representation, or None.
        reason (str): ``RULE``, ``DEFAULT``, ``FALLBACK`` or ``UNRESOLVED``.
        skipped (tuple): ``(representation name, why)`` pairs that were
            considered and rejected.

    """

    asset: str
    representation: object
    reason: str
    skipped: tuple = ()

    @property
    def ok(self):
        """bool: True when a representation was chosen."""
        return self.representation is not None


def resolve(asset, context, rules=None, file_exists=os.path.isfile):
    """Choose the representation of an asset for a context.

    Args:
        asset (model.Asset): Asset to resolve.
        context (str): Context name, a key of ``rules``.
        rules (dict): Context to token list. Defaults to
            ``constants.DEFAULT_RULES``.
        file_exists (callable): Predicate on a file path, injectable for
            tests and for asset systems that are not plain files.

    Returns:
        Resolution: Always returned; check ``ok`` for success.

    Raises:
        ResolveError: If the context has no rule.

    """
    skipped = []
    tried = set()

    def _first_available(candidates):
        for rep in candidates:
            if rep.name in tried:
                continue
            tried.add(rep.name)
            if file_exists(rep.file_path):
                return rep
            skipped.append((rep.name, "missing file {0}".format(rep.file_path)))
        return None

    for token in preferences_for(context, rules):
        chosen = _first_available(asset.find(token))
        if chosen:
            return Resolution(asset.name, chosen, RULE, tuple(skipped))
    default = asset.default_representation()
    chosen = _first_available([default] if default else [])
    if chosen:
        return Resolution(asset.name, chosen, DEFAULT, tuple(skipped))
    chosen = _first_available(asset.representations)
    if chosen:
        return Resolution(asset.name, chosen, FALLBACK, tuple(skipped))
    return Resolution(asset.name, None, UNRESOLVED, tuple(skipped))


def resolve_all(assets, context, rules=None, file_exists=os.path.isfile):
    """Resolve several assets for the same context.

    Args:
        assets (list): ``model.Asset`` objects.
        context (str): Context name.
        rules (dict): Optional rules, see ``resolve``.
        file_exists (callable): Optional file predicate, see ``resolve``.

    Returns:
        list: One ``Resolution`` per asset, in input order.

    """
    return [resolve(asset, context, rules, file_exists) for asset in assets]


def preferences_for(context, rules=None):
    """Return the ordered tokens for a context.

    Args:
        context (str): Context name.
        rules (dict): Optional rules, defaults to ``constants.DEFAULT_RULES``.

    Returns:
        tuple: Tokens in order of preference.

    Raises:
        ResolveError: If the context has no rule.

    """
    rules = constants.DEFAULT_RULES if rules is None else rules
    try:
        return tuple(rules[context])
    except KeyError:
        raise ResolveError(
            "No rule for context '{0}', known contexts: {1}".format(
                context, ", ".join(sorted(rules))
            )
        ) from None


def detect_context(environ=None, batch=False):
    """Work out the current context.

    The ``REP_SWITCH_CONTEXT`` environment variable wins. Otherwise batch
    sessions (render farm, mayapy) use ``farm`` and interactive ones use
    ``layout``.

    Args:
        environ (dict): Environment to read, defaults to ``os.environ``.
        batch (bool): True when running without a UI.

    Returns:
        str: Context name.

    """
    environ = os.environ if environ is None else environ
    explicit = environ.get(constants.CONTEXT_ENV, "").strip()
    if explicit:
        return explicit
    return constants.BATCH_CONTEXT if batch else constants.DEFAULT_CONTEXT


def rules_from_environ(environ=None):
    """Return the studio rules file named by ``REP_SWITCH_RULES``, else the defaults.

    Args:
        environ (dict): Environment to read, defaults to ``os.environ``.

    Returns:
        dict: Context name to tuple of tokens.

    """
    environ = os.environ if environ is None else environ
    path = environ.get(constants.RULES_ENV, "").strip()
    return load_rules(path) if path else dict(constants.DEFAULT_RULES)


def load_rules(path):
    """Load context rules from a JSON or YAML file.

    The file maps context names to token lists, e.g.
    ``{"layout": ["proxy", "gpuCache"], "farm": ["render"]}``.

    Args:
        path (str): Rules file path.

    Returns:
        dict: Context name to tuple of tokens.

    Raises:
        FileNotFoundError: If the file does not exist.
        ResolveError: If the rules are malformed.

    """
    if not os.path.isfile(path):
        raise FileNotFoundError("Missing rules file: {0}".format(path))
    with open(path, encoding="utf-8") as handle:
        if path.lower().endswith((".yaml", ".yml")):
            import yaml

            data = yaml.safe_load(handle)
        else:
            data = json.load(handle)
    return validate_rules(data)


def validate_rules(data):
    """Check a rules mapping and normalize its values to tuples.

    Args:
        data (dict): Context name to list of tokens.

    Returns:
        dict: Context name to tuple of tokens.

    Raises:
        ResolveError: If the mapping or any token list is malformed.

    """
    if not isinstance(data, dict) or not data:
        raise ResolveError("Rules must be a non-empty mapping of context to tokens")
    rules = {}
    for context, tokens in data.items():
        if not isinstance(tokens, (list, tuple)) or not tokens:
            raise ResolveError("Rule '{0}' must be a non-empty list".format(context))
        if not all(isinstance(token, str) and token for token in tokens):
            raise ResolveError("Rule '{0}' must only hold strings".format(context))
        rules[context] = tuple(tokens)
    return rules
