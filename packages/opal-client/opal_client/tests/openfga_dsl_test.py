"""Tests for the OpenFGA DSL -> JSON transpiler.

The happy-path cases are the *official* OpenFGA language transformer test
cases, vendored from github.com/openfga/language (Apache-2.0) under
tests/fixtures/openfga_transformer/ - each "<name>.fga" file must transpile
to exactly its "<name>.json" counterpart (semantic equality).
"""

import json
from pathlib import Path

import pytest
from opal_client.policy_store.openfga_dsl import (
    OpenFGADslError,
    merge_models,
    normalize_model,
    strip_extend,
    transpile_fga_to_model,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "openfga_transformer"


def _fixture_names():
    return sorted(path.stem for path in FIXTURES_DIR.glob("*.fga"))


@pytest.mark.parametrize("name", _fixture_names())
def test_transpile_matches_official_transformer(name):
    """Conformance: official .fga files transpile to the official JSON."""
    source = (FIXTURES_DIR / f"{name}.fga").read_text(encoding="utf-8")
    expected = json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))
    actual = strip_extend(transpile_fga_to_model(source))
    assert actual == expected


def test_transpile_empty_document_raises():
    with pytest.raises(OpenFGADslError):
        transpile_fga_to_model("")
    with pytest.raises(OpenFGADslError):
        transpile_fga_to_model("# only a comment\n")


def test_transpile_missing_schema_version_raises():
    with pytest.raises(OpenFGADslError, match="missing schema"):
        transpile_fga_to_model("model\n")


def test_transpile_invalid_schema_version_raises():
    with pytest.raises(OpenFGADslError, match="invalid schema version"):
        transpile_fga_to_model("model\n  schema abc\n")


def test_transpile_unexpected_token_raises():
    with pytest.raises(OpenFGADslError, match="unexpected character"):
        transpile_fga_to_model(
            "model\n  schema 1.1\n\ntype doc\n  relations\n    define viewer: [user @ bad]\n"
        )


def test_transpile_mixed_operators_without_parens_raises():
    source = (
        "model\n  schema 1.1\n\ntype doc\n  relations\n"
        "    define viewer: [user] or [user] and owner\n"
    )
    with pytest.raises(OpenFGADslError, match="without parentheses"):
        transpile_fga_to_model(source)


def test_transpile_direct_assignment_with_condition_and_wildcard():
    source = (
        "model\n  schema 1.1\n\n"
        "type user\n\n"
        "type document\n  relations\n"
        "    define viewer: [user:*, group#member with granted, user]\n\n"
        'condition granted(when: timestamp) {\n  when < timestamp("2099-01-01T00:00:00Z")\n}\n'
    )
    model = transpile_fga_to_model(source)
    document = model["type_definitions"][1]
    related = document["metadata"]["relations"]["viewer"]["directly_related_user_types"]
    assert related == [
        {"type": "user", "wildcard": {}},
        {"type": "group", "relation": "member", "condition": "granted"},
        {"type": "user"},
    ]
    assert model["conditions"]["granted"]["parameters"] == {
        "when": {"type_name": "TYPE_NAME_TIMESTAMP"}
    }


def test_transpile_multiline_define_expression():
    # a define expression wrapped over multiple lines: type-restriction lists
    # may span lines (newlines are allowed inside the brackets)
    source = (
        "model\n  schema 1.1\n\ntype document\n  relations\n"
        "    define viewer: [user,\n      user:*,\n      group#member] or editor\n"
        "    define editor: [user]\n"
    )
    model = transpile_fga_to_model(source)
    document = model["type_definitions"][0]
    viewer = document["relations"]["viewer"]
    assert viewer["union"]["child"][0] == {"this": {}}
    assert viewer["union"]["child"][1] == {"computedUserset": {"relation": "editor"}}
    related = document["metadata"]["relations"]["viewer"]["directly_related_user_types"]
    assert related == [
        {"type": "user"},
        {"type": "user", "wildcard": {}},
        {"type": "group", "relation": "member"},
    ]


def test_transpile_module_header_forces_schema_1_2():
    source = "module core\n\ntype user\n\ntype document\n  relations\n    define viewer: [user]\n"
    model = transpile_fga_to_model(source)
    assert model["schema_version"] == "1.2"


