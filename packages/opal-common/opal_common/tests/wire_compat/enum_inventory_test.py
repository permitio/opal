"""Every enum-bearing model must be a deliberate decision, not an oversight.

The inline-OPA regression was one instance of a class: under pydantic v2
``use_enum_values`` fires at validation time, defaults are never validated, and
a ``force_enum`` validator can put the member back afterwards - so an enum field
can reach a python-mode dump as the MEMBER where v1 gave its value. That value
renders as ``ClassName.member`` in an f-string on python 3.11+ and is not JSON
serialisable if the enum is not a ``str`` mixin.

The corpus in ``payloads.py`` pins the models we know about. This test stops a
NEW enum-bearing model from quietly joining them: every such model must either
have a wire_compat case, or be listed in ``NOT_ON_THE_WIRE`` with a reason.

It is an inventory check, not a behaviour check - it fails when someone adds a
model, which is exactly when the decision should be made.
"""

import enum
import importlib
import pkgutil
import typing
from typing import Dict, Set, Tuple

import pytest
from pydantic import BaseModel

from .payloads import CASES

# Packages swept for models.
#
# Must cover opal_client and opal_server, not just opal_common: the inline-OPA
# regression this PR fixes lived in `opal_client.engine.options`, and a sweep
# that cannot see that package cannot claim to force a decision on the shape
# that produced it. Two of the NOT_ON_THE_WIRE entries below name models there
# and were INERT - never consulted - until this list was widened.
#
# Entries must be PACKAGES, not modules: `_discover` calls
# `pkgutil.walk_packages(package.__path__, ...)` and a module has no
# `__path__`. So `opal_client.policy_store`, not
# `opal_client.policy_store.schemas`.
#
# Deliberately NOT swept: `opal_server.server`, `opal_server.main` and
# `opal_client.client`, whose import has side effects (app construction,
# config binding). Models that reach a wire do not live there.
SWEPT_PACKAGES = (
    "opal_common.schemas",
    "opal_common.fetcher",
    "opal_client.engine",
    "opal_client.policy_store",
    "opal_client.policy",
    "opal_server.scopes",
)

# Enum-bearing models that deliberately never reach a wire. A reason is
# mandatory - "it looked fine" is how the OPA regression shipped.
NOT_ON_THE_WIRE: Dict[str, str] = {
    "opal_client.engine.options:OpaServerOptions": (
        "not serialized to a peer - dumped to build OPA's argv. Covered instead "
        "by opal_client/tests/opa_argv_real_binary_test.py, which hands the argv "
        "to the real opa binary across the CI python matrix."
    ),
    "opal_client.engine.options:CedarServerOptions": (
        "get_args() yields explicit strings and never formats an enum into an "
        "argument, so the dump path does not apply."
    ),
    "opal_client.policy.options:ConnRetryOptions": (
        "configuration, not a payload: read via confi.model for the four "
        "OPAL_*_CONN_RETRY keys and consumed in-process by toTenacityConfig(), "
        "which reads the attribute rather than a dump. `WaitStrategy` is a str "
        "mixin compared as an enum, so neither the member nor its value changes "
        "that comparison. Never serialized to a peer."
    ),
    "opal_common.schemas.webhook:GitWebhookRequestParams": (
        "configuration, not a payload: it is OPAL_POLICY_REPO_WEBHOOK_PARAMS, read "
        "server-side via confi.model and never sent to a peer. Its enum is compared "
        "as an enum (webhook/deps.py:52) and SecretTypeEnum is a str mixin, so "
        "neither the member nor its value changes that comparison."
    ),
}


def _enum_fields(model: type) -> Set[str]:
    """Field names whose annotation is (or contains) an Enum subclass."""
    found = set()
    for name, field in getattr(model, "model_fields", {}).items():
        stack = [field.annotation]
        while stack:
            annotation = stack.pop()
            if isinstance(annotation, type) and issubclass(annotation, enum.Enum):
                found.add(name)
                break
            stack.extend(a for a in typing.get_args(annotation) if a is not None)
    return found


# Modules the sweep could not import, as (module, error). A module that fails
# to import is silently absent from the sweep, so an uncovered model inside it
# passes - the coverage gap and the import failure are indistinguishable from
# the outside. Collected here and asserted empty rather than discarded.
IMPORT_FAILURES: list = []


