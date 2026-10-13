"""OpenFGA authorization-model DSL (".fga") -> JSON transpiler.

OpenFGA authorization models can be authored either in JSON (the format the
OpenFGA API accepts) or in the OpenFGA DSL (the human friendly ".fga" format
used by the FGA CLI and the OpenFGA playground).

OPAL policy repos can store ".fga" (DSL) or ".json" (JSON) model files; this
module converts the DSL flavor into the JSON flavor so the resulting model can
be written to the OpenFGA API (POST /stores/{store_id}/authorization-models).

The conversion follows the official language definition (the ANTLR grammar and
transformer in github.com/openfga/language) and is validated against the
official dsl->json transformer test cases, which are vendored under
opal_client/tests/fixtures/openfga_transformer/.
"""

import re
from typing import Dict, List, Optional, Tuple

# condition parameter types -> OpenFGA protobuf type-name enums
_CONDITION_TYPE_NAMES = {
    "any": "TYPE_NAME_ANY",
    "bool": "TYPE_NAME_BOOL",
    "string": "TYPE_NAME_STRING",
    "int": "TYPE_NAME_INT",
    "uint": "TYPE_NAME_UINT",
    "double": "TYPE_NAME_DOUBLE",
    "duration": "TYPE_NAME_DURATION",
    "timestamp": "TYPE_NAME_TIMESTAMP",
    "ipaddress": "TYPE_NAME_IPADDRESS",
}

# identifiers may contain "/", "." and "-" separators (per the official lexer)
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_./-]*")
_SCHEMA_VERSION_RE = re.compile(r"\d+\.\d+")
_DEFINE_RE = re.compile(r"define\s+([A-Za-z_][A-Za-z0-9_./-]*)\s*:\s*(.+)$")
_CONDITION_RE = re.compile(r"condition\s+([A-Za-z_][A-Za-z0-9_./-]*)")


class OpenFGADslError(ValueError):
    """Raised when an OpenFGA DSL document cannot be parsed or transpiled."""

    def __init__(self, message: str, line: Optional[int] = None):
        if line is not None:
            message = f"line {line}: {message}"
        super().__init__(message)
        self.line = line


# ---------------------------------------------------------------------------
# Tokenizer (used for relation expressions)
# ---------------------------------------------------------------------------

_TOKEN_PATTERNS = [
    # NOTE: keyword patterns use \b so they don't match the prefix of a
    # longer identifier (e.g. 'or' inside 'organization').
    ("BUT_NOT", re.compile(r"but\s+not\b")),
    ("FROM", re.compile(r"from\b")),
    ("WITH", re.compile(r"with\b")),
    ("OR", re.compile(r"or\b")),
    ("AND", re.compile(r"and\b")),
    ("LBRACKET", re.compile(r"\[")),
    ("RBRACKET", re.compile(r"\]")),
    ("LPAREN", re.compile(r"\(")),
    ("RPAREN", re.compile(r"\)")),
    ("COLON", re.compile(r":")),
    ("HASH", re.compile(r"#")),
    ("STAR", re.compile(r"\*")),
    ("COMMA", re.compile(r",")),
    ("QUOTED_IDENT", re.compile(r"'[^']*'")),
    ("IDENT", re.compile(r"[A-Za-z_][A-Za-z0-9_./-]*")),
    ("WS", re.compile(r"[ \t]+")),
]
_TOKEN_RE = re.compile(
    "|".join(f"(?P<{name}>{pattern.pattern})" for name, pattern in _TOKEN_PATTERNS)
)


def _tokenize(text: str, line: Optional[int] = None) -> List[Tuple[str, str]]:
    """Splits a DSL expression into (kind, value) tokens (whitespace dropped)."""
    tokens: List[Tuple[str, str]] = []
    pos = 0
    while pos < len(text):
        match = _TOKEN_RE.match(text, pos)
        if match is None:
            raise OpenFGADslError(
                f"unexpected character {text[pos]!r} in expression", line=line
            )
        kind = match.lastgroup
        if kind != "WS":
            tokens.append((kind, match.group()))
        pos = match.end()
    return tokens


