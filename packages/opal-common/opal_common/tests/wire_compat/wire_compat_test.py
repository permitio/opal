"""Every model that reaches the wire must serialize as pydantic v1 did.

Every OPAL client in the field runs opal-client 0.9.6, which is pydantic v1
(`0.9.9-rc.2` still pins ``pydantic[email]>=1.9.1,<2``). A v2 server therefore
publishes to, and is posted to by, v1 peers. Unit tests cannot see a break
there, because they exercise both sides at the same version.

The goldens in ``golden/`` were captured by ``generate_golden.py`` running
under pydantic 1.10.26 against a pre-migration checkout. They are the contract.

Two directions are asserted per case:

  forward   v2 serializes the same JSON document v1 did
  reverse   v2 parses the document v1 emitted   (a v1 peer talking to a v2 server)

Equality is on the parsed JSON document, not the byte string: key order is not
part of any wire contract and no JSON parser can observe it. Byte-identity is
reported separately, as information rather than as a failure.

An intended difference goes in ACCEPTED_DELTAS with a reason. Nothing is
tolerated silently.
"""

import json
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

from .canon import canonical
from .payloads import CASES, Case

GOLDEN_DIR = Path(__file__).parent / "golden"


# Differences from the v1 wire form that we have decided to keep. Each entry is
# (case name, json path, reason) and the reason must record how we established
# the delta is safe. Nothing is tolerated silently; an empty dict would mean
# this branch reproduces the v1 wire form exactly.
ACCEPTED_DELTAS: Dict[Tuple[str, str], str] = {
    ("access_token", "details.expired"): (
        "tz-aware datetime: v1 emits '+00:00', v2 emits 'Z'. Equivalent RFC 3339 "
        "spellings of the same instant. Verified a pydantic 1.10.26 peer parses "
        "BOTH to datetime(2027,9,15,10,0,tzinfo=utc), timestamp 1821002400.0 - so "
        "a v1 client reading a v2 server's POST /token response is unaffected. "
        "`expired` also has no consumer in-tree: opal_server/security/api.py:34 "
        "is the only reference and it only produces the value."
    ),
    # --- python-mode dumps: enum members survive where v1 unwrapped them -----
    # These four share one cause. ``use_enum_values`` fires at validation time
    # under v2, but a `force_enum` field_validator runs AFTER it and puts the
    # MEMBER back, so the stored attribute is an enum on both versions - and v1
    # then unwrapped it at .dict() time where v2's python mode does not.
    #
    # Every in-tree path that takes these to a wire was checked and goes through
    # JSON mode, so none of them can reach a json.dumps:
    #   DataUpdate publish  -> data_update_publisher, model_dump(mode="json")
    #   CallbackEntry       -> callbacks/register.py:64, reporter.py:47, model_dump_json()
    #   get_data_with_input -> opa_client.py:934, model_dump(mode="json")
    #   AccessTokenRequest  -> never python-mode dumped; consumers read .type.value
    # The JSON cases above assert the actual wire form for each of these models
    # and all pass, so the wire is unchanged. Recorded rather than "fixed":
    # forcing the value back would mean removing force_enum, which callers rely
    # on for `.value` and isinstance checks.
    ("http_fetcher_config", "method"): "enum member in python-mode dump; see note above",
    ("http_fetch_event", "config.method"): "enum member in python-mode dump; see note above",
    ("callback_entry", "config.method"): "enum member in python-mode dump; see note above",
    (
        "data_update_with_callbacks",
        "callback.callbacks[1].__tuple__[1].method",
    ): "enum member in python-mode dump; see note above",
    (
        "access_token_request_default_ttl",
        "type",
    ): "enum member in python-mode dump; see note above",
    (
        "access_token_request_explicit_ttl",
        "type",
    ): "enum member in python-mode dump; see note above",
    ("server_data_source_config_redirect", "external_source_url"): (
        "AnyHttpUrl is a str subclass in v1 and a pydantic_core.Url object in v2, "
        "so a python-mode dump holds an object rather than a str. The JSON form is "
        "identical (that case passes). Both in-tree consumers already call str() "
        "on it - opal_server/data/api.py:91 and scopes/api.py:810 - and those calls "
        "are PRE-EXISTING on master, not added by this migration."
    ),
}


def _resolve(dotted: str):
    module_path, _, class_name = dotted.partition(":")
    return getattr(import_module(module_path), class_name)


def _load_golden(name: str) -> Dict[str, Any]:
    path = GOLDEN_DIR / f"{name}.json"
    if not path.exists():
        pytest.fail(
            f"no golden for case '{name}'. Goldens are the v1 wire contract and "
            f"cannot be generated from this tree - see {Path(__file__).parent}/README.md"
        )
    return json.loads(path.read_text())


