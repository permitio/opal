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

# Keys added by the scopes git-resilience / leak series. Deliberately explicit:
# a new key belongs in the public reference AND in this list.
_TRACKED_KEYS = (
    "SCOPES_GIT_FETCH_TIMEOUT",
    "SCOPES_GIT_MAX_WORKERS",
    "SCOPES_GIT_MAX_ZOMBIES",
    "SCOPES_GIT_PRELOAD_DRAIN_TIMEOUT",
    "SCOPES_ORPHAN_SWEEP_INTERVAL",
    "SCOPES_ORPHAN_SWEEP_RECLAIM_ON_EMPTY_STORE",
    "SCOPES_ORPHAN_SWEEP_MAX_RECLAIM_FRACTION",
    "SCOPES_PURGE_CHANNEL",
)

_CONFIG_PY = Path(server_config_module.__file__)
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


@pytest.mark.parametrize("key", _TRACKED_KEYS)
def test_scopes_key_description_is_verbatim_in_the_public_reference(key):
    if not _MDX.exists():
        # Absence is only legitimate outside a checkout (an installed package
        # has no documentation/ tree). Inside one, a moved or renamed docs file
        # must FAIL: skipping would turn this whole guard into a green no-op
        # exactly when someone reorganises the docs — the likeliest way for the
        # drift to come back.
        if (_CONFIG_PY.parents[3] / "documentation").is_dir():
            pytest.fail(
                f"{_MDX} is missing from this checkout — the docs file moved or "
                f"was renamed, so this drift guard is no longer guarding "
                f"anything. Update _MDX."
            )
        pytest.skip("documentation/ tree not present (installed package)")

    description = _declared_description(_CONFIG_PY.read_text(), key)
    # Slice to this key's own section: asserting the heading and the description
    # exist independently anywhere in the file passes even when the text sits
    # under a different key's heading and this key's body is a paraphrase.
    section = _section_for(_MDX.read_text(), key)

    assert _normalize(description) in _normalize(section), (
        f"OPAL_{key}'s description in {_MDX.name} is a paraphrase, not the "
        f"config.py text. Copy it verbatim:\n\n{description}"
    )
    default = getattr(opal_server_config, key)
    assert f"Default: `{default}`" in section, (
        f"OPAL_{key}'s documented default does not match config.py "
        f"(expected 'Default: `{default}`')"
    )
