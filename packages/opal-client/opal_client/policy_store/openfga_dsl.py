import json
import re
from typing import Any, Dict, List, Optional, Tuple


# Parse OpenFGA schema 1.1 DSL or JSON authorization models into canonical
# OpenFGA WriteAuthorizationModelRequest payloads for policy store synchronization.
def parse_fga_dsl_to_json(dsl_text: str) -> Dict[str, Any]:
    stripped = dsl_text.strip()
    if stripped.startswith("{"):
        return _parse_json_model(stripped)
    return _parse_dsl_model(stripped)


def _parse_json_model(raw_json: str) -> Dict[str, Any]:
    parsed = json.loads(raw_json)
    if not isinstance(parsed, dict):
        raise ValueError("OpenFGA JSON authorization model must be a dictionary.")
    if "type_definitions" not in parsed:
        raise ValueError(
            "OpenFGA JSON authorization model must contain type_definitions."
        )
    parsed.setdefault("schema_version", "1.1")
    return parsed


def _parse_dsl_model(stripped: str) -> Dict[str, Any]:
    schema_match = re.search(r"schema\s+(\d+\.\d+)", stripped)
    if not schema_match:
        raise ValueError(
            "Invalid OpenFGA model: must be JSON or DSL containing schema <version>."
        )
    schema_version = schema_match.group(1)
    type_definitions = _extract_type_definitions(stripped.splitlines())
    return {
        "schema_version": schema_version,
        "type_definitions": type_definitions,
    }


def _is_header_or_empty_line(line: str) -> bool:
    if not line:
        return True
    if line == "model":
        return True
    return line.startswith("schema ")


def _extract_type_definitions(lines: List[str]) -> List[Dict[str, Any]]:
    type_definitions: List[Dict[str, Any]] = []
    current_type: Optional[Dict[str, Any]] = None

    for raw_line in lines:
        line = raw_line.split("#", 1)[0].strip()
        if _is_header_or_empty_line(line):
            continue
        current_type = _process_dsl_line(type_definitions, (current_type, line))

    if current_type is not None:
        type_definitions.append(current_type)
    return type_definitions


def _process_dsl_line(
    type_definitions: List[Dict[str, Any]],
    state: Tuple[Optional[Dict[str, Any]], str],
) -> Optional[Dict[str, Any]]:
    current_type, line = state
    type_match = re.match(r"^type\s+([A-Za-z0-9_-]+)$", line)
    if type_match:
        if current_type is not None:
            type_definitions.append(current_type)
        return {"type": type_match.group(1)}
    if line == "relations":
        _enable_relations_section(current_type)
        return current_type
    if current_type is not None:
        _attach_relation_definition(current_type, line)
    return current_type


def _enable_relations_section(current_type: Optional[Dict[str, Any]]) -> None:
    if current_type is None:
        return
    current_type.setdefault("relations", {})
    current_type.setdefault("metadata", {"relations": {}})


def _attach_relation_definition(current_type: Dict[str, Any], line: str) -> None:
    if "relations" not in current_type:
        return
    rel_match = re.match(r"^define\s+([A-Za-z0-9_-]+)\s*:\s*(.+)$", line)
    if not rel_match:
        return
    rel_name = rel_match.group(1)
    rel_expr = rel_match.group(2).strip()
    rewrite_node, direct_types = _parse_relation_expression(rel_expr)
    current_type["relations"][rel_name] = rewrite_node
    current_type["metadata"]["relations"][rel_name] = {
        "directly_related_user_types": direct_types
    }


def _parse_relation_expression(
    expr: str,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if " but not " in expr:
        return _parse_exclusion_expression(expr)
    if " or " in expr:
        return _parse_composite_expression(expr, (" or ", "union"))
    if " and " in expr:
        return _parse_composite_expression(expr, (" and ", "intersection"))
    return _parse_atomic_expression(expr.strip())


def _parse_exclusion_expression(
    expr: str,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    base_str, subtract_str = expr.split(" but not ", 1)
    base_node, base_types = _parse_relation_expression(base_str.strip())
    sub_node, sub_types = _parse_relation_expression(subtract_str.strip())
    return (
        {"difference": {"base": base_node, "subtract": sub_node}},
        base_types + sub_types,
    )


def _parse_composite_expression(
    expr: str, op_spec: Tuple[str, str]
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    separator, node_key = op_spec
    parts = [part.strip() for part in expr.split(separator) if part.strip()]
    children: List[Dict[str, Any]] = []
    direct_types: List[Dict[str, Any]] = []
    for part in parts:
        child_node, child_types = _parse_atomic_expression(part)
        children.append(child_node)
        direct_types.extend(child_types)
    return {node_key: {"child": children}}, direct_types


def _parse_atomic_expression(
    token: str,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if token.startswith("[") and token.endswith("]"):
        return {"this": {}}, _parse_direct_type_restrictions(token[1:-1])
    from_match = re.match(
        r"^([A-Za-z0-9_-]+)\s+from\s+([A-Za-z0-9_-]+)$", token
    )
    if from_match:
        return (
            {
                "tupleToUserset": {
                    "tupleset": {"relation": from_match.group(2)},
                    "computedUserset": {"relation": from_match.group(1)},
                }
            },
            [],
        )
    return {"computedUserset": {"relation": token}}, []


def _parse_direct_type_restrictions(inner: str) -> List[Dict[str, Any]]:
    items = [item.strip() for item in inner.split(",") if item.strip()]
    return [_parse_single_type_restriction(item) for item in items]


def _parse_single_type_restriction(item: str) -> Dict[str, Any]:
    if item.endswith(":*"):
        return {"type": item[:-2].strip(), "wildcard": {}}
    if "#" in item:
        type_name, rel_name = item.split("#", 1)
        return {"type": type_name.strip(), "relation": rel_name.strip()}
    return {"type": item}
