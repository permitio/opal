"""Public config reference must quote config.py verbatim for the scopes keys
this series added.

OPAL_SCOPES_GIT_FETCH_TIMEOUT's description has now drifted twice
(commit adade574 existed solely to re-sync it, and the round-2 fix
commit re-broke it with three rewordings). Operators read the public
config reference, so a paraphrase there is a doc bug that no reviewer
should have to catch by hand a third time.
"""
import re
from pathlib import Path

import pytest
from opal_server import config as server_config_module
from opal_server.config import opal_server_config

_CONFIG_PY_PATH = Path(server_config_module.__file__)


def _tracked_keys(_source_unused=None):
    """Every SCOPES_* key the running config actually exposes.

    Derived, not hand-listed: the version before that carried a comment stating
    the invariant ("a new key belongs in the public reference AND in this list")
    with nothing enforcing it, so a new key was unguarded by omission.

    Derived from the LIVE OBJECT, not the source text. The previous derivation
    regex-matched `\n    SCOPES_\w+ = confi\.`, which demands exactly four
    spaces of indent and exactly one space around `=`. Two ordinary declaration
    styles fell outside it —

        SCOPES_SNEAKY_KNOB: str = confi.str(...)   # type annotation
        SCOPES_SNEAKY_KNOB  = confi.str(...)       # stray second space

    — and a key written either way is fully live at runtime yet invisible to
    this guard, escaping BOTH directions at once: the forward test never
    requires it in the .mdx, and the reverse test cannot flag it because an
    undocumented key is not in the .mdx to be found. That is the same
    unguarded-by-omission failure, moved from the list level to the formatting
    level. dir() cannot be fooled by formatting.
    """
    return tuple(sorted(k for k in dir(opal_server_config) if k.startswith("SCOPES_")))


_CONFIG_PY = _CONFIG_PY_PATH
_MDX = (
    _CONFIG_PY.parents[3]
    / "documentation"
    / "docs"
    / "getting-started"
    / "configuration.mdx"
)


def _normalize(text: str) -> str:
    """Collapse whitespace: config.py wraps its descriptions across source
    lines, the .mdx keeps each on one line."""
    return " ".join(text.split())


def _declared_description(source: str, key: str) -> str:
    decl = re.search(
        r"\n    %s = confi\.\w+\(\n(.*?)\n    \)\n" % re.escape(key), source, re.S
    )
    assert decl, f"{key} is not declared in {_CONFIG_PY.name}"
    described = re.search(r"description=(.*)$", decl.group(1), re.S)
    assert described, f"{key} has no description= in {_CONFIG_PY.name}"
    # Concatenate the implicitly-joined string literals that make up the value.
    literals = re.findall(r'"((?:[^"\\]|\\.)*)"', described.group(1))
    assert literals, f"could not parse {key}'s description literals"
    return _normalize("".join(literals).replace('\\"', '"'))


def _declared_default(source: str, key: str) -> str:
    """The default literal as written in config.py, rendered the way the docs
    write it."""
    decl = re.search(
        r"\n    %s = confi\.(\w+)\(\n\s*\"%s\",\n(.*?)\n    \)\n"
        % (re.escape(key), re.escape(key)),
        source,
        re.S,
    )
    assert decl, f"{key} is not declared in {_CONFIG_PY.name}"
    body = decl.group(2)
    # first non-comment line after the name is the default
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("description="):
            continue
        literal = line.rstrip(",")
        # The docs render the VALUE, not the Python literal: a str default is
        # written `Default: \`__opal_scope_purge__\``, not with its quotes.
        if len(literal) >= 2 and literal[0] == literal[-1] and literal[0] in "\"'":
            literal = literal[1:-1]
        return literal
    raise AssertionError(f"could not find {key}'s default literal")


def _section_for(mdx: str, key: str) -> str:
    """The `#### OPAL_<key>` section only, so a description found under some
    OTHER key's heading cannot satisfy this key's assertion."""
    # Anchored with the trailing newline: `#### OPAL_FOO` is a prefix of
    # `#### OPAL_FOO_BAR`, so an unanchored find() would happily hand back a
    # DIFFERENT key's section (and a renamed heading would still "exist").
    heading = f"#### OPAL_{key}\n"
    start = mdx.find(heading)
    assert start != -1, f"OPAL_{key} has no `{heading}` section in {_MDX.name}"
    nxt = mdx.find("\n#### ", start + 1)
    return mdx[start : nxt if nxt != -1 else len(mdx)]


