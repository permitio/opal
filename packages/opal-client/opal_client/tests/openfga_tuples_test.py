"""Tests for converting OPAL data updates into OpenFGA relationship tuples."""

import pytest
from opal_client.policy_store.openfga_tuples import (
    TupleConversionError,
    convert_to_tuples,
    filter_tuples_by_object_prefix,
)


def test_convert_tuple_native_dict():
    data = {
        "tuples": [
            {"user": "user:anne", "relation": "viewer", "object": "document:1"},
            {"user": "user:bob", "relation": "viewer", "object": "document:1"},
        ]
    }
    assert convert_to_tuples(data) == data["tuples"]


def test_convert_bare_list_and_single_tuple():
    single = {"user": "user:anne", "relation": "viewer", "object": "document:1"}
    assert convert_to_tuples([single]) == [single]
    assert convert_to_tuples(single) == [single]


def test_convert_nested_object_relation_users():
    data = {
        "document:readme": {"viewer": ["user:anne", "user:bob"]},
        "folder:company": {"owner": ["user:anne"]},
    }
    assert convert_to_tuples(data) == [
        {"user": "user:anne", "relation": "viewer", "object": "document:readme"},
        {"user": "user:bob", "relation": "viewer", "object": "document:readme"},
        {"user": "user:anne", "relation": "owner", "object": "folder:company"},
    ]


def test_convert_nested_with_condition():
    data = {
        "document:readme": {
            "viewer": {
                "user:anne": {
                    "name": "granted",
                    "context": {"grant_expires_at": "2030-01-01"},
                },
                "user:bob": {},
            }
        }
    }
    tuples = convert_to_tuples(data)
    assert tuples == [
        {
            "user": "user:anne",
            "relation": "viewer",
            "object": "document:readme",
            "condition": {
                "name": "granted",
                "context": {"grant_expires_at": "2030-01-01"},
            },
        },
        {"user": "user:bob", "relation": "viewer", "object": "document:readme"},
    ]


def test_convert_nested_with_wildcard_user():
    data = {"folder:public": {"viewer": ["user:*"]}}
    assert convert_to_tuples(data) == [
        {"user": "user:*", "relation": "viewer", "object": "folder:public"}
    ]


def test_convert_dedupes_tuples():
    data = {
        "tuples": [
            {"user": "user:anne", "relation": "viewer", "object": "document:1"},
            {"user": "user:anne", "relation": "viewer", "object": "document:1"},
        ]
    }
    assert len(convert_to_tuples(data)) == 1


def test_convert_native_tuple_with_condition():
    data = {
        "tuples": [
            {
                "user": "user:anne",
                "relation": "viewer",
                "object": "document:1",
                "condition": {"name": "granted", "context": {"expires": "2030-01-01"}},
            }
        ]
    }
    assert convert_to_tuples(data) == data["tuples"]


def test_convert_dedupes_by_condition_context_including_lists():
    data = {
        "tuples": [
            {
                "user": "user:anne",
                "relation": "viewer",
                "object": "document:1",
                "condition": {
                    "name": "granted",
                    "context": {"roles": ["admin", "dev"]},
                },
            },
            {
                "user": "user:anne",
                "relation": "viewer",
                "object": "document:1",
                "condition": {
                    "name": "granted",
                    "context": {"roles": ["admin", "dev"]},
                },
            },
        ]
    }
    assert len(convert_to_tuples(data)) == 1


def test_convert_nested_edge_cases():
    # a relation mapping that is not a dict
    with pytest.raises(TupleConversionError):
        convert_to_tuples({"document:1": ["viewers"]})
    # an empty (or non-string) relation name
    with pytest.raises(TupleConversionError):
        convert_to_tuples({"document:1": {"": ["user:anne"]}})


def test_convert_invalid_payloads_raise():
    with pytest.raises(TupleConversionError):
        convert_to_tuples("a string")
    with pytest.raises(TupleConversionError):
        convert_to_tuples({"no_tuples": True})
    with pytest.raises(TupleConversionError):
        convert_to_tuples([{"user": "user:anne"}])  # missing fields
    with pytest.raises(TupleConversionError):
        convert_to_tuples(
            [{"user": "anne", "relation": "r", "object": "d:1"}]
        )  # bad user form
    with pytest.raises(TupleConversionError):
        convert_to_tuples([{"user": "u:1", "relation": "", "object": "d:1"}])
    with pytest.raises(TupleConversionError):
        convert_to_tuples(
            [{"user": "u:1", "relation": "r", "object": "d:1", "condition": "x"}]
        )
    # conditions must carry a condition name (per the OpenFGA API spec)
    with pytest.raises(TupleConversionError):
        convert_to_tuples(
            [
                {
                    "user": "u:1",
                    "relation": "r",
                    "object": "d:1",
                    "condition": {"context": {}},
                }
            ]
        )
    with pytest.raises(TupleConversionError):
        convert_to_tuples(
            [
                {
                    "user": "u:1",
                    "relation": "r",
                    "object": "d:1",
                    "condition": {"name": "c", "context": "x"},
                }
            ]
        )
    with pytest.raises(TupleConversionError):
        convert_to_tuples({"document:1": {"viewer": {"user:anne": {"context": {}}}}})
    with pytest.raises(TupleConversionError):
        convert_to_tuples({"bad_object_key": {"viewer": ["user:anne"]}})
    with pytest.raises(TupleConversionError):
        convert_to_tuples({"document:1": {"viewer": "not-a-list"}})
    with pytest.raises(TupleConversionError):
        convert_to_tuples({"document:1": {"viewer": {"anne": {}}}})  # bad user form
    with pytest.raises(TupleConversionError):
        convert_to_tuples({"document:1": {"viewer": {"user:anne": "bad-context"}}})


def test_filter_tuples_by_object_prefix():
    tuples = [
        {"user": "user:anne", "relation": "viewer", "object": "document:1"},
        {"user": "user:anne", "relation": "viewer", "object": "document:2"},
        {"user": "user:bob", "relation": "owner", "object": "folder:x"},
    ]
    assert filter_tuples_by_object_prefix(tuples, "") == tuples
    assert filter_tuples_by_object_prefix(tuples, "/document:1") == [tuples[0]]
    assert filter_tuples_by_object_prefix(tuples, "document") == tuples[:2]
    assert filter_tuples_by_object_prefix(tuples, "folder") == [tuples[2]]
    assert filter_tuples_by_object_prefix(tuples, "missing") == []
