"""Every value the public configuration reference gives for a setting loads,
and every setting it documents is one the code reads (PER-18263).

The reference gave values that stopped a server or a client at startup when
copied into the environment: `opa` for OPAL_POLICY_STORE_TYPE (whose values
are `OPA` and `CEDAR`), `SSH` and `PEM` for the key formats (`ssh`, `pem`),
`"POST"` in OPAL_DEFAULT_UPDATE_CALLBACK_CONFIG (`post`). It also documented
OPAL_DATA_UPDATE_TRIGGER_ROUTE, which was declared under another setting's
environment name and read by no code, so setting it did nothing.

config_docs_drift_test.py checks the text of the SCOPES_* settings. This
checks the values and the names of every setting in the reference, from the
server, client and common configs: each default, each option, and each
example (an ``export OPAL_...=`` line or an inline ``OPAL_...=`` code span).
"""

import collections
import io
import os
import re
import shlex
import tokenize
from pathlib import Path

import pytest
from opal_client.config import OpalClientConfig, opal_client_config
from opal_common.config import OpalCommonConfig, opal_common_config
from opal_server import config as server_config_module
from opal_server.config import OpalServerConfig, opal_server_config

_PACKAGES = Path(server_config_module.__file__).parents[2]
_MDX = (
    _PACKAGES.parent
    / "documentation"
    / "docs"
    / "getting-started"
    / "configuration.mdx"
)
_CONFIGS = (
    (OpalCommonConfig, opal_common_config),
    (OpalServerConfig, opal_server_config),
    (OpalClientConfig, opal_client_config),
)

# Example values a reader replaces with a key of their own: no placeholder
# text loads as a key.
_PLACEHOLDERS = {
    ("AUTH_PRIVATE_KEY", "your-rsa-private-key"),
    ("AUTH_PUBLIC_KEY", "your-rsa-public-key"),
}


def _sections(mdx: str):
    """(key, body) of each `#### OPAL_<key>` section."""
    return re.findall(r"^#### OPAL_(\w+)\n(.*?)(?=^#{2,4} |\Z)", mdx, re.M | re.S)


def _default(body: str):
    inline = re.search(r"^Default: `([^`]*)`", body, re.M)
    if inline:
        return inline.group(1)
    block = re.search(r"^Default:\s*\n```\w*\n(.*?)\n```", body, re.M | re.S)
    return block.group(1) if block else None


def _documented_values(mdx: str):
    """(key, value, where) for each value the reference gives a setting."""
    values = []
    for key, body in _sections(mdx):
        values.append((key, _default(body), "default"))
        options = re.search(r"Options: (.*)$", body, re.M)
        if options:
            for option in re.findall(r"`([^`]*)`", options.group(1)):
                values.append((key, option, "option"))
    for block in re.findall(r"^```(?:bash|sh|shell)\n(.*?)^```", mdx, re.M | re.S):
        for token in shlex.split(block, comments=True):
            assignment = re.fullmatch(r"OPAL_(\w+)=(.*)", token, re.S)
            if assignment:
                values.append((*assignment.groups(), "export example"))
    for key, value in re.findall(r"`OPAL_(\w+)=([^`]*)`", mdx):
        values.append((key, value, "inline example"))
    return values


def _readers():
    """Env key (without the prefix) -> the config classes that read it, and the
    attributes they read it into."""
    readers = collections.defaultdict(list)
    for config_class, config in _CONFIGS:
        for attribute, entry in config.entries.items():
            readers[entry.key].append((config_class, attribute))
    return readers


_READERS = _readers()
_VALUES = [
    (key, value, where)
    for key, value, where in _documented_values(_MDX.read_text())
    # `None` is the reference's word for unset.
    if key in _READERS and value != "None" and (key, value) not in _PLACEHOLDERS
]


def test_every_section_has_a_default_this_test_reads():
    """A guard that finds no values guards nothing: a reformatted `Default:`
    line would empty the list below without failing anything."""
    sections = _sections(_MDX.read_text())
    assert len(sections) == _MDX.read_text().count("\n#### OPAL_")
    assert [key for key, body in sections if _default(body) is None] == []
    assert len(_VALUES) > 100


@pytest.mark.parametrize(
    "key, value, where",
    _VALUES,
    ids=[f"OPAL_{key}-{where}-{i}" for i, (key, _, where) in enumerate(_VALUES)],
)
def test_a_documented_value_loads(key, value, where, monkeypatch):
    for name in [name for name in os.environ if name.startswith("OPAL_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv(f"OPAL_{key}", value)
    # OpalClientConfig.on_load adds to this list of the common config.
    monkeypatch.setattr(
        opal_common_config,
        "LOG_MODULE_EXCLUDE_LIST",
        list(opal_common_config.LOG_MODULE_EXCLUDE_LIST),
    )
    for config_class, _ in _READERS[key]:
        try:
            config_class(prefix="OPAL_")
        except Exception as e:
            pytest.fail(
                f"OPAL_{key}={value!r}, {_MDX.name}'s {where}, fails to load "
                f"in {config_class.__name__}: {type(e).__name__}: {e}"
            )


def _identifier_uses():
    """How often each name is used in the packages' code, tests left out: as an
    identifier (``config.NAME``, a delayed default's ``lambda NAME=...``), or
    as ``{NAME}`` in a string (a delayed default's template).

    Comments and the rest of a string's text do not count.
    """
    uses = collections.Counter()
    for path in _PACKAGES.rglob("*.py"):
        parts = path.relative_to(_PACKAGES).parts
        if "tests" in parts or path.name.endswith("_test.py"):
            continue
        source = io.StringIO(path.read_text(encoding="utf-8"))
        for token in tokenize.generate_tokens(source.readline):
            if token.type == tokenize.NAME:
                uses[token.string] += 1
            elif token.type == tokenize.STRING:
                uses.update(re.findall(r"\{(\w+)\}", token.string))
    return uses


def test_every_documented_setting_is_read_by_the_code():
    """Read means that a config reads the documented name from the environment,
    and that the attribute it reads it into is used beyond its declaration."""
    uses = _identifier_uses()
    declarations = collections.Counter(
        attribute for readers in _READERS.values() for _, attribute in readers
    )
    unread = {
        key
        for key, _ in _sections(_MDX.read_text())
        if not any(
            uses[attribute] > declarations[attribute]
            for _, attribute in _READERS.get(key, [])
        )
    }

    assert not unread, (
        f"{_MDX.name} documents {sorted(unread)}, and setting them does nothing: "
        "no config reads the name, or no code uses what it read. Declare and use "
        "the setting, or take it out of the reference."
    )