# ---------------------------------------------------------------------------
# Expression parsing
# ---------------------------------------------------------------------------


class _ExpressionParser:
    """Parses one relation expression into an OpenFGA JSON "userset" node.

    Also collects the directly-related-user-types (type restrictions) declared
    by any direct-assignment operand (`[user, group#member, ...]`) found in the
    expression; these feed the type's metadata block.
    """

    def __init__(self, tokens: List[Tuple[str, str]], line: Optional[int] = None):
        self._tokens = tokens
        self._pos = 0
        self._line = line
        self.directly_related_user_types: List[Dict] = []

    # -- token helpers ------------------------------------------------------
    def _peek(self) -> Optional[Tuple[str, str]]:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _next(self) -> Tuple[str, str]:
        token = self._peek()
        if token is None:
            raise OpenFGADslError("unexpected end of expression", line=self._line)
        self._pos += 1
        return token

    def _expect(self, kind: str, description: str) -> str:
        token = self._peek()
        if token is None:
            raise OpenFGADslError(
                f"expected {description} but reached end of expression", line=self._line
            )
        if token[0] != kind:
            raise OpenFGADslError(
                f"expected {description} but found {token[1]!r}", line=self._line
            )
        self._pos += 1
        return token[1]

    # -- grammar -------------------------------------------------------------
    def parse(self) -> Dict:
        node = self._parse_expression()
        if self._peek() is not None:
            raise OpenFGADslError(
                f"unexpected trailing token {self._peek()[1]!r} in expression",
                line=self._line,
            )
        return node

    def _parse_expression(self) -> Dict:
        first = self._parse_operand()

        token = self._peek()
        if token is None or token[0] not in ("OR", "AND", "BUT_NOT"):
            return first

        # every operator at the same nesting level must match; mixing
        # operators requires explicit parentheses (mirrors the official
        # grammar's relationDefPartials rule).
        operator = token[0]
        self._next()
        operands = [first]
        while True:
            if operator == "BUT_NOT":
                # 'but not' takes exactly one right-hand operand
                operands.append(self._parse_operand())
                break
            operands.append(self._parse_operand())
            token = self._peek()
            if token is None or token[0] != operator:
                break
            self._next()

        token = self._peek()
        if token is not None and token[0] in ("OR", "AND", "BUT_NOT"):
            raise OpenFGADslError(
                "cannot mix 'or', 'and' and 'but not' without parentheses",
                line=self._line,
            )

        if operator == "OR":
            return {"union": {"child": operands}}
        if operator == "AND":
            return {"intersection": {"child": operands}}
        # exclusion ("but not") maps to the Zanzibar "difference" node
        return {"difference": {"base": operands[0], "subtract": operands[1]}}

    def _parse_operand(self) -> Dict:
        token = self._peek()
        if token is None:
            raise OpenFGADslError("unexpected end of expression", line=self._line)

        if token[0] == "LPAREN":
            self._next()
            node = self._parse_expression()
            self._expect("RPAREN", "')'")
            return node

        if token[0] == "LBRACKET":
            return self._parse_direct_assignment()

        # relation reference: <name> [from <tupleset>]
        name = self._parse_identifier("relation name")
        token = self._peek()
        if token is not None and token[0] == "FROM":
            self._next()
            tupleset = self._parse_identifier("tupleset relation name")
            return {
                "tupleToUserset": {
                    "tupleset": {"relation": tupleset},
                    "computedUserset": {"relation": name},
                }
            }
        return {"computedUserset": {"relation": name}}

    def _parse_identifier(self, description: str) -> str:
        token = self._peek()
        if token is None:
            raise OpenFGADslError(
                f"expected {description} but reached end of expression", line=self._line
            )
        if token[0] == "IDENT":
            self._next()
            return token[1]
        if token[0] == "QUOTED_IDENT":
            self._next()
            return token[1][1:-1]
        raise OpenFGADslError(
            f"expected {description} but found {token[1]!r}", line=self._line
        )

    def _parse_direct_assignment(self) -> Dict:
        self._expect("LBRACKET", "'['")
        restrictions: List[Dict] = []
        token = self._peek()
        if token is not None and token[0] != "RBRACKET":
            while True:
                restrictions.append(self._parse_type_restriction())
                token = self._peek()
                if token is not None and token[0] == "COMMA":
                    self._next()
                    continue
                break
        self._expect("RBRACKET", "']'")
        self.directly_related_user_types.extend(restrictions)
        return {"this": {}}

    def _parse_type_restriction(self) -> Dict:
        type_name = self._parse_identifier("type name")
        restriction: Dict = {"type": type_name}

        token = self._peek()
        if token is not None and token[0] == "COLON":
            # public (wildcard) restriction: user:*
            self._next()
            self._expect("STAR", "'*' (wildcard)")
            restriction["wildcard"] = {}
        elif token is not None and token[0] == "HASH":
            self._next()
            restriction["relation"] = self._parse_identifier("relation name")

        token = self._peek()
        if token is not None and token[0] == "WITH":
            self._next()
            restriction["condition"] = self._parse_identifier("condition name")
        return restriction