def _discover() -> Dict[str, Tuple[type, Set[str]]]:
    """Every model in SWEPT_PACKAGES carrying at least one enum field."""
    out = {}
    for package_name in SWEPT_PACKAGES:
        package = importlib.import_module(package_name)
        modules = [package]
        for info in pkgutil.walk_packages(package.__path__, f"{package_name}."):
            try:
                modules.append(importlib.import_module(info.name))
            except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                IMPORT_FAILURES.append((info.name, f"{type(exc).__name__}: {exc}"))
                continue
        for module in modules:
            for attr in vars(module).values():
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseModel)
                    and attr is not BaseModel
                    and attr.__module__.startswith(tuple(SWEPT_PACKAGES))
                ):
                    fields = _enum_fields(attr)
                    if fields:
                        out[f"{attr.__module__}:{attr.__name__}"] = (attr, fields)
    return out


DISCOVERED = _discover()


def test_sweep_actually_found_models():
    """Guard against the sweep silently finding nothing and passing
    vacuously."""
    assert DISCOVERED, (
        f"no enum-bearing models discovered in {SWEPT_PACKAGES} - the sweep is "
        "broken, and every assertion below would pass for the wrong reason"
    )


def test_sweep_imported_every_module():
    """A module the sweep could not import is a module it cannot police.

    Non-empty is not the same as complete: a sweep that quietly covers less than
    it did yesterday still satisfies `assert DISCOVERED`. The realistic trigger
    is a circular import that only manifests under a different collection order,
    or an optional dependency missing on one leg of the matrix.
    """
    assert not IMPORT_FAILURES, (
        "the enum sweep could not import these modules, so any enum-bearing "
        "model inside them is invisible to it:\n  "
        + "\n  ".join(f"{name}: {err}" for name, err in IMPORT_FAILURES)
    )


def test_sweep_covers_every_package_it_claims_to():
    """Each SWEPT_PACKAGES entry must actually be walkable.

    `pkgutil.walk_packages` needs `__path__`, so a MODULE listed here would
    raise rather than contribute - and the entry would read as covered while
    contributing nothing.
    """
    not_packages = []
    for name in SWEPT_PACKAGES:
        mod = importlib.import_module(name)
        if not hasattr(mod, "__path__"):
            not_packages.append(name)

    assert not not_packages, (
        f"these SWEPT_PACKAGES entries are modules, not packages, so they are "
        f"not walked: {not_packages}. Use the containing package instead."
    )


def _reachable_models(root: type, seen=None) -> Set[str]:
    """Every model reachable from ``root`` through its field annotations.

    A corpus case covers what it embeds: ``TokenDetails`` is asserted by the
    ``access_token`` case even though the case only names ``AccessToken``.
    """
    seen = seen if seen is not None else set()
    dotted = f"{root.__module__}:{root.__name__}"
    if dotted in seen:
        return seen
    seen.add(dotted)

    for field in getattr(root, "model_fields", {}).values():
        stack = [field.annotation]
        while stack:
            annotation = stack.pop()
            if (
                isinstance(annotation, type)
                and issubclass(annotation, BaseModel)
                and annotation is not BaseModel
            ):
                _reachable_models(annotation, seen)
            else:
                stack.extend(a for a in typing.get_args(annotation) if a is not None)
    return seen


def _covered_by_corpus() -> Set[str]:
    covered: Set[str] = set()
    for case in CASES:
        module_path, _, class_name = case.model.partition(":")
        model = getattr(importlib.import_module(module_path), class_name)
        covered |= _reachable_models(model)
    return covered


COVERED = _covered_by_corpus()


@pytest.mark.parametrize("dotted", sorted(DISCOVERED))
def test_enum_bearing_model_is_covered_or_excused(dotted):
    """Each enum-bearing model has a corpus case or a written exclusion."""
    if dotted in COVERED or dotted in NOT_ON_THE_WIRE:
        return

    _, fields = DISCOVERED[dotted]
    pytest.fail(
        f"\n{dotted} has enum field(s) {sorted(fields)} but no wire_compat case.\n\n"
        "Under v2 an enum field can reach a python-mode dump as the MEMBER, which "
        "renders as 'ClassName.member' in an f-string on python 3.11+ and is not "
        "JSON serialisable for a non-str enum.\n\n"
        "Either add a Case to payloads.py (and regenerate the goldens under v1), "
        "or add it to NOT_ON_THE_WIRE with the reason it never reaches a peer."
    )


def test_exclusions_still_exist():
    """A stale exclusion hides a model that was renamed or moved."""
    missing = []
    for dotted in NOT_ON_THE_WIRE:
        module_path, _, class_name = dotted.partition(":")
        try:
            getattr(importlib.import_module(module_path), class_name)
        except (ImportError, AttributeError):
            missing.append(dotted)

    assert not missing, (
        f"NOT_ON_THE_WIRE names models that no longer exist: {missing}. "
        "Remove the entry, or point it at the model's new name."
    )
