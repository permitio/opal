"""The third-party fetch-provider compatibility contract, asserted in CI.

Custom fetch providers live outside this repo, so the population is unbounded.
``provider_shapes.py`` characterises it instead: provider code written the way
pydantic v1 taught, exercised under whichever version is installed.

This test pins the v2 column. Two shapes are expected to break, and BOTH are
documented in ``write_your_own_fetch_provider.mdx`` - if a third starts
breaking, or one of these silently starts working, this fails and the docs need
revisiting.

The v1 column is not asserted here (it needs a pydantic-v1 interpreter). Produce
the full side-by-side with:

    <v1-python> provider_conformance.py --out v1.json
    <v2-python> provider_conformance.py --out v2.json
    <v2-python> provider_conformance.py --compare v1.json v2.json
"""

import pydantic
import pytest

from .provider_shapes import SHAPES, run_all

# What a provider author can expect under pydantic v2, and why.
#
# "ok"     - v1-era code still works unchanged
# "broken" - the author must change something; the reason names what
EXPECTED = {
    "optional_config_annotated": ("ok", "Optional[X] = None is the correct form"),
    "bare_config_default_none": (
        "ok",
        "an explicit `= None` IS a default, so the field stays optional - this is "
        "NOT trap 1, see optional_without_default for the shape that does break",
    ),
    "optional_without_default": (
        "broken",
        "trap 1: a BARE Optional[X] defaulted to None in v1 and is REQUIRED in v2, "
        "so a config that used to be constructible with no arguments now raises. "
        "Breaks at RUNTIME, not import - the provider loads and then fails to "
        "build its config. Fix: write `Optional[X] = None`.",
    ),
    "inner_class_config": ("ok", "inner `class Config` still works via the v2 shim"),
    "v1_validator": ("ok", "@validator still works via the v2 shim"),
    "bare_root_validator": (
        "broken",
        "the one IMPORT-time break: a bare @root_validator raises PydanticUserError "
        "while the class is being defined, so the provider module cannot even load. "
        "Fix: @model_validator(mode='after'), or @root_validator(skip_on_failure=True).",
    ),
    "root_validator_pre_true": (
        "ok",
        "@root_validator(pre=True) is accepted - only the BARE form breaks",
    ),
    "dict_based_parse_event": ("ok", ".dict() still works via the v2 shim"),
    "alias_only_config": (
        "ok",
        "preserved by the coercion rule in opal_common.fetcher.events - a config "
        "populated only by alias would otherwise be silently blanked",
    ),
    "subclassed_config_extra_field": (
        "ok",
        "preserved by the same rule: a declared model type is passed through "
        "rather than flattened and re-validated",
    ),
    "config_model_where_dict_declared": (
        "ok",
        "the coercion shim keeps v1's behaviour of accepting a model where a "
        "plain dict is declared",
    ),
}

RESULTS = run_all()


@pytest.mark.skipif(
    not pydantic.VERSION.startswith("2."),
    reason="this pins the pydantic v2 column; run provider_conformance.py for v1",
)
@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_provider_shape_matches_the_documented_contract(shape):
    assert shape in EXPECTED, (
        f"{shape} has no documented expectation. Add it to EXPECTED with the "
        "reason, and to write_your_own_fetch_provider.mdx if it breaks."
    )
    expected, why = EXPECTED[shape]
    actual = RESULTS[shape]["status"]

    assert actual == expected, (
        f"\nprovider shape {shape!r} is {actual!r}, expected {expected!r}.\n"
        f"  documented reason: {why}\n"
        f"  detail: {RESULTS[shape]}\n\n"
        + (
            "A shape that started WORKING is good news - update EXPECTED and the "
            "migration note, which currently tells authors to change it."
            if expected == "broken"
            else "A shape that started BREAKING is a new burden on every "
            "third-party provider. It needs a fix here, or a documented "
            "migration step in write_your_own_fetch_provider.mdx."
        )
    )


@pytest.mark.skipif(not pydantic.VERSION.startswith("2."), reason="v2 column only")
def test_only_the_documented_shapes_break():
    """The headline claim: exactly two shapes need author action."""
    broken = sorted(n for n, r in RESULTS.items() if r["status"] == "broken")

    assert broken == ["bare_root_validator", "optional_without_default"], (
        f"the set of breaking provider shapes changed: {broken}.\n"
        "write_your_own_fetch_provider.mdx names exactly these two; update both "
        "together or provider authors get a surprise."
    )


def test_every_shape_is_documented():
    """A shape with no expectation would be asserted by nothing."""
    undocumented = sorted(set(SHAPES) - set(EXPECTED))
    stale = sorted(set(EXPECTED) - set(SHAPES))

    assert not undocumented, f"shapes with no documented expectation: {undocumented}"
    assert not stale, f"EXPECTED names shapes that no longer exist: {stale}"


def test_import_time_breaks_are_called_out_separately():
    """An import-time break is strictly worse than a runtime one.

    It stops the provider module loading at all, so it cannot be caught
    by the author's own error handling. The docs lead with these for
    that reason.
    """
    import_breaks = sorted(
        n
        for n, r in RESULTS.items()
        if r["status"] == "broken" and r.get("when") == "import"
    )

    assert import_breaks == ["bare_root_validator"], (
        f"the set of IMPORT-time provider breaks changed: {import_breaks}. "
        "These are the ones the migration note must lead with."
    )
