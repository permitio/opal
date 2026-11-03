import asyncio
import copy
import json
import re
import ssl
import textwrap
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlencode

import aiohttp
import jsonpatch
import yaml
from aiofiles.threadpool.text import AsyncTextIOWrapper
from fastapi import Response, status
from opal_client.config import opal_client_config
from opal_client.logger import logger
from opal_client.policy_store.base_policy_store_client import (
    BasePolicyStoreClient,
    JsonableValue,
)
from opal_client.policy_store.liveness_probe import LivenessProbeMixin
from opal_client.policy_store.opa_client import (
    OpaTransactionLogState,
    affects_transaction,
    should_ignore_path,
)
from opal_client.policy_store.schemas import PolicyStoreAuth
from opal_client.utils import exclude_none_fields, proxy_response
from opal_common.git_utils.bundle_utils import BundleUtils
from opal_common.logging_utils.errors import describe_error
from opal_common.schemas.policy import DataModule, PolicyBundle, RegoModule
from opal_common.schemas.store import JSONPatchAction, StoreTransaction
from pydantic import BaseModel
from tenacity import retry

RETRY_CONFIG = {
    **opal_client_config.POLICY_STORE_CONN_RETRY.toTenacityConfig(),
    "reraise": True,
}
MAX_TUPLES_PER_WRITE = 100

_CONDITION_PARAM_TYPE_MAP: Dict[str, str] = {
    "string": "TYPE_NAME_STRING",
    "int": "TYPE_NAME_INT",
    "uint": "TYPE_NAME_UINT",
    "double": "TYPE_NAME_DOUBLE",
    "bool": "TYPE_NAME_BOOL",
    "timestamp": "TYPE_NAME_TIMESTAMP",
    "duration": "TYPE_NAME_DURATION",
    "bytes": "TYPE_NAME_BYTES",
    "ipaddress": "TYPE_NAME_IPADDRESS",
    "map": "TYPE_NAME_MAP",
    "list": "TYPE_NAME_LIST",
    "any": "TYPE_NAME_ANY",
}


async def proxy_openfga_response_unless_invalid(
    raw_response: aiohttp.ClientResponse, accepted_status_codes: List[int]
) -> Response:
    """Proxies an aiohttp response into a FastAPI Response and raises
    ValueError if status is not in accepted_status_codes."""
    response = await proxy_response(raw_response)
    if response.status_code not in accepted_status_codes:
        try:
            error = json.loads(response.body.decode("utf-8"))
        except Exception:
            error = response.body.decode("utf-8", errors="replace")
        raise ValueError(
            f"OpenFGA Client: unexpected status code: {response.status_code}, error: {error}"
        )
    return response


def _split_top_level(expr: str, separator: str) -> List[str]:
    """Splits a DSL relation expression by a keyword separator (e.g., ' or ', '
    and ', ' but not ') only at the top level (outside parentheses and
    brackets)."""
    parts: List[str] = []
    depth_paren = 0
    depth_bracket = 0
    current: List[str] = []
    i = 0
    sep_len = len(separator)
    n = len(expr)

    while i < n:
        ch = expr[i]
        if ch == "(":
            depth_paren += 1
            current.append(ch)
            i += 1
        elif ch == ")":
            depth_paren = max(0, depth_paren - 1)
            current.append(ch)
            i += 1
        elif ch == "[":
            depth_bracket += 1
            current.append(ch)
            i += 1
        elif ch == "]":
            depth_bracket = max(0, depth_bracket - 1)
            current.append(ch)
            i += 1
        elif (
            depth_paren == 0
            and depth_bracket == 0
            and expr[i : i + sep_len] == separator
        ):
            parts.append("".join(current).strip())
            current = []
            i += sep_len
        else:
            current.append(ch)
            i += 1

    parts.append("".join(current).strip())
    return parts


def _parse_direct_type_entry(entry: str) -> Dict[str, Any]:
    """Parses a single direct type restriction item inside `[...]` in OpenFGA
    DSL.

    Examples:
      - `user` -> `{"type": "user"}`
      - `user:*` -> `{"type": "user", "wildcard": {}}`
      - `group#member` -> `{"type": "group", "relation": "member"}`
      - `user with cond1` -> `{"type": "user", "condition": "cond1"}`
      - `group#member with cond1` -> `{"type": "group", "relation": "member", "condition": "cond1"}`
    """
    token = entry.strip()
    condition: Optional[str] = None
    with_match = re.split(r"\s+with\s+", token, maxsplit=1)
    if len(with_match) == 2:
        token, condition = with_match[0].strip(), with_match[1].strip()

    result: Dict[str, Any]
    if token.endswith(":*"):
        result = {"type": token[:-2].strip(), "wildcard": {}}
    elif "#" in token:
        type_part, rel_part = token.split("#", 1)
        result = {"type": type_part.strip(), "relation": rel_part.strip()}
    else:
        result = {"type": token}

    if condition:
        result["condition"] = condition

    return result