def _diff(expected: Any, actual: Any, path: str = "") -> List[str]:
    """Deep diff, reporting every difference rather than the first."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        out = []
        for key in sorted(set(expected) | set(actual)):
            where = f"{path}.{key}" if path else key
            if key not in expected:
                out.append(f"{where}: added by v2 = {actual[key]!r}")
            elif key not in actual:
                out.append(f"{where}: dropped by v2 (v1 had {expected[key]!r})")
            else:
                out.extend(_diff(expected[key], actual[key], where))
        return out
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return [f"{path}: length {len(expected)} -> {len(actual)}"]
        out = []
        for i, (e, a) in enumerate(zip(expected, actual)):
            out.extend(_diff(e, a, f"{path}[{i}]"))
        return out
    if expected != actual or type(expected) is not type(actual):
        return [
            f"{path}: {expected!r} ({type(expected).__name__})"
            f" -> {actual!r} ({type(actual).__name__})"
        ]
    return []


def _filter_accepted(case_name: str, diffs: List[str]) -> List[str]:
    remaining = []
    for d in diffs:
        where = d.split(":", 1)[0]
        if (case_name, where) in ACCEPTED_DELTAS:
            continue
        remaining.append(d)
    return remaining


def _ids(cases):
    return [c.name for c in cases]


@pytest.mark.parametrize("case", CASES, ids=_ids(CASES))
def test_serializes_as_pydantic_v1_did(case: Case):
    """Forward: what a v2 server emits must be what a v1 peer expects."""
    golden = _load_golden(case.name)
    model = _resolve(case.model)

    instance = model.model_validate(case.payload)

    for key, kwargs in (("json", {}), ("json_by_alias", {"by_alias": True})):
        produced = json.loads(instance.model_dump_json(**kwargs))
        diffs = _filter_accepted(case.name, _diff(golden[key], produced, ""))
        assert not diffs, (
            f"\n{case.name} ({key}) diverged from the pydantic "
            f"{golden['pydantic']} wire form.\n"
            f"  why this case exists: {case.note}\n"
            f"  model: {case.model}\n\n  " + "\n  ".join(diffs) + "\n\n"
            "If this change is intended, add it to ACCEPTED_DELTAS with a reason."
        )


@pytest.mark.parametrize("case", CASES, ids=_ids(CASES))
def test_parses_what_pydantic_v1_emitted(case: Case):
    """Reverse: a v2 server must accept a document a v1 peer sent."""
    golden = _load_golden(case.name)
    model = _resolve(case.model)

    try:
        instance = model.model_validate(golden["json_by_alias"])
    except Exception as exc:  # noqa: BLE001 - the failure message is the point
        pytest.fail(
            f"\n{case.name}: v2 cannot parse the document pydantic "
            f"{golden['pydantic']} emitted.\n"
            f"  why this case exists: {case.note}\n"
            f"  model: {case.model}\n"
            f"  {type(exc).__name__}: {exc}"
        )

    # and it must survive the round trip unchanged
    reserialized = json.loads(instance.model_dump_json(by_alias=True))
    diffs = _filter_accepted(case.name, _diff(golden["json_by_alias"], reserialized, ""))
    assert not diffs, (
        f"\n{case.name}: v2 parsed the v1 document but re-serialized it "
        f"differently.\n  " + "\n  ".join(diffs)
    )


@pytest.mark.parametrize("case", CASES, ids=_ids(CASES))
def test_python_mode_dump_matches_pydantic_v1(case: Case):
    """The python-mode dump must hold the same values v1's ``.dict()`` did.

    JSON mode unwraps enums whatever the model config says, so the JSON cases
    above cannot see this. Python mode is where the real surface is:
    ``get_cli_options_dict()`` f-strings these values into OPA's argv, the
    ``dict(model)`` config coercion stores them, and anything calling
    ``json.dumps`` on a dump needs them to be plain types. Under v2
    ``use_enum_values`` fires at validation time and defaults are never
    validated, so an unset enum field comes back as the MEMBER here.
    """
    golden = _load_golden(case.name)
    model = _resolve(case.model)

    instance = model.model_validate(case.payload)

    for key, kwargs in (("dict", {}), ("dict_by_alias", {"by_alias": True})):
        produced = canonical(instance.model_dump(**kwargs))
        diffs = _filter_accepted(case.name, _diff(golden[key], produced, ""))
        assert not diffs, (
            f"\n{case.name} ({key}) python-mode dump diverged from pydantic "
            f"{golden['pydantic']}.\n"
            f"  why this case exists: {case.note}\n"
            f"  model: {case.model}\n\n  " + "\n  ".join(diffs) + "\n\n"
            "A '__enum__' on the v2 side means use_enum_values did not fire - "
            "that value will render as 'ClassName.member' in an f-string on "
            "python 3.11+ and is not JSON serializable."
        )


@pytest.mark.parametrize("case", CASES, ids=_ids(CASES))
def test_published_payload_is_json_serializable(case: Case):
    """A python-mode dump must still be handed to json.dumps safely.

    ``data_update_publisher`` publishes ``model_dump(...)`` and downstream
    serializers call ``json.dumps`` on it. v1's ``.dict()`` unwrapped enums;
    v2's python mode does not, so an enum field here is a latent TypeError.
    """
    model = _resolve(case.model)
    instance = model.model_validate(case.payload)

    json.dumps(instance.model_dump(mode="json", by_alias=True))


def test_corpus_covers_every_golden():
    """A golden with no case would silently stop being asserted."""
    on_disk = {p.stem for p in GOLDEN_DIR.glob("*.json")}
    in_corpus = {c.name for c in CASES}

    assert not (on_disk - in_corpus), (
        f"goldens with no corpus case (they are no longer asserted): "
        f"{sorted(on_disk - in_corpus)}"
    )
    assert not (in_corpus - on_disk), (
        f"corpus cases with no golden (run generate_golden.py under v1): "
        f"{sorted(in_corpus - on_disk)}"
    )


def test_goldens_were_captured_under_pydantic_v1():
    """A golden regenerated under v2 would assert v2 against itself."""
    offenders = []
    for path in sorted(GOLDEN_DIR.glob("*.json")):
        version = json.loads(path.read_text()).get("pydantic", "")
        if not str(version).startswith("1."):
            offenders.append(f"{path.name}: pydantic {version}")

    assert not offenders, (
        "these goldens were not captured under pydantic v1, so they prove "
        "nothing about wire compatibility:\n  " + "\n  ".join(offenders)
    )