def test_transpile_cel_comment_stripped_from_condition():
    source = (
        "model\n  schema 1.1\n\ntype user\n\n"
        'condition is_old(when: timestamp) {\n  // a comment\n  when < timestamp("2020-01-01T00:00:00Z")\n}\n'
    )
    model = transpile_fga_to_model(source)
    assert (
        model["conditions"]["is_old"]["expression"]
        == 'when < timestamp("2020-01-01T00:00:00Z")'
    )


def test_transpile_condition_missing_brace_raises():
    source = "model\n  schema 1.1\n\ncondition broken(when: timestamp) {\n  when\n"
    with pytest.raises(OpenFGADslError, match="missing closing"):
        transpile_fga_to_model(source)


def test_transpile_condition_unsupported_type_raises():
    source = "model\n  schema 1.1\n\ncondition broken(x: widget) {\n  x == x\n}\n"
    with pytest.raises(OpenFGADslError, match="unsupported condition parameter type"):
        transpile_fga_to_model(source)


def test_normalize_model_accepts_fragment_shapes():
    full = {"schema_version": "1.1", "type_definitions": [{"type": "user"}]}
    assert normalize_model(full) == full
    fragment = {"type_definitions": [{"type": "user"}]}
    assert normalize_model(fragment)["schema_version"] == "1.1"
    bare = [{"type": "user"}]
    assert normalize_model(bare) == full
    with pytest.raises(OpenFGADslError):
        normalize_model("not-a-model")
    with pytest.raises(OpenFGADslError):
        normalize_model({"type_definitions": "nope"})
    with pytest.raises(OpenFGADslError):
        normalize_model([{"no_type": True}])


def test_merge_models_later_definitions_win_and_conditions_merge():
    base = {
        "schema_version": "1.1",
        "type_definitions": [
            {"type": "user", "relations": {}, "metadata": None},
            {
                "type": "document",
                "relations": {"viewer": {"this": {}}},
                "metadata": {
                    "relations": {
                        "viewer": {"directly_related_user_types": [{"type": "user"}]}
                    }
                },
            },
        ],
        "conditions": {"a": {"name": "a", "expression": "x", "parameters": {}}},
    }
    delta = {
        "schema_version": "1.1",
        "type_definitions": [
            {
                "type": "document",
                "relations": {"editor": {"this": {}}},
                "metadata": {
                    "relations": {
                        "editor": {"directly_related_user_types": [{"type": "user"}]}
                    }
                },
            },
            {
                "type": "folder",
                "relations": {},
                "metadata": None,
                "extend": True,
            },
        ],
        "conditions": {"b": {"name": "b", "expression": "y", "parameters": {}}},
    }
    merged = merge_models([base, delta])
    assert merged["schema_version"] == "1.1"
    types = {td["type"]: td for td in merged["type_definitions"]}
    # later full definition replaces the earlier one
    assert set(types["document"]["relations"]) == {"editor"}
    # "extend" marker merges into an existing type and is stripped from output
    assert "extend" not in json.dumps(merged)
    assert merged["conditions"] == {
        "a": {"name": "a", "expression": "x", "parameters": {}},
        "b": {"name": "b", "expression": "y", "parameters": {}},
    }


def test_merge_models_highest_schema_version_wins():
    low = {
        "schema_version": "1.1",
        "type_definitions": [{"type": "user", "relations": {}, "metadata": None}],
    }
    high = {
        "schema_version": "1.2",
        "type_definitions": [{"type": "team", "relations": {}, "metadata": None}],
    }
    assert merge_models([low, high])["schema_version"] == "1.2"
    assert merge_models([high, low])["schema_version"] == "1.2"


# ---------------------------------------------------------------------------
# error branches and less common syntax
# ---------------------------------------------------------------------------


