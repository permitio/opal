from typing import Any, Dict, List, Optional


# Normalize incoming OPAL data payloads into OpenFGA /stores/{id}/write request dicts.
def normalize_openfga_write_payload(
    policy_data: Any, authorization_model_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    writes, deletes = _extract_writes_and_deletes(policy_data)
    if not writes and not deletes:
        return None
    return _build_write_payload((writes, deletes), authorization_model_id)


def _build_write_payload(
    changes: tuple[List[Dict[str, Any]], List[Dict[str, Any]]],
    authorization_model_id: Optional[str],
) -> Dict[str, Any]:
    writes, deletes = changes
    payload: Dict[str, Any] = {}
    if writes:
        payload["writes"] = {"tuple_keys": writes}
    if deletes:
        payload["deletes"] = {"tuple_keys": deletes}
    if authorization_model_id:
        payload["authorization_model_id"] = authorization_model_id
    return payload


def _extract_writes_and_deletes(
    policy_data: Any,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if isinstance(policy_data, list):
        return _normalize_tuple_list(policy_data), []
    if not isinstance(policy_data, dict):
        return [], []
    if _is_single_tuple(policy_data):
        return [_normalize_single_tuple(policy_data)], []
    writes = _extract_tuple_section(policy_data, ("writes", "tuples", "tuple_keys"))
    deletes = _extract_tuple_section(policy_data, ("deletes",))
    return writes, deletes


def _extract_tuple_section(
    data: Dict[str, Any], keys: tuple[str, ...]
) -> List[Dict[str, Any]]:
    for key in keys:
        section = data.get(key)
        extracted = _unwrap_section_value(section)
        if extracted:
            return extracted
    return []


def _unwrap_section_value(section: Any) -> List[Dict[str, Any]]:
    if isinstance(section, list):
        return _normalize_tuple_list(section)
    if isinstance(section, dict):
        nested = section.get("tuple_keys")
        if isinstance(nested, list):
            return _normalize_tuple_list(nested)
    return []


def _is_single_tuple(candidate: Dict[str, Any]) -> bool:
    for required in ("user", "relation", "object"):
        if required not in candidate:
            return False
    return True


def _normalize_single_tuple(item: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {
        "user": str(item["user"]),
        "relation": str(item["relation"]),
        "object": str(item["object"]),
    }
    condition = item.get("condition")
    if condition is not None:
        normalized["condition"] = condition
    return normalized


def _unwrap_tuple_candidate(item: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict):
        return None
    inner = item.get("key")
    candidate = inner if isinstance(inner, dict) else item
    if _is_single_tuple(candidate):
        return _normalize_single_tuple(candidate)
    return None


def _normalize_tuple_list(items: List[Any]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for item in items:
        normalized = _unwrap_tuple_candidate(item)
        if normalized is not None:
            result.append(normalized)
    return result


# Extract normalized tuple_keys from an OpenFGA /stores/{id}/read response payload.
def extract_read_tuples(read_response: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_tuples = read_response.get("tuples", [])
    if not isinstance(raw_tuples, list):
        return []
    return _normalize_tuple_list(raw_tuples)


# Filter relationship tuples matching a hierarchical OPAL data path selector.
def filter_tuples_by_path(
    tuples: List[Dict[str, Any]], path: str
) -> List[Dict[str, Any]]:
    cleaned = path.strip("/")
    if not cleaned or cleaned in ("tuples", "writes"):
        return tuples
    parts = [segment for segment in cleaned.split("/") if segment]
    return [t for t in tuples if _tuple_matches_segments(t, parts)]


def _tuple_matches_segments(
    tuple_item: Dict[str, Any], segments: List[str]
) -> bool:
    if len(segments) == 1:
        return _matches_single_segment(tuple_item, segments[0])
    if len(segments) == 2:
        return _matches_two_segments(tuple_item, (segments[0], segments[1]))
    return _matches_three_segments(
        tuple_item, (segments[0], segments[1], segments[2])
    )


def _matches_single_segment(tuple_item: Dict[str, Any], target: str) -> bool:
    if tuple_item.get("object") == target:
        return True
    return tuple_item.get("user") == target


def _matches_two_segments(
    tuple_item: Dict[str, Any], pair: tuple[str, str]
) -> bool:
    first, second = pair
    if tuple_item.get("object") == f"{first}:{second}":
        return True
    if tuple_item.get("object") != first:
        return False
    return tuple_item.get("relation") == second


def _matches_three_segments(
    tuple_item: Dict[str, Any], triple: tuple[str, str, str]
) -> bool:
    obj_type, obj_id, relation = triple
    if tuple_item.get("object") != f"{obj_type}:{obj_id}":
        return False
    return tuple_item.get("relation") == relation
