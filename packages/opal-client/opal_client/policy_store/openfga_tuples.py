"""Conversion of OPAL "policy data" into OpenFGA relationship tuples.

OPAL's data-update pipeline is store agnostic: an OPAL server publishes
data updates (fetched from external data sources) and each OPAL client
writes them into its policy store. For OpenFGA, "data" means relationship
tuples (the `user`, `relation`, `object` triples OpenFGA stores).

`convert_to_tuples` accepts the tuple-native shapes plus a convenient
nested form, so a regular data API (HR system, CRM, etc.) can serve data
that OPAL turns into tuples:

1. `{"tuples": [{"user": ..., "relation": ..., "object": ...}, ...]}`
2. `[{"user": ..., "relation": ..., "object": ...}, ...]`
3. `{"user": ..., "relation": ..., "object": ...}` (a single tuple)
4. `{"<object>": {"<relation>": ["<user>", ...]}}` (object -> relation -> users)
5. `{"<object>": {"<relation>": {"<user>": <condition>, ...}}}`
   (the same shape, where `<condition>` is an optional OpenFGA
   RelationshipCondition object: `{"name": <condition name>, "context": {...}}`)

Tuples are deduplicated while preserving order.
"""

from typing import Any, Dict, List

_TUPLE_FIELDS = ("user", "relation", "object")


class TupleConversionError(ValueError):
    """Raised when a data-update payload cannot be converted to tuples."""


def is_single_tuple(data: Dict) -> bool:
    """Checks whether a dict is a single flat relationship tuple."""
    return isinstance(data, dict) and all(field in data for field in _TUPLE_FIELDS)


def _validate_tuple(raw: Any) -> Dict:
    if not isinstance(raw, dict) or not is_single_tuple(raw):
        raise TupleConversionError(
            f"expected a tuple object with fields {list(_TUPLE_FIELDS)}, got {raw!r}"
        )
    tuple_data = {field: raw[field] for field in _TUPLE_FIELDS}
    for field, value in tuple_data.items():
        if not isinstance(value, str) or not value:
            raise TupleConversionError(
                f"tuple field {field!r} must be a non-empty string, got {value!r}"
            )
    # OpenFGA requires the '<type>:<id>' form for users and objects
    for field in ("user", "object"):
        if ":" not in tuple_data[field]:
            raise TupleConversionError(
                f"tuple field {field!r} must be in '<type>:<id>' form, "
                f"got {tuple_data[field]!r}"
            )
    # optional relationship condition (an OpenFGA RelationshipCondition:
    # {"name": ..., "context": {...}}, per the OpenFGA API spec)
    condition = raw.get("condition")
    if condition is not None:
        tuple_data["condition"] = _validate_condition(condition, error_prefix="tuple")
    return tuple_data


def _validate_condition(condition: Any, error_prefix: str) -> Dict:
    """Validates an OpenFGA RelationshipCondition object (name required)."""
    if not isinstance(condition, dict):
        raise TupleConversionError(
            f"{error_prefix} 'condition' must be an object, got {condition!r}"
        )
    if not isinstance(condition.get("name"), str) or not condition["name"]:
        raise TupleConversionError(
            f"{error_prefix} 'condition' must include a condition 'name' "
            f"(per the OpenFGA API spec), got {condition!r}"
        )
    validated: Dict[str, Any] = {"name": condition["name"]}
    if "context" in condition:
        if not isinstance(condition["context"], dict):
            raise TupleConversionError(
                f"{error_prefix} condition 'context' must be an object, "
                f"got {condition['context']!r}"
            )
        validated["context"] = condition["context"]
    return validated


def _convert_nested(data: Dict) -> List[Dict]:
    """Converts the nested {object: {relation: users}} form into tuples."""
    tuples: List[Dict] = []
    for object_id, relations in data.items():
        if not isinstance(object_id, str) or ":" not in object_id:
            raise TupleConversionError(
                f"expected object key in '<type>:<id>' form, got {object_id!r}"
            )
        if not isinstance(relations, dict):
            raise TupleConversionError(
                f"expected a mapping of relation -> users under {object_id!r}, "
                f"got {relations!r}"
            )
        for relation, users in relations.items():
            if not isinstance(relation, str) or not relation:
                raise TupleConversionError(
                    f"relation name must be a non-empty string, got {relation!r}"
                )
            if isinstance(users, dict):
                # {user: condition-context} form
                items = users.items()
            elif isinstance(users, list):
                items = ((user, None) for user in users)
            else:
                raise TupleConversionError(
                    f"expected a list or mapping of users under "
                    f"{object_id!r}.{relation!r}, got {users!r}"
                )
            for user, condition in items:
                if not isinstance(user, str) or ":" not in user:
                    raise TupleConversionError(
                        f"expected user in '<type>:<id>' form, got {user!r}"
                    )
                tuple_data: Dict[str, Any] = {
                    "user": user,
                    "relation": relation,
                    "object": object_id,
                }
                if isinstance(condition, dict):
                    if condition:
                        tuple_data["condition"] = _validate_condition(
                            condition, error_prefix=f"condition of user {user!r}"
                        )
                elif condition is not None:
                    raise TupleConversionError(
                        f"condition for user {user!r} must be an object, "
                        f"got {condition!r}"
                    )
                tuples.append(tuple_data)
    return tuples


def convert_to_tuples(data: Any) -> List[Dict]:
    """Converts an OPAL data-update payload into OpenFGA relationship tuples.

    See the module docstring for the accepted shapes. Raises
    `TupleConversionError` when the payload cannot be interpreted.
    """
    if isinstance(data, dict) and isinstance(data.get("tuples"), list):
        raw_tuples = data["tuples"]
    elif isinstance(data, list):
        raw_tuples = data
    elif isinstance(data, dict) and is_single_tuple(data):
        raw_tuples = [data]
    elif isinstance(data, dict):
        return _dedupe_tuples(_convert_nested(data))
    else:
        raise TupleConversionError(
            "data must be a list of tuples, a {'tuples': [...]} object, "
            "a single tuple, or a nested {object: {relation: [users]}} object; "
            f"got {type(data).__name__}"
        )

    tuples = [_validate_tuple(raw) for raw in raw_tuples]
    return _dedupe_tuples(tuples)


def _dedupe_tuples(tuples: List[Dict]) -> List[Dict]:
    """Removes exact duplicates (same user/relation/object/condition)."""
    seen = set()
    deduped = []
    for tuple_data in tuples:
        key = (
            tuple_data["user"],
            tuple_data["relation"],
            tuple_data["object"],
            json_key(tuple_data.get("condition")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(tuple_data)
    return deduped


def json_key(value: Any) -> Any:
    """Makes a hashable, order-insensitive key from a JSON-ish value."""
    if isinstance(value, dict):
        return frozenset((k, json_key(v)) for k, v in value.items())
    if isinstance(value, list):
        return tuple(json_key(item) for item in value)
    return value


def filter_tuples_by_object_prefix(tuples: List[Dict], prefix: str) -> List[Dict]:
    """Filters tuples whose object equals or starts with the given prefix.

    Used to scope `delete_policy_data` to a specific object (or object type).
    A leading "/" is tolerated and stripped, matching OPAL's data paths.
    """
    prefix = prefix.lstrip("/")
    if not prefix:
        return list(tuples)
    return [
        tuple_data
        for tuple_data in tuples
        if tuple_data["object"] == prefix
        or tuple_data["object"].startswith(f"{prefix}:")
        or tuple_data["object"].startswith(f"{prefix}/")
    ]