# ---------------------------------------------------------------------------
# Document parsing (line oriented, leading indentation is significant)
# ---------------------------------------------------------------------------


def _strip_hash_comment(line: str) -> str:
    """Removes '#' comments.

    In the DSL, '#' starts a comment only when it *begins* a line's content
    (the grammar's multiLineComment rule) - a '#' inside an expression is the
    relation-restriction separator (e.g. `group#member`) and must be kept.
    """
    stripped = line.lstrip()
    if stripped.startswith("#"):
        return line[: line.find("#")]
    return line


def _iter_significant_lines(source: str) -> List[Tuple[int, str]]:
    """Collects (line_number, rstripped) for non-empty, non-comment lines.

    Leading indentation is preserved (the DSL is indentation sensitive).
    """
    result = []
    for number, raw in enumerate(source.splitlines(), start=1):
        line = _strip_hash_comment(raw).rstrip()
        if line.strip():
            result.append((number, line))
    return result


def _indentation(line: str) -> int:
    return len(line) - len(line.lstrip())


def _open_depth(text: str) -> int:
    """Counts unbalanced brackets/parentheses in a line (quote aware)."""
    depth = 0
    in_quotes = False
    for char in text:
        if char == "'":
            in_quotes = not in_quotes
        elif not in_quotes:
            if char in "([":
                depth += 1
            elif char in ")]":
                depth -= 1
    return depth


def _parse_define(line_number: int, text: str) -> Tuple[str, Dict, List[Dict]]:
    """Parses a single 'define <name>: <expression>' entry.

    Returns (relation_name, userset_node, directly_related_user_types).
    """
    match = _DEFINE_RE.match(text)
    if match is None:
        raise OpenFGADslError(
            f"malformed relation definition {text!r}", line=line_number
        )
    name, expression = match.group(1), match.group(2).strip()
    parser = _ExpressionParser(_tokenize(expression, line_number), line_number)
    node = parser.parse()
    return name, node, parser.directly_related_user_types


def _join_continuation_lines(
    lines: List[Tuple[int, str]], index: int
) -> Tuple[Tuple[int, str], int]:
    """Joins bracket continuation lines into one logical 'define' expression.

    A define expression continues while brackets/parentheses remain open.
    Returns ((first_line_number, expression), next_index).
    """
    number, expression = lines[index][0], lines[index][1].strip()
    index += 1
    while _open_depth(expression) > 0 and index < len(lines):
        continuation = lines[index][1].strip()
        index += 1
        expression = f"{expression} {continuation}".strip()
    if _open_depth(expression) > 0:
        raise OpenFGADslError("unbalanced brackets in expression", line=number)
    return (number, expression), index


def _strip_cel_comment(line: str) -> str:
    """Removes CEL '//' comments (only when '//' is outside string literals)."""
    in_string = False
    index = 0
    while index < len(line) - 1:
        char = line[index]
        if char == '"':
            in_string = not in_string
        elif not in_string and char == "/" and line[index + 1] == "/":
            return line[:index]
        index += 1
    return line