def test_expression_error_branches():
    model_prefix = "model\n  schema 1.1\n\ntype doc\n  relations\n"
    # expression ends right after ':' -> malformed define (nothing after colon)
    with pytest.raises(OpenFGADslError, match="malformed relation definition"):
        transpile_fga_to_model(model_prefix + "    define viewer:\n")
    # empty grouping '()' -> error inside the group
    with pytest.raises(OpenFGADslError, match="relation name"):
        transpile_fga_to_model(model_prefix + "    define viewer: ()\n")
    # an unclosed group never closed before EOF
    with pytest.raises(OpenFGADslError, match="unbalanced brackets"):
        transpile_fga_to_model(model_prefix + "    define viewer: ([user]\n")
    # trailing token after a complete expression
    with pytest.raises(OpenFGADslError, match="trailing token"):
        transpile_fga_to_model(model_prefix + "    define viewer: owner viewer\n")
    # a non-identifier token where a relation name is expected
    with pytest.raises(OpenFGADslError, match="relation name"):
        transpile_fga_to_model(model_prefix + "    define viewer: from x\n")
    # missing closing bracket in a direct assignment (never closed before EOF)
    with pytest.raises(OpenFGADslError, match="unbalanced brackets"):
        transpile_fga_to_model(model_prefix + "    define viewer: [user\n")


def test_expression_parser_defensive_end_of_stream():
    """Direct coverage of the parser's end-of-stream defenses."""
    from opal_client.policy_store.openfga_dsl import _ExpressionParser, _tokenize

    with pytest.raises(OpenFGADslError, match="unexpected end"):
        _ExpressionParser([], line=1)._next()
    with pytest.raises(OpenFGADslError, match="unexpected end"):
        _ExpressionParser([], line=1)._parse_operand()
    with pytest.raises(OpenFGADslError, match="reached end of expression"):
        _ExpressionParser([], line=1)._expect("RBRACKET", "']'")
    with pytest.raises(OpenFGADslError, match="found 'x'"):
        _ExpressionParser(_tokenize("x", 1), line=1)._expect("RBRACKET", "']'")
    with pytest.raises(OpenFGADslError, match="reached end of expression"):
        _ExpressionParser([], line=1)._parse_identifier("relation name")
    with pytest.raises(OpenFGADslError, match="trailing token"):
        _ExpressionParser(_tokenize("owner )", 1), line=1).parse()


def test_header_only_model_and_bad_schema_line():
    with pytest.raises(OpenFGADslError, match="expected 'schema"):
        transpile_fga_to_model("model\n  foo\n")


def test_quoted_identifiers_are_supported():
    source = (
        "model\n  schema 1.1\n\n"
        "type 'my-user'\n\n"
        "type document\n  relations\n    define viewer: ['my-user'] or 'other-rel'\n"
    )
    model = transpile_fga_to_model(source)
    assert model["type_definitions"][0]["type"] == "my-user"
    document = model["type_definitions"][1]
    related = document["metadata"]["relations"]["viewer"]["directly_related_user_types"]
    assert related == [{"type": "my-user"}]
    assert document["relations"]["viewer"]["union"]["child"][1] == {
        "computedUserset": {"relation": "other-rel"}
    }


def test_malformed_define_raises():
    source = "model\n  schema 1.1\n\ntype doc\n  relations\n    define broken [user]\n"
    with pytest.raises(OpenFGADslError, match="malformed relation definition"):
        transpile_fga_to_model(source)


def test_unbalanced_brackets_at_end_of_file_raises():
    source = "model\n  schema 1.1\n\ntype doc\n  relations\n    define viewer: [user,\n"
    with pytest.raises(OpenFGADslError, match="unbalanced brackets"):
        transpile_fga_to_model(source)


def test_condition_error_branches():
    # missing condition name
    with pytest.raises(OpenFGADslError, match="malformed condition header"):
        transpile_fga_to_model(
            "model\n  schema 1.1\n\ncondition (a: string) {\n  a\n}\n"
        )
    # missing parameter list
    with pytest.raises(OpenFGADslError, match="malformed condition parameter list"):
        transpile_fga_to_model("model\n  schema 1.1\n\ncondition broken {\n  a\n}\n")
    # trailing comma in parameters
    with pytest.raises(OpenFGADslError, match="empty condition parameter"):
        transpile_fga_to_model(
            "model\n  schema 1.1\n\ncondition broken(a: string,) {\n  a\n}\n"
        )
    # header does not open a body
    with pytest.raises(OpenFGADslError, match="must open a"):
        transpile_fga_to_model("model\n  schema 1.1\n\ncondition broken(a: string)\n")
    # one-line condition bodies are supported
    model = transpile_fga_to_model(
        "model\n  schema 1.1\n\ncondition one_line(a: string) { a == 'x' }\n"
    )
    assert model["conditions"]["one_line"]["expression"] == "a == 'x'"


