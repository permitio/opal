"""Realistic third-party fetch-provider shapes, written the way v1 taught.

Custom fetch providers are pydantic models that live OUTSIDE this repo, so the
population is unbounded and cannot be grepped. What we can do is characterise
it: take provider code written against pydantic v1 - the only way it could have
been written, since every released opal-common pins v1 - and see which shapes
still work under v2.

Each shape is built inside a function rather than at module import, because the
whole point is that some of them RAISE while the class is being defined (a bare
``@root_validator`` is the one hard break). A module-level definition would take
the sweep down with it.

Every shape returns a dict describing what happened, so the same file produces a
comparable matrix under either pydantic version. ``provider_conformance.py``
runs it; ``provider_conformance_test.py`` asserts the v2 column in CI.
"""

from typing import Any, Callable, Dict, List, Optional

import pydantic

V1 = pydantic.VERSION.startswith("1.")


def _ok(**extra) -> Dict[str, Any]:
    return dict(status="ok", **extra)


def _broken(exc: BaseException, when: str) -> Dict[str, Any]:
    return {
        "status": "broken",
        "when": when,  # "import" is the severe one: the provider cannot load
        "error": f"{type(exc).__name__}: {str(exc).splitlines()[0][:120]}",
    }


# --- shapes -----------------------------------------------------------------


def shape_optional_config_annotated():
    """The correct form: ``Optional[X] = None``."""
    from opal_common.fetcher.events import FetcherConfig, FetchEvent

    try:

        class Cfg(FetcherConfig):
            dsn: Optional[str] = None

        class Ev(FetchEvent):
            fetcher: str = "P"
            config: Optional[Cfg] = None

    except Exception as exc:  # noqa: BLE001
        return _broken(exc, "import")

    try:
        empty = Ev(url="u")
        filled = Ev(url="u", config=Cfg(dsn="postgres://h/db"))
    except Exception as exc:  # noqa: BLE001
        return _broken(exc, "runtime")
    return _ok(config_optional=empty.config is None, value=filled.config.dsn)


def shape_bare_config_default_none():
    """``config: X = None`` without Optional - trap 1.

    v1 made a field with a ``None`` default implicitly optional. v2 does not, so
    the field becomes REQUIRED and constructing the event without it raises.
    """
    from opal_common.fetcher.events import FetcherConfig, FetchEvent

    try:

        class Cfg(FetcherConfig):
            dsn: str = None

        class Ev(FetchEvent):
            fetcher: str = "P"
            config: Cfg = None

    except Exception as exc:  # noqa: BLE001
        return _broken(exc, "import")

    try:
        event = Ev(url="u")
    except Exception as exc:  # noqa: BLE001
        return _broken(exc, "runtime")
    return _ok(config_optional=event.config is None)


def shape_optional_without_default():
    """``Optional[X]`` with NO default - the actual trap 1.

    Distinct from ``shape_bare_config_default_none``: an explicit ``= None`` is
    a default and stays optional under both versions. A BARE ``Optional[X]``
    defaulted to None in v1 and is REQUIRED in v2, so a provider whose config
    was constructible with no arguments stops being so.
    """
    from opal_common.fetcher.events import FetcherConfig

    try:

        class Cfg(FetcherConfig):
            dsn: Optional[str]  # no default - this is the trap

    except Exception as exc:  # noqa: BLE001
        return _broken(exc, "import")

    try:
        built = Cfg()
    except Exception as exc:  # noqa: BLE001
        return _broken(exc, "runtime")
    return _ok(constructible_with_no_args=True, value=built.dsn)


def shape_inner_class_config():
    """An inner ``class Config`` instead of ``model_config``."""
    from opal_common.fetcher.events import FetcherConfig

    try:

        class Cfg(FetcherConfig):
            token: Optional[str] = None

            class Config:
                allow_population_by_field_name = True
                use_enum_values = True

    except Exception as exc:  # noqa: BLE001
        return _broken(exc, "import")

    try:
        return _ok(value=Cfg(token="t").token)
    except Exception as exc:  # noqa: BLE001
        return _broken(exc, "runtime")


def shape_v1_validator():
    """``@validator`` rather than ``@field_validator``."""
    from opal_common.fetcher.events import FetcherConfig

    try:
        from pydantic import validator

        class Cfg(FetcherConfig):
            port: Optional[int] = None

            @validator("port")
            def _check(cls, v):  # noqa: N805
                if v is not None and v < 0:
                    raise ValueError("port must be >= 0")
                return v

    except Exception as exc:  # noqa: BLE001
        return _broken(exc, "import")

    try:
        good = Cfg(port=5432).port
        try:
            Cfg(port=-1)
            enforced = False
        except Exception:  # noqa: BLE001 - the validator firing is the point
            enforced = True
    except Exception as exc:  # noqa: BLE001
        return _broken(exc, "runtime")
    return _ok(value=good, validator_enforced=enforced)


