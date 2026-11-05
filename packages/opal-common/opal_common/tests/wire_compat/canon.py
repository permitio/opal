"""Canonical rendering of a PYTHON-mode model dump, for cross-version diffing.

``model_dump_json()`` is not enough on its own. JSON mode unwraps enums,
datetimes and Paths whatever the model config says, so a JSON-only corpus
cannot see the trap that broke inline OPA and the publish payload: under v2,
``use_enum_values`` is applied at *validation* time and defaults are never
validated, so ``model_dump()`` in python mode hands back the enum MEMBER where
v1's ``.dict()`` handed back its value.

That surface is real - ``get_cli_options_dict()``, the ``dict(model)`` config
coercion and anything that calls ``json.dumps`` on a dump all live there - so
the corpus captures it too. A python-mode dump holds non-JSON objects, so it is
rendered into a JSON-safe structure that keeps the TYPE visible:

    'get'                 ->  "get"
    HttpMethods.GET       ->  {"__enum__": "HttpMethods.GET", "value": "get"}
    datetime(...)         ->  {"__datetime__": "2027-09-15T10:00:00"}
    PosixPath('a/b')      ->  {"__path__": "a/b"}

A v1 dump giving ``"get"`` against a v2 dump giving ``{"__enum__": ...}`` is
then an ordinary, readable diff rather than an invisible pass.

This module is imported by both the v1 generator and the v2 test suite, so it
must not import pydantic and must behave identically on both.
"""

import datetime as _datetime
import enum as _enum
import pathlib as _pathlib
import uuid as _uuid
from typing import Any

_PLAIN = (str, int, float, bool, type(None))


def canonical(value: Any) -> Any:
    """Render a python-mode dump into a JSON-safe, type-preserving
    structure."""
    # bool is an int subclass; check enum first since IntEnum/StrEnum are too
    if isinstance(value, _enum.Enum):
        return {
            "__enum__": f"{type(value).__name__}.{value.name}",
            "value": canonical(value.value),
        }
    if isinstance(value, _PLAIN):
        return value
    if isinstance(value, dict):
        return {str(k): canonical(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = [canonical(v) for v in value]
        if isinstance(value, (set, frozenset)):
            # sets have no wire order; sort by repr so the diff is stable
            items = sorted(items, key=repr)
            return {"__set__": items}
        if isinstance(value, tuple):
            return {"__tuple__": items}
        return items
    if isinstance(value, _datetime.datetime):
        return {"__datetime__": value.isoformat()}
    if isinstance(value, _datetime.date):
        return {"__date__": value.isoformat()}
    if isinstance(value, _datetime.timedelta):
        return {"__timedelta__": value.total_seconds()}
    if isinstance(value, _pathlib.PurePath):
        return {"__path__": str(value)}
    if isinstance(value, _uuid.UUID):
        return {"__uuid__": str(value)}
    if isinstance(value, bytes):
        return {"__bytes__": value.decode("utf-8", "replace")}
    # A BaseModel here means the dump did not go all the way down, which is
    # itself worth seeing in a diff - record the type without importing pydantic.
    return {"__object__": type(value).__name__, "repr": repr(value)}