_TRACKED_KEYS = _tracked_keys()


def test_the_guard_derives_at_least_one_key():
    """A guard that derives its own parameters can silently stop guarding: an
    empty list feeds @parametrize an empty set and pytest reports `1 skipped —
    got empty parameter set`, not a failure. Renaming the Confi handle inside
    the class (`confi.` -> `_confi.`) or moving the SCOPES_* keys to their own
    module both do it, and config.py still imports and every key still resolves.

    A test rather than a module-level assert: an assert at import time raises
    during COLLECTION, and pytest aborts the entire run on a collection error —
    so one drifted regex would hide every other test's result. This fails loudly
    and locally instead.
    """
    assert _TRACKED_KEYS, (
        f"no SCOPES_* keys derived from {_CONFIG_PY_PATH.name} — this drift "
        f"guard is no longer guarding anything. Did the keys move, or the Confi "
        f"handle get renamed? Update _tracked_keys()."
    )


def _require_mdx():
    """Fail (not skip) when the public reference is missing from a checkout."""
    if _MDX.exists():
        return
    # Absence is only legitimate outside a checkout. "Am I in a checkout" is
    # answered by something that CANNOT move with the docs — asking the docs
    # tree itself (the previous version) meant relocating `documentation/`
    # wholesale, e.g. a docusaurus reorg to `website/docs/`, silently skipped
    # every key instead of failing.
    repo_root = _CONFIG_PY.parents[3]
    in_checkout = (repo_root / ".git").exists() or (
        repo_root / "packages" / "opal-server" / "setup.py"
    ).exists()
    if in_checkout:
        pytest.fail(
            f"{_MDX} is missing from this checkout — the public config "
            f"reference moved or was renamed, so this drift guard is no "
            f"longer guarding anything. Update _MDX to its new location."
        )
    pytest.skip("not a source checkout (installed package)")


@pytest.mark.parametrize("key", _TRACKED_KEYS)
def test_scopes_key_description_is_verbatim_in_the_public_reference(key):
    _require_mdx()

    description = _declared_description(_CONFIG_PY.read_text(), key)
    # Slice to this key's own section: asserting the heading and the description
    # exist independently anywhere in the file passes even when the text sits
    # under a different key's heading and this key's body is a paraphrase.
    section = _section_for(_MDX.read_text(), key)

    # A single heading per key: a SECOND `#### OPAL_<key>` section with a
    # contradicting default renders on the page, but _section_for uses find()
    # so first-match-wins hides it, and the reverse test only flags keys
    # config.py does not declare.
    assert _MDX.read_text().count(f"#### OPAL_{key}\n") == 1, (
        f"OPAL_{key} has more than one `#### ` section in {_MDX.name}; the "
        f"later one renders but this guard only ever reads the first"
    )
    assert _normalize(description) in _normalize(section), (
        f"OPAL_{key}'s description in {_MDX.name} is a paraphrase, not the "
        f"config.py text. Copy it verbatim:\n\n{description}"
    )
    # The DECLARED literal, not getattr(opal_server_config, key): the latter is
    # the effective value after Confi has consulted OPAL_<KEY>, so exporting one
    # (this repo's own bed does) reddened a test about doc-vs-source drift with a
    # doc-vs-environment mismatch, pointing the reader at an .mdx that was right.
    declared = _declared_default(_CONFIG_PY.read_text(), key)
    assert f"Default: `{declared}`" in section, (
        f"OPAL_{key}'s documented default does not match the literal declared in "
        f"{_CONFIG_PY.name} (expected 'Default: `{declared}`')"
    )


def test_no_documented_scopes_key_is_undeclared():
    """The reverse direction: a `#### OPAL_SCOPES_*` section for a key config.py
    no longer declares.

    The parametrized guard above only walks config.py -> .mdx, so a doc entry
    left behind by a removed key is invisible to it — the operator reads a knob
    that does nothing. This PR deletes keys from both files, which is exactly
    when that matters.
    """
    _require_mdx()

    documented = set(re.findall(r"^#### OPAL_(SCOPES_\w+)$", _MDX.read_text(), re.M))
    stale = documented - set(_TRACKED_KEYS)
    assert not stale, (
        f"{_MDX.name} documents OPAL_SCOPES_* keys that {_CONFIG_PY.name} does "
        f"not declare (setting them does nothing): {sorted(stale)}"
    )