def shape_bare_root_validator():
    """A bare ``@root_validator`` - the one break that happens at IMPORT."""
    from opal_common.fetcher.events import FetcherConfig

    try:
        from pydantic import root_validator

        class Cfg(FetcherConfig):
            a: Optional[str] = None
            b: Optional[str] = None

            @root_validator
            def _both_or_neither(cls, values):  # noqa: N805
                return values

    except Exception as exc:  # noqa: BLE001
        return _broken(exc, "import")

    try:
        return _ok(value=Cfg(a="x").a)
    except Exception as exc:  # noqa: BLE001
        return _broken(exc, "runtime")


def shape_root_validator_pre_true():
    """``@root_validator(pre=True)`` - the explicitly-parameterised form."""
    from opal_common.fetcher.events import FetcherConfig

    try:
        from pydantic import root_validator

        class Cfg(FetcherConfig):
            a: Optional[str] = None

            @root_validator(pre=True)
            def _normalise(cls, values):  # noqa: N805
                return values

    except Exception as exc:  # noqa: BLE001
        return _broken(exc, "import")

    try:
        return _ok(value=Cfg(a="x").a)
    except Exception as exc:  # noqa: BLE001
        return _broken(exc, "runtime")


def shape_dict_based_parse_event():
    """``parse_event`` built on ``.dict()``, as the tutorial showed."""
    from opal_common.fetcher.events import FetcherConfig, FetchEvent

    try:

        class Cfg(FetcherConfig):
            dsn: Optional[str] = None

        class Ev(FetchEvent):
            fetcher: str = "P"
            config: Optional[Cfg] = None

        def parse_event(event: FetchEvent) -> Ev:
            return Ev(**event.dict(exclude={"config"}), config=event.config)

    except Exception as exc:  # noqa: BLE001
        return _broken(exc, "import")

    try:
        base = FetchEvent(url="u", fetcher="P", config={"dsn": "d"})
        parsed = parse_event(base)
    except Exception as exc:  # noqa: BLE001
        return _broken(exc, "runtime")
    return _ok(value=getattr(parsed.config, "dsn", None))


def shape_alias_only_config():
    """A config populated only by alias - the silent-credential-loss case."""
    from opal_common.fetcher.events import FetcherConfig, FetchEvent
    from pydantic import Field

    try:

        class Cfg(FetcherConfig):
            api_key: Optional[str] = Field(None, alias="apiKey")

        class Ev(FetchEvent):
            fetcher: str = "P"
            config: Optional[Cfg] = None

    except Exception as exc:  # noqa: BLE001
        return _broken(exc, "import")

    try:
        event = Ev(url="u", config=Cfg(apiKey="SECRET"))
    except Exception as exc:  # noqa: BLE001
        return _broken(exc, "runtime")
    return _ok(value=event.config.api_key, preserved=event.config.api_key == "SECRET")


def shape_subclassed_config_extra_field():
    """A config subclass adding a field the declared type does not know."""
    from opal_common.fetcher.events import FetcherConfig, FetchEvent

    try:

        class Base(FetcherConfig):
            dsn: Optional[str] = None

        class Extended(Base):
            extra: Optional[str] = None

        class Ev(FetchEvent):
            fetcher: str = "P"
            config: Optional[Base] = None

    except Exception as exc:  # noqa: BLE001
        return _broken(exc, "import")

    try:
        event = Ev(url="u", config=Extended(dsn="d", extra="keepme"))
    except Exception as exc:  # noqa: BLE001
        return _broken(exc, "runtime")
    return _ok(
        value=getattr(event.config, "extra", None),
        preserved=getattr(event.config, "extra", None) == "keepme",
    )


def shape_config_model_where_dict_declared():
    """Passing a config MODEL to the base event, whose field is a dict."""
    from opal_common.fetcher.events import FetcherConfig, FetchEvent

    try:

        class Cfg(FetcherConfig):
            dsn: Optional[str] = None

    except Exception as exc:  # noqa: BLE001
        return _broken(exc, "import")

    try:
        event = FetchEvent(url="u", fetcher="P", config=Cfg(dsn="d"))
    except Exception as exc:  # noqa: BLE001
        return _broken(exc, "runtime")
    return _ok(value=(event.config or {}).get("dsn"))


SHAPES: Dict[str, Callable[[], Dict[str, Any]]] = {
    "optional_config_annotated": shape_optional_config_annotated,
    "bare_config_default_none": shape_bare_config_default_none,
    "optional_without_default": shape_optional_without_default,
    "inner_class_config": shape_inner_class_config,
    "v1_validator": shape_v1_validator,
    "bare_root_validator": shape_bare_root_validator,
    "root_validator_pre_true": shape_root_validator_pre_true,
    "dict_based_parse_event": shape_dict_based_parse_event,
    "alias_only_config": shape_alias_only_config,
    "subclassed_config_extra_field": shape_subclassed_config_extra_field,
    "config_model_where_dict_declared": shape_config_model_where_dict_declared,
}


def run_all() -> Dict[str, Dict[str, Any]]:
    out = {}
    for name, fn in SHAPES.items():
        try:
            out[name] = fn()
        except Exception as exc:  # noqa: BLE001 - a shape must never kill the sweep
            out[name] = _broken(exc, "harness")
    return out


def shape_names() -> List[str]:
    return list(SHAPES)