def _parse_condition_header(
    header: str, line_number: int
) -> Tuple[str, List[Tuple[str, str]]]:
    match = _CONDITION_RE.match(header)
    if match is None:
        raise OpenFGADslError("malformed condition header", line=line_number)
    name = match.group(1)
    open_index = header.find("(")
    close_index = header.rfind(")")
    if open_index == -1 or close_index < open_index:
        raise OpenFGADslError("malformed condition parameter list", line=line_number)
    params_text = header[open_index + 1 : close_index].strip()
    params: List[Tuple[str, str]] = []
    if params_text:
        for param in params_text.split(","):
            param = param.strip()
            if not param:
                raise OpenFGADslError(
                    "empty condition parameter (trailing comma?)", line=line_number
                )
            param_name, _, param_type = param.partition(":")
            params.append((param_name.strip(), param_type.strip()))
    return name, params


def _condition_parameter_type(type_text: str, line_number: int) -> Dict:
    type_text = type_text.strip()
    container: Optional[str] = None
    if type_text.startswith("list<") and type_text.endswith(">"):
        container, type_text = "TYPE_NAME_LIST", type_text[len("list<") : -1]
    elif type_text.startswith("map<") and type_text.endswith(">"):
        container, type_text = "TYPE_NAME_MAP", type_text[len("map<") : -1]
    type_name = _CONDITION_TYPE_NAMES.get(type_text)
    if type_name is None:
        raise OpenFGADslError(
            f"unsupported condition parameter type {type_text!r}", line=line_number
        )
    if container is None:
        return {"type_name": type_name}
    return {"type_name": container, "generic_types": [{"type_name": type_name}]}


class _ModelBuilder:
    """Accumulates the parts of a transpiled model."""

    def __init__(self):
        self.schema_version: Optional[str] = None
        self.module_name: Optional[str] = None
        self.type_definitions: List[Dict] = []
        self.conditions: Dict[str, Dict] = {}
        self.extended_types: List[str] = []

    def result(self) -> Dict:
        model: Dict = {
            "schema_version": self.schema_version or "1.1",
            "type_definitions": self.type_definitions,
        }
        if self.conditions:
            model["conditions"] = self.conditions
        if not self.type_definitions:
            # a header-only model (e.g. "model\n  schema 1.1") has no types;
            # the official transformer omits the (empty) type_definitions key
            del model["type_definitions"]
        return model


def _parse_condition_block(
    lines: List[Tuple[int, str]], index: int, builder: _ModelBuilder
) -> int:
    """Parses one 'condition name(params) { ... }' block; returns next index."""
    number, header = lines[index]
    header = header.strip()
    name, params = _parse_condition_header(header, number)

    if "{" not in header:
        raise OpenFGADslError("condition header must open a '{' body", line=number)
    body: List[str] = []
    depth = header.count("{") - header.count("}")
    remainder = header[header.find("{") + 1 :]
    if "}" in remainder:
        remainder = remainder[: remainder.rfind("}")]
    if remainder.strip():
        body.append(remainder.strip())
    index += 1
    while index < len(lines) and depth > 0:
        line_number, line = lines[index]
        stripped = _strip_cel_comment(line.strip())
        depth += stripped.count("{") - stripped.count("}")
        index += 1
        if depth <= 0:
            # remove the trailing closing brace from the last body line
            stripped = stripped[: stripped.rfind("}")].strip()
        if stripped:
            body.append(stripped)
    if depth > 0:
        raise OpenFGADslError(
            f"condition {name!r} is missing closing '}}'", line=number
        )

    builder.conditions[name] = {
        "name": name,
        "expression": "\n".join(body).strip(),
        "parameters": {
            param_name: _condition_parameter_type(param_type, number)
            for param_name, param_type in params
        },
    }
    return index


