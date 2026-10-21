from __future__ import annotations

import pytest

from service_orchestrator.shared.infrastructure.schema_validator import JsonSchemaValidator

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["distanceKm", "weightKg"],
    "properties": {
        "distanceKm": {"type": "number", "minimum": 0},
        "weightKg": {"type": "number", "exclusiveMinimum": 0},
        "startDate": {"type": "string", "format": "date"},
        "contact": {
            "type": "object",
            "required": ["email"],
            "properties": {"email": {"type": "string", "format": "email"}},
        },
        "items": {"type": "array", "items": {"type": "integer"}},
    },
}


def errors_for(instance) -> list[tuple[str, str]]:
    return [(e.path, e.code) for e in JsonSchemaValidator().validate(SCHEMA, instance)]


def test_valid_payload_has_no_errors() -> None:
    assert errors_for({"distanceKm": 0, "weightKg": 0.5, "startDate": "2026-10-21"}) == []


def test_missing_required_fields_point_at_the_field() -> None:
    assert errors_for({}) == [("/distanceKm", "required"), ("/weightKg", "required")]


def test_type_and_constraint_failures_carry_json_pointers() -> None:
    assert errors_for({"distanceKm": "far", "weightKg": 0}) == [
        ("/distanceKm", "type"),
        ("/weightKg", "exclusiveMinimum"),
    ]


def test_nested_and_array_paths() -> None:
    errors = errors_for({"distanceKm": 1, "weightKg": 1, "contact": {}, "items": [1, "x"]})
    assert errors == [("/contact/email", "required"), ("/items/1", "type")]


def test_each_unexpected_field_is_reported() -> None:
    errors = errors_for({"distanceKm": 1, "weightKg": 1, "extra": 1, "more": 2})
    assert errors == [("/extra", "additional_property"), ("/more", "additional_property")]


def test_formats_are_asserted() -> None:
    errors = errors_for({"distanceKm": 1, "weightKg": 1, "startDate": "21/10/2026"})
    assert errors == [("/startDate", "format")]


def test_check_schema_accepts_supported_schema() -> None:
    assert JsonSchemaValidator().check_schema(SCHEMA) == []


@pytest.mark.parametrize(
    ("schema", "path", "code"),
    [
        ({"type": "array"}, "/type", "invalid_root"),
        (
            {"$schema": "http://json-schema.org/draft-07/schema#", "type": "object"},
            "/$schema",
            "unsupported_dialect",
        ),
        (
            {"type": "object", "properties": {"a": {"type": "strng"}}},
            "/properties/a/type",
            "invalid_schema",
        ),
        (
            {"type": "object", "properties": {"a": {"$ref": "https://example.com/s.json"}}},
            "/properties/a/$ref",
            "remote_ref",
        ),
        (
            {"type": "object", "properties": {"a": {"$ref": "#/$defs/missing"}}},
            "/properties/a/$ref",
            "unresolvable_ref",
        ),
        ({"type": "object", "$id": "https://example.com/x"}, "/$id", "unsupported_keyword"),
        (
            {"type": "object", "properties": {"a": {"x-ui": 1}}},
            "/properties/a/x-ui",
            "unsupported_keyword",
        ),
        (
            {"type": "object", "properties": {"a": {"format": "hostname"}}},
            "/properties/a/format",
            "unsupported_format",
        ),
        (
            {"type": "object", "properties": {"a": {"type": "string", "pattern": "^(a+)+$"}}},
            "/properties/a/pattern",
            "unsafe_pattern",
        ),
        (
            {"type": "object", "properties": {"a": {"type": "string", "pattern": "(x)\\1"}}},
            "/properties/a/pattern",
            "unsafe_pattern",
        ),
        (
            {"type": "object", "patternProperties": {"^(\\w*)*$": {}}},
            "/patternProperties/^(\\w*)*$",
            "unsafe_pattern",
        ),
        (
            {"type": "object", "properties": {"a": {"type": "string", "pattern": "a" * 300}}},
            "/properties/a/pattern",
            "pattern_too_long",
        ),
    ],
)
def test_check_schema_rejects_unsupported_features(schema, path, code) -> None:
    errors = JsonSchemaValidator().check_schema(schema)
    assert (path, code) in [(e.path, e.code) for e in errors]


def test_property_named_like_a_keyword_is_not_mistaken_for_one() -> None:
    schema = {"type": "object", "properties": {"pattern": {"type": "string"}, "format": {}}}
    assert JsonSchemaValidator().check_schema(schema) == []


def test_check_schema_bounds_nesting() -> None:
    schema: dict = {"type": "object"}
    node = schema
    for _ in range(40):
        child: dict = {"type": "object"}
        node["properties"] = {"x": child}
        node = child
    errors = JsonSchemaValidator(max_depth=32).check_schema(schema)
    assert "too_deep" in [e.code for e in errors]


def test_remote_refs_are_never_fetched_at_validation_time() -> None:
    schema = {"type": "object", "properties": {"a": {"$ref": "https://example.invalid/s.json"}}}
    with pytest.raises(Exception, match="example.invalid"):
        JsonSchemaValidator().validate(schema, {"a": 1})


def test_forbidden_properties_point_at_the_field() -> None:
    schema = {
        "type": "object",
        "properties": {"legacy": False, "tags": {"prefixItems": [{}, False]}},
    }
    errors = JsonSchemaValidator().validate(schema, {"legacy": 1, "tags": ["a", "b"]})
    assert [(e.path, e.code) for e in errors] == [
        ("/legacy", "not_allowed"),
        ("/tags/1", "not_allowed"),
    ]
