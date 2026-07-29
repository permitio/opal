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

# Keys added by the scopes git-resilience / leak series. Deliberately explicit:
# a new key belongs in the public reference AND in this list.
_TRACKED_KEYS = (
    "SCOPES_GIT_FETCH_TIMEOUT",
    "SCOPES_GIT_MAX_WORKERS",
    "SCOPES_GIT_MAX_ZOMBIES",
    "SCOPES_GIT_PRELOAD_DRAIN_TIMEOUT",
    "SCOPES_ORPHAN_SWEEP_INTERVAL",
    "SCOPES_ORPHAN_SWEEP_RECLAIM_ON_EMPTY_STORE",
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


@pytest.mark.parametrize("key", _TRACKED_KEYS)
def test_scopes_key_description_is_verbatim_in_the_public_reference(key):
    if not _MDX.exists():  # running against an installed package, not the repo
        pytest.skip(f"{_MDX} not present in this checkout")

    description = _declared_description(_CONFIG_PY.read_text(), key)
    mdx = _normalize(_MDX.read_text())

    assert f"#### OPAL_{key}" in _MDX.read_text(), f"OPAL_{key} is undocumented"
    assert description in mdx, (
        f"OPAL_{key}'s description in configuration.mdx is a paraphrase, not the "
        f"config.py text. Copy it verbatim:\n\n{description}"
    )