def _parse_relation_expr(
    expr: str,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Parses an OpenFGA DSL relation expression into its JSON userset rewrite
    and list of directly_related_user_types."""
    s = expr.strip()

    # Strip enclosing parentheses if they wrap the entire expression
    while s.startswith("(") and s.endswith(")"):
        depth = 0
        wraps_all = True
        for idx, ch in enumerate(s):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and idx < len(s) - 1:
                    wraps_all = False
                    break
        if wraps_all:
            s = s[1:-1].strip()
        else:
            break

    # Precedence in OpenFGA DSL: `or` (lowest), `and`, `but not` (highest binary)
    or_parts = _split_top_level(s, " or ")
    if len(or_parts) > 1:
        children = []
        direct_types: List[Dict[str, Any]] = []
        for part in or_parts:
            child_rewrite, child_types = _parse_relation_expr(part)
            children.append(child_rewrite)
            direct_types.extend(child_types)
        return {"union": {"child": children}}, direct_types

    and_parts = _split_top_level(s, " and ")
    if len(and_parts) > 1:
        children = []
        direct_types = []
        for part in and_parts:
            child_rewrite, child_types = _parse_relation_expr(part)
            children.append(child_rewrite)
            direct_types.extend(child_types)
        return {"intersection": {"child": children}}, direct_types

    but_not_parts = _split_top_level(s, " but not ")
    if len(but_not_parts) > 1:
        if len(but_not_parts) != 2:
            raise ValueError(
                f"Invalid 'but not' relation expression: '{expr}' (expected base 'but not' subtract)"
            )
        base_rewrite, base_types = _parse_relation_expr(but_not_parts[0])
        sub_rewrite, sub_types = _parse_relation_expr(but_not_parts[1])
        return (
            {"difference": {"base": base_rewrite, "subtract": sub_rewrite}},
            base_types + sub_types,
        )

    # Direct type restrictions: `[type1, type2#rel, type3:*]`
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return {"this": {}}, []
        items = [item.strip() for item in inner.split(",") if item.strip()]
        direct_types = [_parse_direct_type_entry(item) for item in items]
        return {"this": {}}, direct_types

    # Tuple-to-userset: `<computed_rel> from <tupleset_rel>`
    from_match = re.match(r"^([A-Za-z0-9_]+)\s+from\s+([A-Za-z0-9_]+)$", s)
    if from_match:
        computed_rel, tupleset_rel = from_match.group(1), from_match.group(2)
        return (
            {
                "tupleToUserset": {
                    "tupleset": {"relation": tupleset_rel},
                    "computedUserset": {"relation": computed_rel},
                }
            },
            [],
        )

    # Computed userset: `<relation_name>`
    if re.match(r"^[A-Za-z0-9_]+$", s):
        return {"computedUserset": {"relation": s}}, []

    raise ValueError(f"Unsupported or invalid OpenFGA relation expression: '{expr}'")


def _parse_condition_param_type(raw_type: str) -> Dict[str, Any]:
    """Converts a condition parameter type (e.g. `string`, `list<string>`,
    `map<string>`) into OpenFGA JSON parameter type schema."""
    t = raw_type.strip().lower()
    generic_match = re.match(r"^(list|map)\s*<\s*([a-z0-9_]+)\s*>$", t)
    if generic_match:
        container_type = _CONDITION_PARAM_TYPE_MAP[generic_match.group(1)]
        elem_type = _CONDITION_PARAM_TYPE_MAP.get(
            generic_match.group(2), "TYPE_NAME_ANY"
        )
        return {
            "type_name": container_type,
            "generic_types": [{"type_name": elem_type}],
        }
    mapped = _CONDITION_PARAM_TYPE_MAP.get(t)
    if not mapped:
        raise ValueError(f"Unknown OpenFGA condition parameter type: '{raw_type}'")
    return {"type_name": mapped}


def parse_fga_dsl(dsl_text: str) -> Dict[str, Any]:
    """Transpiles an OpenFGA `.fga` DSL model or module into the OpenFGA JSON
    authorization model representation."""
    lines = dsl_text.splitlines()
    schema_version = "1.1"
    type_definitions: List[Dict[str, Any]] = []
    conditions: Dict[str, Dict[str, Any]] = {}

    current_type: Optional[Dict[str, Any]] = None
    in_relations = False
    i = 0
    n = len(lines)

    while i < n:
        raw_line = lines[i]
        # Remove inline comments starting with `#` only when preceded by start-of-line or whitespace
        # Note: in `[group#member]`, `#` is NOT preceded by whitespace!
        cleaned_line = re.sub(r"(^|\s)#.*$", "", raw_line).strip()
        if not cleaned_line:
            i += 1
            continue

        if cleaned_line == "model" or cleaned_line.startswith("module "):
            current_type = None
            in_relations = False
            i += 1
            continue

        schema_match = re.match(r"^schema\s+([0-9.]+)$", cleaned_line)
        if schema_match:
            schema_version = schema_match.group(1)
            i += 1
            continue

        # Condition block: `condition <name>(<params>) { ... }`
        cond_match = re.match(
            r"^condition\s+([A-Za-z0-9_]+)\s*\(([^)]*)\)\s*\{(.*)$", cleaned_line
        )
        if cond_match:
            current_type = None
            in_relations = False
            cond_name = cond_match.group(1)
            params_str = cond_match.group(2).strip()
            first_expr_part = cond_match.group(3).strip()

            params_dict: Dict[str, Dict[str, Any]] = {}
            if params_str:
                for param_item in params_str.split(","):
                    param_item = param_item.strip()
                    if not param_item:
                        continue
                    if ":" not in param_item:
                        raise ValueError(
                            f"Invalid condition parameter '{param_item}' in condition '{cond_name}'"
                        )
                    p_name, p_type = param_item.split(":", 1)
                    params_dict[p_name.strip()] = _parse_condition_param_type(p_type)

            expr_Parts: List[str] = []
            if first_expr_part.endswith("}"):
                expr_Parts.append(first_expr_part[:-1].strip())
            else:
                if first_expr_part:
                    expr_Parts.append(first_expr_part)
                i += 1
                while i < n:
                    c_line = re.sub(r"(^|\s)#.*$", "", lines[i]).strip()
                    if c_line.endswith("}"):
                        before_brace = c_line[:-1].strip()
                        if before_brace:
                            expr_Parts.append(before_brace)
                        break
                    elif c_line:
                        expr_Parts.append(c_line)
                    i += 1

            conditions[cond_name] = {
                "name": cond_name,
                "expression": " ".join(p for p in expr_Parts if p).strip(),
                "parameters": params_dict,
            }
            i += 1
            continue

        # Type definition: `type <name>` or `extend type <name>`
        type_match = re.match(r"^(?:extend\s+)?type\s+([A-Za-z0-9_-]+)$", cleaned_line)
        if type_match:
            type_name = type_match.group(1)
            existing = next(
                (td for td in type_definitions if td["type"] == type_name), None
            )
            if existing is not None:
                current_type = existing
            else:
                current_type = {
                    "type": type_name,
                    "relations": {},
                    "metadata": {"relations": {}},
                }
                type_definitions.append(current_type)
            in_relations = False
            i += 1
            continue

        if cleaned_line == "relations":
            if current_type is None:
                raise ValueError("Unexpected 'relations' keyword outside a type block")
            in_relations = True
            i += 1
            continue

        define_match = re.match(
            r"^define\s+([A-Za-z0-9_-]+)\s*:\s*(.+)$", cleaned_line
        )
        if define_match and current_type is not None and in_relations:
            rel_name = define_match.group(1)
            rel_expr = define_match.group(2)
            rewrite, direct_types = _parse_relation_expr(rel_expr)
            current_type["relations"][rel_name] = rewrite
            current_type["metadata"]["relations"][rel_name] = {
                "directly_related_user_types": direct_types
            }
            i += 1
            continue

        raise ValueError(f"Unrecognized OpenFGA DSL line: '{cleaned_line}'")

    # Clean up empty metadata on types without relations
    for td in type_definitions:
        if not td.get("relations"):
            td["relations"] = {}
            td["metadata"] = None

    model: Dict[str, Any] = {
        "schema_version": schema_version,
        "type_definitions": type_definitions,
    }
    if conditions:
        model["conditions"] = conditions
    return model


def parse_openfga_model(
    policy_code: str, policy_id: Optional[str] = None
) -> Dict[str, Any]:
    """Parses an OpenFGA model from JSON, YAML, or `.fga` DSL string into an
    OpenFGA JSON authorization model dictionary."""
    text = textwrap.dedent(policy_code or "").strip()
    if not text:
        raise ValueError("OpenFGA policy content cannot be empty")

    # 1. If it looks like JSON or policy_id ends with .json
    if text.startswith("{") or (policy_id and policy_id.endswith(".json")):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and "type_definitions" in parsed:
                parsed.setdefault("schema_version", "1.1")
                return parsed
            raise ValueError(
                "JSON policy must be an object containing 'type_definitions'"
            )
        except json.JSONDecodeError as e:
            if policy_id and policy_id.endswith(".json"):
                raise ValueError(f"Invalid OpenFGA JSON model: {e}") from e

    # 2. Try YAML (for .yaml / .yml / fga.mod or general YAML model)
    if policy_id and policy_id.endswith((".yaml", ".yml")):
        try:
            parsed_yaml = yaml.safe_load(text)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid OpenFGA YAML model: {e}") from e

        if isinstance(parsed_yaml, dict):
            if "type_definitions" in parsed_yaml:
                parsed_yaml.setdefault("schema_version", "1.1")
                return parsed_yaml
            if "model" in parsed_yaml and isinstance(parsed_yaml["model"], str):
                return parse_fga_dsl(parsed_yaml["model"])
        raise ValueError(
            "YAML policy must contain 'type_definitions' or a 'model' DSL string"
        )

    # 3. If policy_id ends with .fga or text starts with model/module/type/extend
    if (
        (policy_id and policy_id.endswith(".fga"))
        or re.match(r"^(model(?:\s|$)|module\s+|type\s+|extend\s+type\s+)", text)
    ):
        return parse_fga_dsl(text)

    # 4. Fallback: try JSON, then DSL
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "type_definitions" in parsed:
            parsed.setdefault("schema_version", "1.1")
            return parsed
    except Exception:
        pass

    return parse_fga_dsl(text)


def merge_openfga_models(models: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Merges one or more parsed OpenFGA models (keyed by policy_id) into a
    single unified OpenFGA authorization model."""
    if not models:
        return {"schema_version": "1.1", "type_definitions": []}

    # If there is only a single model, return a deep copy of it directly
    if len(models) == 1:
        only_model = copy.deepcopy(next(iter(models.values())))
        only_model.setdefault("schema_version", "1.1")
        return only_model

    schema_version = "1.1"
    merged_types: Dict[str, Dict[str, Any]] = {}
    type_order: List[str] = []
    merged_conditions: Dict[str, Dict[str, Any]] = {}

    for policy_id in sorted(models.keys()):
        model = models[policy_id]
        if model.get("schema_version"):
            schema_version = model["schema_version"]

        for td in model.get("type_definitions", []):
            t_name = td["type"]
            if t_name not in merged_types:
                merged_types[t_name] = copy.deepcopy(td)
                type_order.append(t_name)
            else:
                target = merged_types[t_name]
                if td.get("relations"):
                    target.setdefault("relations", {})
                    target["relations"].update(copy.deepcopy(td["relations"]))
                if td.get("metadata") and td["metadata"].get("relations"):
                    if not target.get("metadata"):
                        target["metadata"] = {"relations": {}}
                    target["metadata"].setdefault("relations", {})
                    target["metadata"]["relations"].update(
                        copy.deepcopy(td["metadata"]["relations"])
                    )

        if model.get("conditions"):
            merged_conditions.update(copy.deepcopy(model["conditions"]))

    result: Dict[str, Any] = {
        "schema_version": schema_version,
        "type_definitions": [merged_types[t] for t in type_order],
    }
    if merged_conditions:
        result["conditions"] = merged_conditions
    return result


def normalize_tuple_key(item: Any) -> Optional[Dict[str, Any]]:
    """Normalizes a tuple entry into an OpenFGA `tuple_key` dict (`{"user":
    ..., "relation": ..., "object": ..., ...}`)."""
    if not isinstance(item, dict):
        return None

    candidate = item.get("key") if isinstance(item.get("key"), dict) else item
    user = candidate.get("user")
    relation = candidate.get("relation")
    obj = candidate.get("object")

    if not (
        isinstance(user, str)
        and user
        and isinstance(relation, str)
        and relation
        and isinstance(obj, str)
        and obj
    ):
        return None

    normalized: Dict[str, Any] = {
        "user": user,
        "relation": relation,
        "object": obj,
    }
    if candidate.get("condition") is not None:
        normalized["condition"] = candidate["condition"]
    return normalized


def _extract_tuple_list(raw_items: Any) -> List[Dict[str, Any]]:
    """Extracts normalized tuple keys from a list or dict wrapper (`{"tuple_keys":
    [...]}` or `[...]`)."""
    if isinstance(raw_items, dict):
        raw_items = (
            raw_items.get("tuple_keys")
            or raw_items.get("tuples")
            or []
        )
    if not isinstance(raw_items, list):
        return []
    result: List[Dict[str, Any]] = []
    for item in raw_items:
        tk = normalize_tuple_key(item)
        if tk is not None:
            result.append(tk)
    return result


def extract_tuples_from_data(
    policy_data: Any, path: str = ""
) -> Tuple[Optional[List[Dict[str, Any]]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Parses input `policy_data` into either:

    - Declarative tuples: `(tuples_list, [], [])`
    - Explicit write/delete mutation: `(None, writes_list, deletes_list)`

    Supports:
    1. Explicit mutations: `{"writes": [...], "deletes": [...]}`
    2. Standard tuple lists: `{"tuples": [...]}` or `{"tuple_keys": [...]}` or `[...]`
    3. Single tuple dict: `{"user": "...", "relation": "...", "object": "..."}`
    4. Hierarchical mapping:
       - `{"document:roadmap": {"viewer": ["user:anne", "user:bob"]}}`
       - `{"document": {"roadmap": {"viewer": ["user:anne"]}}}`
    """
    clean_path = (path or "").strip("/")

    if isinstance(policy_data, list):
        return _extract_tuple_list(policy_data), [], []

    if isinstance(policy_data, dict):
        # 1. Explicit writes/deletes format
        if (
            ("writes" in policy_data or "deletes" in policy_data)
            and "tuples" not in policy_data
            and "tuple_keys" not in policy_data
        ):
            writes = _extract_tuple_list(policy_data.get("writes", []))
            deletes = _extract_tuple_list(policy_data.get("deletes", []))
            return None, writes, deletes

        # 2. Standard {"tuples": [...]} or {"tuple_keys": [...]}
        if "tuples" in policy_data or "tuple_keys" in policy_data:
            raw_list = policy_data.get("tuples")
            if raw_list is None:
                raw_list = policy_data.get("tuple_keys", [])
            return _extract_tuple_list(raw_list), [], []

        # 3. Single tuple dict
        single = normalize_tuple_key(policy_data)
        if single is not None:
            return [single], [], []

        # 4. Hierarchical mapping
        tuples: List[Dict[str, Any]] = []
        # If clean_path specifies an object like `document:roadmap` or `document/roadmap`
        path_obj: Optional[str] = None
        if ":" in clean_path:
            path_obj = clean_path.split("/")[0]
        elif "/" in clean_path:
            parts = [p for p in clean_path.split("/") if p]
            if len(parts) == 2:
                path_obj = f"{parts[0]}:{parts[1]}"

        if path_obj and all(isinstance(v, list) for v in policy_data.values()):
            for rel, users in policy_data.items():
                for u in users:
                    if isinstance(u, str):
                        tuples.append(
                            {"user": u, "relation": str(rel), "object": path_obj}
                        )
            return tuples, [], []

        for key, val in policy_data.items():
            if isinstance(val, list):
                sub_tuples = _extract_tuple_list(val)
                tuples.extend(sub_tuples)
            elif isinstance(val, dict):
                if ":" in key:
                    # key is an object, e.g. "document:roadmap": {"viewer": ["user:anne"]}
                    for rel, users in val.items():
                        if isinstance(users, list):
                            for u in users:
                                if isinstance(u, str):
                                    tuples.append(
                                        {
                                            "user": u,
                                            "relation": str(rel),
                                            "object": key,
                                        }
                                    )
                else:
                    # key may be an object type, e.g. "document": {"roadmap": {"viewer": ["user:anne"]}}
                    for obj_id, rel_map in val.items():
                        if isinstance(rel_map, dict):
                            obj_str = (
                                obj_id if ":" in str(obj_id) else f"{key}:{obj_id}"
                            )
                            for rel, users in rel_map.items():
                                if isinstance(users, list):
                                    for u in users:
                                        if isinstance(u, str):
                                            tuples.append(
                                                {
                                                    "user": u,
                                                    "relation": str(rel),
                                                    "object": obj_str,
                                                }
                                            )
        return tuples, [], []

    raise ValueError(
        f"Unsupported policy_data type for OpenFGA store: {type(policy_data).__name__}"
    )


def tuple_identity(tk: Dict[str, Any]) -> Tuple[str, str, str]:
    """Returns the unique `(user, relation, object)` key of a tuple."""
    return (tk["user"], tk["relation"], tk["object"])


def _tuple_matches_path(tk: Dict[str, Any], path: str) -> bool:
    """Checks whether a tuple key matches a scoped data path."""
    clean = (path or "").strip("/")
    if not clean or clean in (".", "tuples", "tuple_keys", "relations"):
        return True
    obj = tk.get("object", "")
    if obj == clean or obj.startswith(f"{clean}:"):
        return True
    parts = [p for p in clean.split("/") if p]
    if len(parts) == 2 and obj == f"{parts[0]}:{parts[1]}":
        return True
    if len(parts) == 3 and obj == f"{parts[0]}:{parts[1]}" and tk.get("relation") == parts[2]:
        return True
    return False


class OpenFGAClient(LivenessProbeMixin, BasePolicyStoreClient):
    """Communicates with OpenFGA via its REST API using aiohttp."""

    def __init__(
        self,
        server_url: Optional[str] = None,
        store_id: Optional[str] = None,
        store_name: Optional[str] = None,
        authorization_model_id: Optional[str] = None,
        auth_token: Optional[str] = None,
        auth_type: PolicyStoreAuth = PolicyStoreAuth.NONE,
        oauth_client_id: Optional[str] = None,
        oauth_client_secret: Optional[str] = None,
        oauth_server: Optional[str] = None,
        data_updater_enabled: bool = True,
        policy_updater_enabled: bool = True,
        cache_policy_data: bool = False,
        tls_client_cert: Optional[str] = None,
        tls_client_key: Optional[str] = None,
        tls_ca: Optional[str] = None,
    ):
        self._server_url = (
            server_url or opal_client_config.POLICY_STORE_URL
        ).rstrip("/")
        self._store_id: Optional[str] = (
            store_id
            or opal_client_config.POLICY_STORE_OPENFGA_STORE_ID
            or opal_client_config.OPENFGA_STORE_ID
        )
        self._store_name: str = (
            store_name
            or opal_client_config.POLICY_STORE_OPENFGA_STORE_NAME
            or "opal"
        )
        self._authorization_model_id: Optional[str] = (
            authorization_model_id
            or opal_client_config.POLICY_STORE_OPENFGA_AUTHORIZATION_MODEL_ID
            or opal_client_config.OPENFGA_MODEL_ID
        )
        self._policy_version: Optional[str] = None
        self._lock = asyncio.Lock()

        # Maintain raw and parsed policy modules keyed by policy_id
        self._raw_policies: Dict[str, str] = {}
        self._parsed_policies: Dict[str, Dict[str, Any]] = {}

        # Authentication & TLS settings
        self._token = auth_token
        self._auth_type: PolicyStoreAuth = auth_type
        self._oauth_client_id = oauth_client_id
        self._oauth_client_secret = oauth_client_secret
        self._oauth_server = oauth_server
        self._oauth_token_cache: Dict[str, Any] = {"token": None, "expires": 0}
        self._tls_client_cert = tls_client_cert
        self._tls_client_key = tls_client_key
        self._tls_ca = tls_ca
        self._cache_policy_data = cache_policy_data

        if auth_type == PolicyStoreAuth.TOKEN:
            if self._token is None:
                logger.error("POLICY_STORE_AUTH_TOKEN can not be empty")
                raise ValueError("required variables for token auth are not set")

        if auth_type == PolicyStoreAuth.OAUTH:
            is_error = False
            if self._oauth_client_id is None:
                is_error = True
                logger.error("POLICY_STORE_AUTH_OAUTH_CLIENT_ID can not be empty")
            if self._oauth_client_secret is None:
                is_error = True
                logger.error("POLICY_STORE_AUTH_OAUTH_CLIENT_SECRET can not be empty")
            if self._oauth_server is None:
                is_error = True
                logger.error("POLICY_STORE_AUTH_OAUTH_SERVER can not be empty")
            if is_error:
                raise ValueError("required variables for oauth are not set")

        if auth_type == PolicyStoreAuth.TLS:
            is_error = False
            if self._tls_client_cert is None:
                is_error = True
                logger.error("POLICY_STORE_TLS_CLIENT_CERT can not be empty")
            if self._tls_client_key is None:
                is_error = True
                logger.error("POLICY_STORE_TLS_CLIENT_KEY can not be empty")
            if self._tls_ca is None:
                is_error = True
                logger.error("POLICY_STORE_TLS_CA can not be empty")
            if is_error:
                raise ValueError("required variables for tls are not set")

        self._custom_ssl_context = self._get_custom_ssl_context()
        self._ssl_context_kwargs = (
            {"ssl": self._custom_ssl_context}
            if self._custom_ssl_context is not None
            else {}
        )

        self._transaction_state = OpaTransactionLogState(
            data_updater_enabled=data_updater_enabled,
            policy_updater_enabled=policy_updater_enabled,
        )
        self._init_liveness_probe()

    def _get_custom_ssl_context(self) -> Optional[ssl.SSLContext]:
        if not self._tls_ca:
            return None

        ssl_context = ssl.create_default_context(
            purpose=ssl.Purpose.SERVER_AUTH, cafile=self._tls_ca
        )
        if self._tls_client_key and self._tls_client_cert:
            ssl_context.load_cert_chain(
                certfile=self._tls_client_cert, keyfile=self._tls_client_key
            )
        return ssl_context

    @retry(**RETRY_CONFIG)
    async def _get_oauth_token(self) -> Dict[str, Any]:
        logger.info("Retrieving a new OAuth access_token for OpenFGA.")
        basic_auth = aiohttp.BasicAuth(
            self._oauth_client_id, self._oauth_client_secret
        ).encode()
        async with aiohttp.ClientSession(trust_env=True) as session:
            try:
                async with session.post(
                    self._oauth_server,
                    headers={
                        "accept": "application/json",
                        "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
                        "Authorization": basic_auth,
                    },
                    data=urlencode({"grant_type": "client_credentials"}).encode(
                        "utf-8"
                    ),
                    **self._ssl_context_kwargs,
                ) as oauth_response:
                    response = await oauth_response.json()
                    expires_in = response.get("expires_in", 3600)
                    return {
                        "expires": time.time() + expires_in - 10,
                        "token": response["access_token"],
                    }
            except aiohttp.ClientError as e:
                logger.warning(
                    "OAuth server connection error: {err}", err=describe_error(e)
                )
                raise

    async def _get_auth_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"content-type": "application/json"}
        if self._auth_type == PolicyStoreAuth.TOKEN and self._token is not None:
            headers["Authorization"] = f"Bearer {self._token}"
        elif self._auth_type == PolicyStoreAuth.OAUTH:
            if (
                self._oauth_token_cache["token"] is None
                or time.time() > self._oauth_token_cache["expires"]
            ):
                self._oauth_token_cache = await self._get_oauth_token()
            headers["Authorization"] = f"Bearer {self._oauth_token_cache['token']}"
        return headers

    async def _ensure_store_id(self, session: aiohttp.ClientSession) -> str:
        """Returns the configured OpenFGA `store_id`, or looks up / creates a
        store named `self._store_name` via the OpenFGA HTTP API."""
        if self._store_id:
            return self._store_id

        headers = await self._get_auth_headers()
        continuation_token: Optional[str] = None

        while True:
            params: Dict[str, str] = {}
            if continuation_token:
                params["continuation_token"] = continuation_token
            async with session.get(
                f"{self._server_url}/stores",
                headers=headers,
                params=params,
                **self._ssl_context_kwargs,
            ) as list_resp:
                await proxy_openfga_response_unless_invalid(
                    list_resp, accepted_status_codes=[status.HTTP_200_OK]
                )
                body = await list_resp.json()
                for store in body.get("stores", []):
                    if store.get("name") == self._store_name and store.get("id"):
                        self._store_id = store["id"]
                        logger.info(
                            f"Resolved existing OpenFGA store '{self._store_name}' -> {self._store_id}"
                        )
                        return self._store_id
                continuation_token = body.get("continuation_token")
                if not continuation_token:
                    break

        async with session.post(
            f"{self._server_url}/stores",
            data=json.dumps({"name": self._store_name}),
            headers=headers,
            **self._ssl_context_kwargs,
        ) as create_resp:
            await proxy_openfga_response_unless_invalid(
                create_resp,
                accepted_status_codes=[status.HTTP_200_OK, status.HTTP_201_CREATED],
            )
            created = await create_resp.json()
            self._store_id = created["id"]
            logger.info(
                f"Created new OpenFGA store '{self._store_name}' -> {self._store_id}"
            )
            return self._store_id

    async def _write_merged_authorization_model(
        self, session: aiohttp.ClientSession
    ) -> Response:
        """Merges all currently active policy modules and writes the resulting
        authorization model to OpenFGA."""
        store_id = await self._ensure_store_id(session)
        headers = await self._get_auth_headers()
        merged_model = merge_openfga_models(self._parsed_policies)

        async with session.post(
            f"{self._server_url}/stores/{store_id}/authorization-models",
            data=json.dumps(merged_model),
            headers=headers,
            **self._ssl_context_kwargs,
        ) as fga_response:
            response = await proxy_openfga_response_unless_invalid(
                fga_response,
                accepted_status_codes=[
                    status.HTTP_200_OK,
                    status.HTTP_201_CREATED,
                ],
            )
            try:
                payload = json.loads(response.body.decode("utf-8"))
                if isinstance(payload, dict) and payload.get("authorization_model_id"):
                    self._authorization_model_id = payload["authorization_model_id"]
            except Exception:
                pass
            return response

    async def get_policy_version(self) -> Optional[str]:
        return self._policy_version

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def set_policy(
        self,
        policy_id: str,
        policy_code: str,
        transaction_id: Optional[str] = None,
    ) -> Optional[Response]:
        if should_ignore_path(
            policy_id, opal_client_config.POLICY_STORE_POLICY_PATHS_TO_IGNORE
        ):
            logger.info(
                f"Ignoring setting policy - {policy_id}, set in POLICY_STORE_POLICY_PATHS_TO_IGNORE."
            )
            return None

        parsed_model = parse_openfga_model(policy_code, policy_id=policy_id)

        async with self._lock:
            self._raw_policies[policy_id] = policy_code
            self._parsed_policies[policy_id] = parsed_model

            try:
                async with aiohttp.ClientSession(trust_env=True) as session:
                    return await self._write_merged_authorization_model(session)
            except aiohttp.ClientError as e:
                logger.warning(
                    "OpenFGA connection error: {err}", err=describe_error(e)
                )
                raise

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def set_policies(
        self, bundle: PolicyBundle, transaction_id: Optional[str] = None
    ) -> Optional[Response]:
        if bundle.old_hash is not None and bundle.old_hash != self._policy_version:
            logger.warning(
                f"Received a diff bundle with old_hash ({bundle.old_hash}) != current version ({self._policy_version})"
            )

        async with self._lock:
            # 1. Handle deleted policy and data modules in diff bundles
            if bundle.deleted_files is not None:
                for deleted_policy_id in BundleUtils.sorted_policy_modules_to_delete(
                    bundle
                ):
                    str_id = str(deleted_policy_id)
                    if not should_ignore_path(
                        str_id, opal_client_config.POLICY_STORE_POLICY_PATHS_TO_IGNORE
                    ):
                        self._raw_policies.pop(str_id, None)
                        self._parsed_policies.pop(str_id, None)

                for deleted_data_path in BundleUtils.sorted_data_modules_to_delete(
                    bundle
                ):
                    str_path = str(deleted_data_path)
                    if not should_ignore_path(
                        str_path,
                        opal_client_config.POLICY_STORE_POLICY_PATHS_TO_IGNORE,
                    ):
                        await self._delete_policy_data_unlocked(
                            path=str_path, transaction_id=transaction_id
                        )

            # 2. Parse and stage added/modified policy modules
            policy_changed = bool(
                bundle.deleted_files and bundle.deleted_files.policy_modules
            )
            for module in BundleUtils.sorted_policy_modules_to_load(bundle):
                if should_ignore_path(
                    module.path, opal_client_config.POLICY_STORE_POLICY_PATHS_TO_IGNORE
                ):
                    continue
                parsed = parse_openfga_model(module.rego, policy_id=module.path)
                self._raw_policies[module.path] = module.rego
                self._parsed_policies[module.path] = parsed
                policy_changed = True

            response: Optional[Response] = None
            if policy_changed and self._parsed_policies:
                try:
                    async with aiohttp.ClientSession(trust_env=True) as session:
                        response = await self._write_merged_authorization_model(session)
                except aiohttp.ClientError as e:
                    logger.warning(
                        "OpenFGA connection error: {err}", err=describe_error(e)
                    )
                    raise
            elif policy_changed and not self._parsed_policies:
                self._authorization_model_id = None

            # 3. Apply static data modules from the bundle (after model is updated)
            for data_module in BundleUtils.sorted_data_modules_to_load(bundle):
                if should_ignore_path(
                    data_module.path,
                    opal_client_config.POLICY_STORE_POLICY_PATHS_TO_IGNORE,
                ):
                    continue
                try:
                    parsed_data = (
                        json.loads(data_module.data)
                        if isinstance(data_module.data, str)
                        else data_module.data
                    )
                except json.JSONDecodeError as e:
                    logger.warning(
                        "Data module {path} contains non-json data: {err}",
                        path=data_module.path,
                        err=describe_error(e),
                    )
                    continue
                await self._set_policy_data_unlocked(
                    policy_data=parsed_data,
                    path=data_module.path,
                    transaction_id=transaction_id,
                )

            self._policy_version = bundle.hash
            return response

    @retry(**RETRY_CONFIG)
    async def get_policy(self, policy_id: str) -> Optional[str]:
        if policy_id in self._raw_policies:
            return self._raw_policies[policy_id]

        # If not in local cache, fetch the latest model from OpenFGA
        models_dict = await self.get_policies()
        if policy_id in models_dict:
            val = models_dict[policy_id]
            return val if isinstance(val, str) else json.dumps(val)
        return None

    @retry(**RETRY_CONFIG)
    async def get_policy_module_ids(self) -> List[str]:
        if self._raw_policies:
            return list(self._raw_policies.keys())
        if self._authorization_model_id:
            return [self._authorization_model_id]
        return []

    @retry(**RETRY_CONFIG)
    async def get_policies(self) -> Dict[str, Any]:
        """Retrieves the current authorization model(s) from OpenFGA."""
        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                store_id = await self._ensure_store_id(session)
                headers = await self._get_auth_headers()

                if self._authorization_model_id:
                    url = f"{self._server_url}/stores/{store_id}/authorization-models/{self._authorization_model_id}"
                    async with session.get(
                        url, headers=headers, **self._ssl_context_kwargs
                    ) as resp:
                        await proxy_openfga_response_unless_invalid(
                            resp, accepted_status_codes=[status.HTTP_200_OK]
                        )
                        body = await resp.json()
                        model = body.get("authorization_model", body)
                        result: Dict[str, Any] = {
                            self._authorization_model_id: model,
                        }
                        result.update(self._raw_policies)
                        return result

                url = f"{self._server_url}/stores/{store_id}/authorization-models"
                async with session.get(
                    url, headers=headers, **self._ssl_context_kwargs
                ) as resp:
                    await proxy_openfga_response_unless_invalid(
                        resp, accepted_status_codes=[status.HTTP_200_OK]
                    )
                    body = await resp.json()
                    models = body.get("authorization_models", [])
                    result = {
                        m["id"]: m for m in models if isinstance(m, dict) and "id" in m
                    }
                    result.update(self._raw_policies)
                    return result
        except aiohttp.ClientError as e:
            logger.warning("OpenFGA connection error: {err}", err=describe_error(e))
            raise

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def delete_policy(
        self, policy_id: str, transaction_id: Optional[str] = None
    ) -> Optional[Response]:
        if should_ignore_path(
            policy_id, opal_client_config.POLICY_STORE_POLICY_PATHS_TO_IGNORE
        ):
            logger.info(
                f"Ignoring deleting policy - {policy_id}, set in POLICY_STORE_POLICY_PATHS_TO_IGNORE."
            )
            return None

        async with self._lock:
            self._raw_policies.pop(policy_id, None)
            self._parsed_policies.pop(policy_id, None)
            if self._authorization_model_id == policy_id:
                self._authorization_model_id = None

            if not self._parsed_policies:
                self._authorization_model_id = None
                return Response(status_code=status.HTTP_200_OK)

            try:
                async with aiohttp.ClientSession(trust_env=True) as session:
                    return await self._write_merged_authorization_model(session)
            except aiohttp.ClientError as e:
                logger.warning(
                    "OpenFGA connection error: {err}", err=describe_error(e)
                )
                raise

    async def _read_all_tuples(
        self,
        session: aiohttp.ClientSession,
        store_id: str,
        tuple_key_filter: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """Reads all relationship tuples from OpenFGA, handling pagination."""
        headers = await self._get_auth_headers()
        tuples: List[Dict[str, Any]] = []
        continuation_token: Optional[str] = None

        while True:
            payload: Dict[str, Any] = {}
            if tuple_key_filter:
                payload["tuple_key"] = tuple_key_filter
            if continuation_token:
                payload["continuation_token"] = continuation_token

            async with session.post(
                f"{self._server_url}/stores/{store_id}/read",
                data=json.dumps(payload),
                headers=headers,
                **self._ssl_context_kwargs,
            ) as resp:
                await proxy_openfga_response_unless_invalid(
                    resp, accepted_status_codes=[status.HTTP_200_OK]
                )
                body = await resp.json()
                for entry in body.get("tuples", []):
                    tk = normalize_tuple_key(entry)
                    if tk is not None:
                        tuples.append(tk)
                continuation_token = body.get("continuation_token")
                if not continuation_token:
                    break

        return tuples

    async def _write_and_delete_tuples_batched(
        self,
        session: aiohttp.ClientSession,
        store_id: str,
        writes: List[Dict[str, Any]],
        deletes: List[Dict[str, Any]],
    ) -> Response:
        """Executes tuple writes and deletes against OpenFGA's `/write`
        endpoint in batches of at most `MAX_TUPLES_PER_WRITE`."""
        if not writes and not deletes:
            return Response(status_code=status.HTTP_200_OK, content="{}")

        headers = await self._get_auth_headers()
        last_response: Optional[Response] = None

        # Delete batches uses tuple_key without condition
        delete_keys = [
            {"user": tk["user"], "relation": tk["relation"], "object": tk["object"]}
            for tk in deletes
        ]

        # If everything fits into a single transaction, send writes and deletes together
        if len(writes) + len(delete_keys) <= MAX_TUPLES_PER_WRITE:
            payload: Dict[str, Any] = {}
            if writes:
                payload["writes"] = {"tuple_keys": writes}
            if delete_keys:
                payload["deletes"] = {"tuple_keys": delete_keys}
            if self._authorization_model_id:
                payload["authorization_model_id"] = self._authorization_model_id

            async with session.post(
                f"{self._server_url}/stores/{store_id}/write",
                data=json.dumps(payload),
                headers=headers,
                **self._ssl_context_kwargs,
            ) as resp:
                return await proxy_openfga_response_unless_invalid(
                    resp, accepted_status_codes=[status.HTTP_200_OK]
                )

        # Otherwise chunk deletes then writes
        for i in range(0, len(delete_keys), MAX_TUPLES_PER_WRITE):
            chunk = delete_keys[i : i + MAX_TUPLES_PER_WRITE]
            payload = {"deletes": {"tuple_keys": chunk}}
            if self._authorization_model_id:
                payload["authorization_model_id"] = self._authorization_model_id
            async with session.post(
                f"{self._server_url}/stores/{store_id}/write",
                data=json.dumps(payload),
                headers=headers,
                **self._ssl_context_kwargs,
            ) as resp:
                last_response = await proxy_openfga_response_unless_invalid(
                    resp, accepted_status_codes=[status.HTTP_200_OK]
                )

        for i in range(0, len(writes), MAX_TUPLES_PER_WRITE):
            chunk = writes[i : i + MAX_TUPLES_PER_WRITE]
            payload = {"writes": {"tuple_keys": chunk}}
            if self._authorization_model_id:
                payload["authorization_model_id"] = self._authorization_model_id
            async with session.post(
                f"{self._server_url}/stores/{store_id}/write",
                data=json.dumps(payload),
                headers=headers,
                **self._ssl_context_kwargs,
            ) as resp:
                last_response = await proxy_openfga_response_unless_invalid(
                    resp, accepted_status_codes=[status.HTTP_200_OK]
                )

        return last_response or Response(status_code=status.HTTP_200_OK, content="{}")

    async def _set_policy_data_unlocked(
        self,
        policy_data: JsonableValue,
        path: str = "",
        transaction_id: Optional[str] = None,
    ) -> Optional[Response]:
        if policy_data is None:
            return await self._delete_policy_data_unlocked(
                path=path, transaction_id=transaction_id
            )

        if should_ignore_path(
            path, opal_client_config.POLICY_STORE_POLICY_PATHS_TO_IGNORE
        ):
            logger.info(
                f"Ignoring setting policy data at path '{path}', set in POLICY_STORE_POLICY_PATHS_TO_IGNORE."
            )
            return None

        declarative_tuples, explicit_writes, explicit_deletes = (
            extract_tuples_from_data(policy_data, path=path)
        )

        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                store_id = await self._ensure_store_id(session)

                # Explicit writes/deletes payload
                if declarative_tuples is None:
                    return await self._write_and_delete_tuples_batched(
                        session, store_id, explicit_writes, explicit_deletes
                    )

                # Declarative state reconciliation
                existing_all = await self._read_all_tuples(session, store_id)
                existing_in_scope = [
                    tk for tk in existing_all if _tuple_matches_path(tk, path)
                ]

                existing_map = {tuple_identity(tk): tk for tk in existing_in_scope}
                desired_map = {tuple_identity(tk): tk for tk in declarative_tuples}

                to_write = [
                    tk
                    for ident, tk in desired_map.items()
                    if ident not in existing_map
                    or existing_map[ident].get("condition") != tk.get("condition")
                ]
                to_delete = [
                    tk
                    for ident, tk in existing_map.items()
                    if ident not in desired_map
                    or existing_map[ident].get("condition")
                    != desired_map[ident].get("condition")
                ]

                return await self._write_and_delete_tuples_batched(
                    session, store_id, to_write, to_delete
                )
        except aiohttp.ClientError as e:
            logger.warning("OpenFGA connection error: {err}", err=describe_error(e))
            raise

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def set_policy_data(
        self,
        policy_data: JsonableValue,
        path: str = "",
        transaction_id: Optional[str] = None,
    ) -> Optional[Response]:
        async with self._lock:
            return await self._set_policy_data_unlocked(
                policy_data=policy_data, path=path, transaction_id=transaction_id
            )

    async def _delete_policy_data_unlocked(
        self, path: str = "", transaction_id: Optional[str] = None
    ) -> Optional[Response]:
        if should_ignore_path(
            path, opal_client_config.POLICY_STORE_POLICY_PATHS_TO_IGNORE
        ):
            logger.info(
                f"Ignoring deleting policy data at path '{path}', set in POLICY_STORE_POLICY_PATHS_TO_IGNORE."
            )
            return None

        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                store_id = await self._ensure_store_id(session)
                existing_all = await self._read_all_tuples(session, store_id)
                to_delete = [
                    tk for tk in existing_all if _tuple_matches_path(tk, path)
                ]
                return await self._write_and_delete_tuples_batched(
                    session, store_id, [], to_delete
                )
        except aiohttp.ClientError as e:
            logger.warning("OpenFGA connection error: {err}", err=describe_error(e))
            raise

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def delete_policy_data(
        self, path: str = "", transaction_id: Optional[str] = None
    ) -> Optional[Response]:
        async with self._lock:
            return await self._delete_policy_data_unlocked(
                path=path, transaction_id=transaction_id
            )

    @affects_transaction
    @retry(**RETRY_CONFIG)
    async def patch_policy_data(
        self,
        patch_document: List[JSONPatchAction],
        path: str = "",
        transaction_id: Optional[str] = None,
    ) -> Optional[Response]:
        if should_ignore_path(
            path, opal_client_config.POLICY_STORE_POLICY_PATHS_TO_IGNORE
        ):
            logger.info(
                f"Ignoring patching policy data at path '{path}', set in POLICY_STORE_POLICY_PATHS_TO_IGNORE."
            )
            return None

        async with self._lock:
            try:
                async with aiohttp.ClientSession(trust_env=True) as session:
                    store_id = await self._ensure_store_id(session)
                    current_tuples = await self._read_all_tuples(session, store_id)
                    doc: Dict[str, Any] = {"tuples": copy.deepcopy(current_tuples)}

                    raw_actions = exclude_none_fields(patch_document)
                    # Check if patch actions directly supply tuple_keys in `value` (e.g. op="add" / op="remove" with value={"user":...})
                    direct_writes: List[Dict[str, Any]] = []
                    direct_deletes: List[Dict[str, Any]] = []
                    can_apply_directly = True

                    for action in raw_actions:
                        op = action.get("op")
                        val = action.get("value")
                        extracted = (
                            _extract_tuple_list(val)
                            if isinstance(val, (list, dict))
                            else []
                        )
                        single = normalize_tuple_key(val)
                        if single is not None:
                            extracted = [single]

                        if op == "add" and extracted:
                            direct_writes.extend(extracted)
                        elif op == "remove" and extracted:
                            direct_deletes.extend(extracted)
                        else:
                            can_apply_directly = False
                            break

                    if can_apply_directly and (direct_writes or direct_deletes):
                        return await self._write_and_delete_tuples_batched(
                            session, store_id, direct_writes, direct_deletes
                        )

                    # Otherwise apply standard RFC 6902 JSON Patch against `{"tuples": [...]}`
                    adjusted_actions = []
                    prefix = "/" + path.strip("/") if path and path != "/" else ""
                    for action in raw_actions:
                        act = dict(action)
                        act_path = act.get("path", "")
                        if prefix and not act_path.startswith(prefix):
                            act["path"] = (
                                f"{prefix}/{act_path.lstrip('/')}"
                                if act_path
                                else prefix
                            )
                        adjusted_actions.append(act)

                    patch = jsonpatch.JsonPatch(adjusted_actions)
                    patched_doc = patch.apply(doc, in_place=False)
                    new_tuples, _, _ = extract_tuples_from_data(patched_doc)
                    new_tuples = new_tuples or []

                    existing_map = {tuple_identity(tk): tk for tk in current_tuples}
                    desired_map = {tuple_identity(tk): tk for tk in new_tuples}

                    to_write = [
                        tk
                        for ident, tk in desired_map.items()
                        if ident not in existing_map
                        or existing_map[ident].get("condition") != tk.get("condition")
                    ]
                    to_delete = [
                        tk
                        for ident, tk in existing_map.items()
                        if ident not in desired_map
                        or existing_map[ident].get("condition")
                        != desired_map[ident].get("condition")
                    ]

                    return await self._write_and_delete_tuples_batched(
                        session, store_id, to_write, to_delete
                    )
            except aiohttp.ClientError as e:
                logger.warning(
                    "OpenFGA connection error: {err}", err=describe_error(e)
                )
                raise

    @retry(**RETRY_CONFIG)
    async def get_data(self, path: str = "") -> Dict[str, Any]:
        """Reads relationship tuples from OpenFGA, optionally filtered by
        `path`."""
        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                store_id = await self._ensure_store_id(session)
                all_tuples = await self._read_all_tuples(session, store_id)
                filtered = [
                    tk for tk in all_tuples if _tuple_matches_path(tk, path)
                ]
                return {"tuples": filtered}
        except aiohttp.ClientError as e:
            logger.warning("OpenFGA connection error: {err}", err=describe_error(e))
            raise

    @retry(**RETRY_CONFIG)
    async def get_data_with_input(self, path: str, input: BaseModel) -> Response:
        """Evaluates an authorization query against OpenFGA (defaulting to
        `/check`, or `/expand`, `/list-objects`, `/list-users`, `/batch-check`
        if specified in `path`)."""
        if hasattr(input, "model_dump"):
            payload = input.model_dump(mode="json", exclude_none=True)
        elif hasattr(input, "dict"):
            payload = input.dict(exclude_none=True)
        elif isinstance(input, dict):
            payload = dict(input)
        else:
            raise TypeError(f"Unsupported input type: {type(input).__name__}")

        # Support shorthand `{"user": ..., "relation": ..., "object": ...}` by wrapping in `tuple_key`
        if (
            "tuple_key" not in payload
            and "user" in payload
            and "relation" in payload
            and "object" in payload
        ):
            tuple_key = {
                "user": payload.pop("user"),
                "relation": payload.pop("relation"),
                "object": payload.pop("object"),
            }
            payload["tuple_key"] = tuple_key

        if (
            self._authorization_model_id
            and "authorization_model_id" not in payload
        ):
            payload["authorization_model_id"] = self._authorization_model_id

        clean_path = (path or "").strip("/")
        allowed_endpoints = {
            "check",
            "expand",
            "list-objects",
            "list-users",
            "batch-check",
        }
        endpoint = clean_path if clean_path in allowed_endpoints else "check"

        try:
            async with aiohttp.ClientSession(trust_env=True) as session:
                store_id = await self._ensure_store_id(session)
                headers = await self._get_auth_headers()
                async with session.post(
                    f"{self._server_url}/stores/{store_id}/{endpoint}",
                    data=json.dumps(payload),
                    headers=headers,
                    **self._ssl_context_kwargs,
                ) as fga_response:
                    return await proxy_openfga_response_unless_invalid(
                        fga_response,
                        accepted_status_codes=[status.HTTP_200_OK],
                    )
        except aiohttp.ClientError as e:
            logger.warning("OpenFGA connection error: {err}", err=describe_error(e))
            raise

    @retry(**RETRY_CONFIG)
    async def init_healthcheck_policy(self, policy_id: str, policy_code: str):
        logger.debug("OpenFGA store stores transaction state in memory")
        return None

    @retry(**RETRY_CONFIG)
    async def log_transaction(self, transaction: StoreTransaction):
        self._transaction_state.process_transaction(transaction)

    async def is_ready(self) -> bool:
        return self._transaction_state.ready

    async def is_healthy(self) -> bool:
        return self._transaction_state.healthy

    @property
    def _probe_log_label(self) -> str:
        return "OpenFGA"

    async def _probe_engine_reachable(self, session: aiohttp.ClientSession) -> bool:
        """Probes OpenFGA's `/healthz` endpoint via the long-lived session
        owned by `LivenessProbeMixin`."""
        health_url = f"{self._server_url}/healthz"
        async with session.get(health_url, **self._ssl_context_kwargs) as response:
            return 200 <= response.status < 300

    def _set_engine_reachable(self, value: bool) -> None:
        self._transaction_state.set_engine_reachable(value)

    def _get_engine_reachable(self) -> bool:
        return self._transaction_state.engine_reachable

    async def full_export(self, writer: AsyncTextIOWrapper) -> None:
        data = await self.get_data()
        export_payload = {
            "policies": self._raw_policies,
            "data": data,
            "store_id": self._store_id,
            "authorization_model_id": self._authorization_model_id,
        }
        await writer.write(json.dumps(export_payload, default=str))

    async def full_import(self, reader: AsyncTextIOWrapper) -> None:
        import_data = json.loads(await reader.read())
        policies = import_data.get("policies", {})
        for policy_id, policy_code in policies.items():
            await self.set_policy(policy_id=policy_id, policy_code=policy_code)
        if "data" in import_data:
            await self.set_policy_data(import_data["data"])