def _parse_relations_block(
    lines: List[Tuple[int, str]], index: int, type_indent: int
) -> Tuple[Dict[str, Dict], Dict[str, Dict], int]:
    """Parses the indented 'relations' block of a type definition.

    Returns (relations, metadata, next_index).
    """
    relations: Dict[str, Dict] = {}
    metadata: Dict[str, Dict] = {}
    while index < len(lines):
        entry_number, entry_line = lines[index]
        entry_indent = _indentation(entry_line)
        stripped = entry_line.strip()
        if entry_indent <= type_indent:
            break  # dedented: the relations block is over
        if stripped.startswith("define"):
            (expr_number, expression), index = _join_continuation_lines(lines, index)
            name, node, related = _parse_define(expr_number, expression)
            relations[name] = node
            metadata[name] = {"directly_related_user_types": related}
        else:
            raise OpenFGADslError(
                f"expected 'define' but found {stripped.split()[0]!r}",
                line=entry_number,
            )
    return relations, metadata, index


def transpile_fga_to_model(source: str) -> Dict:
    """Transpiles an OpenFGA DSL (".fga") document into an OpenFGA JSON model.

    Args:
        source: the contents of a .fga file.

    Returns:
        A dict shaped like the OpenFGA API's WriteAuthorizationModel body:
        {"schema_version": str, "type_definitions": [...], "conditions": {...}?}.
        Type definitions that use the DSL's "extend type" keyword carry an
        internal "extend": True marker (removed by `merge_models`/`strip_extend`).

    Raises:
        OpenFGADslError: when the document is not valid OpenFGA DSL.
    """
    lines = _iter_significant_lines(source)
    builder = _ModelBuilder()

    if not lines:
        raise OpenFGADslError("empty OpenFGA model")

    # ---- header -------------------------------------------------------------
    index = 0
    number, line = lines[index]
    stripped = line.strip()
    if stripped == "model":
        index += 1
        if index >= len(lines):
            raise OpenFGADslError("missing schema version after 'model'", line=number)
        schema_number, schema_line = lines[index]
        match = re.match(r"schema\s+(\S+)$", schema_line.strip())
        if match is None:
            raise OpenFGADslError(
                "expected 'schema <version>' after 'model'", line=schema_number
            )
        version = match.group(1)
        if _SCHEMA_VERSION_RE.fullmatch(version) is None:
            raise OpenFGADslError(
                f"invalid schema version {version!r}", line=schema_number
            )
        builder.schema_version = version
        index += 1
    elif stripped.startswith("module "):
        builder.module_name = stripped[len("module ") :].strip()
        # the "module" keyword only exists in schema 1.2
        builder.schema_version = "1.2"
        index += 1

    # ---- type definitions and conditions -------------------------------------
    while index < len(lines):
        number, line = lines[index]
        stripped = line.strip()
        indent = _indentation(line)

        if stripped.startswith("condition "):
            index = _parse_condition_block(lines, index, builder)
            continue

        is_extend = False
        if stripped.startswith("extend "):
            is_extend = True
            stripped = stripped[len("extend ") :].strip()

        if not stripped.startswith("type "):
            raise OpenFGADslError(
                f"expected 'type' or 'condition' but found {stripped.split()[0]!r}",
                line=number,
            )
        if indent != 0:
            raise OpenFGADslError(
                "'type' declarations must not be indented", line=number
            )

        type_name = _quoted_or_plain(stripped[len("type ") :].strip())
        if type_name is None:
            raise OpenFGADslError(f"invalid type name", line=number)
        index += 1

        relations: Dict[str, Dict] = {}
        metadata: Dict[str, Dict] = {}
        # optional indented relations block
        if index < len(lines):
            peek_indent = _indentation(lines[index][1])
            if lines[index][1].strip() == "relations" and peek_indent > indent:
                index += 1
                relations, metadata, index = _parse_relations_block(
                    lines, index, peek_indent
                )

        type_definition: Dict = {"type": type_name}
        if relations:
            type_definition["relations"] = relations
            type_definition["metadata"] = {
                "relations": {
                    name: {
                        "directly_related_user_types": entry[
                            "directly_related_user_types"
                        ]
                    }
                    for name, entry in metadata.items()
                }
            }
        else:
            # matches the official transformer: empty type -> relations {} + metadata null
            type_definition["relations"] = {}
            type_definition["metadata"] = None

        if is_extend:
            type_definition["extend"] = True
            builder.extended_types.append(type_name)

        builder.type_definitions.append(type_definition)

    return builder.result()