def test_relations_block_error_branches():
    # a line inside the relations block that is not a define
    with pytest.raises(OpenFGADslError, match="expected 'define'"):
        transpile_fga_to_model(
            "model\n  schema 1.1\n\ntype doc\n  relations\n    viewer: [user]\n"
        )
    # top-level junk
    with pytest.raises(OpenFGADslError, match="expected 'type' or 'condition'"):
        transpile_fga_to_model("model\n  schema 1.1\n\njunk\n")
    # indented type declaration
    with pytest.raises(OpenFGADslError, match="must not be indented"):
        transpile_fga_to_model("model\n  schema 1.1\n\n  type doc\n")
    # invalid type name
    with pytest.raises(OpenFGADslError, match="invalid type name"):
        transpile_fga_to_model('model\n  schema 1.1\n\ntype "doc"\n')


def test_extend_type_keyword():
    source = (
        "model\n  schema 1.1\n\n"
        "type document\n  relations\n    define viewer: [user]\n\n"
        "extend type document\n  relations\n    define editor: [user]\n"
    )
    model = transpile_fga_to_model(source)
    assert model["type_definitions"][1]["extend"] is True
    merged = merge_models([model])
    document = [td for td in merged["type_definitions"] if td["type"] == "document"][0]
    assert set(document["relations"]) == {"viewer", "editor"}
    # extending an unknown type behaves like a normal definition
    model2 = transpile_fga_to_model(
        "model\n  schema 1.1\n\nextend type folder\n  relations\n    define viewer: [user]\n"
    )
    merged2 = merge_models([model, model2])
    folder = [td for td in merged2["type_definitions"] if td["type"] == "folder"][0]
    assert set(folder["relations"]) == {"viewer"}


def test_extend_type_with_metadata_merge():
    base = {
        "schema_version": "1.1",
        "type_definitions": [
            {
                "type": "document",
                "relations": {"viewer": {"this": {}}},
                "metadata": {
                    "relations": {
                        "viewer": {"directly_related_user_types": [{"type": "user"}]}
                    }
                },
            }
        ],
    }
    extension = transpile_fga_to_model(
        "model\n  schema 1.1\n\nextend type document\n  relations\n    define editor: [user]\n"
    )
    merged = merge_models([base, extension])
    document = [td for td in merged["type_definitions"] if td["type"] == "document"][0]
    assert set(document["relations"]) == {"viewer", "editor"}
    assert set(document["metadata"]["relations"]) == {"viewer", "editor"}


def test_extend_type_without_relations():
    # an "extend" fragment with no relations must not crash the merge
    extension = {
        "schema_version": "1.1",
        "type_definitions": [
            {"type": "document", "relations": {}, "metadata": None, "extend": True}
        ],
    }
    merged = merge_models([extension])
    assert merged["type_definitions"][0]["metadata"] is None

    # extending a type whose existing metadata is None still merges metadata
    base = {
        "schema_version": "1.1",
        "type_definitions": [
            {
                "type": "document",
                "relations": {"viewer": {"this": {}}},
                "metadata": None,
            }
        ],
    }
    extension = transpile_fga_to_model(
        "model\n  schema 1.1\n\nextend type document\n  relations\n    define editor: [user]\n"
    )
    merged = merge_models([base, extension])
    document = [td for td in merged["type_definitions"] if td["type"] == "document"][0]
    assert set(document["relations"]) == {"viewer", "editor"}
    # the base's metadata was null, so only the extension's metadata exists
    assert set(document["metadata"]["relations"]) == {"editor"}


def test_normalize_and_version_edge_cases():
    # a bare single type definition
    normalized = normalize_model({"type": "user", "relations": {}, "metadata": None})
    assert normalized["type_definitions"] == [
        {"type": "user", "relations": {}, "metadata": None}
    ]
    # strip_extend on a model without type_definitions is a no-op
    assert strip_extend({"schema_version": "1.1"}) == {"schema_version": "1.1"}
    # unparseable schema versions fall back to (1, 1) for the comparison
    weird = {
        "schema_version": "1.x",
        "type_definitions": [{"type": "user", "relations": {}, "metadata": None}],
    }
    assert merge_models([weird])["schema_version"] == "1.1"