def _quoted_or_plain(text: str) -> Optional[str]:
    if len(text) >= 2 and text.startswith("'") and text.endswith("'"):
        return text[1:-1]
    if _IDENT_RE.fullmatch(text):
        return text
    return None


def strip_extend(model: Dict) -> Dict:
    """Removes the internal 'extend' markers from a transpiled/merged model."""
    cleaned = dict(model)
    if "type_definitions" in cleaned:
        cleaned["type_definitions"] = [
            {k: v for k, v in type_definition.items() if k != "extend"}
            for type_definition in cleaned["type_definitions"]
        ]
    return cleaned


def normalize_model(model: Dict) -> Dict:
    """Normalizes a parsed JSON model (or fragment) into a canonical shape.

    Accepts a full model ({"schema_version", "type_definitions", ...}), a bare
    {"type_definitions": [...]} object, or a bare list of type definitions.
    Internal "extend" markers are preserved for `merge_models`.
    """
    if isinstance(model, list):
        model = {"type_definitions": model}
    if not isinstance(model, dict):
        raise OpenFGADslError(
            "model must be a JSON object or a list of type definitions"
        )
    if "type_definitions" in model:
        type_definitions = model["type_definitions"]
    else:
        type_definitions = [model]
    if not isinstance(type_definitions, list):
        raise OpenFGADslError("'type_definitions' must be a list")
    cleaned: List[Dict] = []
    for type_definition in type_definitions:
        if not isinstance(type_definition, dict) or "type" not in type_definition:
            raise OpenFGADslError(
                "each type definition must be an object with a 'type'"
            )
        cleaned.append(type_definition)
    result: Dict = {"schema_version": model.get("schema_version", "1.1")}
    result["type_definitions"] = cleaned
    if model.get("conditions"):
        result["conditions"] = model["conditions"]
    return result


def _version_tuple(version: str) -> Tuple[int, ...]:
    try:
        return tuple(int(part) for part in version.split("."))
    except (ValueError, AttributeError):
        return (1, 1)


def merge_models(models: List[Dict]) -> Dict:
    """Merges several normalized models into a single OpenFGA model.

    Type definitions are merged by type name (later entries win, unless the
    later entry is marked "extend", in which case its relations are merged
    into the earlier definition). Conditions are merged by name. The highest
    declared schema version wins (1.2 > 1.1). The result contains no internal
    "extend" markers, i.e. it is directly writable to the OpenFGA API.
    """
    merged_types: Dict[str, Dict] = {}
    merged_conditions: Dict[str, Dict] = {}
    schema_version = "1.1"

    for model in models:
        model = normalize_model(model)
        if _version_tuple(model["schema_version"]) > _version_tuple(schema_version):
            schema_version = model["schema_version"]

        for type_definition in model["type_definitions"]:
            name = type_definition["type"]
            extend = type_definition.get("extend", False)
            if extend:
                type_definition = {
                    k: v for k, v in type_definition.items() if k != "extend"
                }
            existing = merged_types.get(name)
            if existing is None or not extend:
                merged_types[name] = dict(type_definition)
                continue
            # extend: merge relations/metadata into the existing definition
            new_relations = type_definition.get("relations") or {}
            existing.setdefault("relations", {}).update(new_relations)
            new_metadata = (type_definition.get("metadata") or {}).get(
                "relations"
            ) or {}
            if new_metadata:
                existing_relations_metadata = existing.setdefault(
                    "metadata", {"relations": {}}
                )
                if existing_relations_metadata is None:
                    existing_relations_metadata = existing["metadata"] = {
                        "relations": {}
                    }
                existing_relations_metadata.setdefault("relations", {}).update(
                    new_metadata
                )

        for condition_name, condition in (model.get("conditions") or {}).items():
            merged_conditions[condition_name] = condition

    result: Dict = {
        "schema_version": schema_version,
        "type_definitions": list(merged_types.values()),
    }
    if merged_conditions:
        result["conditions"] = merged_conditions
    return result
