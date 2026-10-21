from __future__ import annotations

import re
from collections.abc import Mapping
from re import _constants as _sre
from re import _parser as _sre_parse
from typing import Any, Final

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError
from jsonschema_specifications import REGISTRY as SPECIFICATIONS
from referencing import Registry

from service_orchestrator.shared.domain.validation import (
    FieldError,
    escape_token,
    from_pointer,
    to_pointer,
)

DIALECT: Final = "https://json-schema.org/draft/2020-12/schema"
ALLOWED_FORMATS: Final = frozenset({"date", "date-time", "time", "email", "uuid"})

_SUBSCHEMA: Final = frozenset(
    {
        "items",
        "additionalProperties",
        "not",
        "if",
        "then",
        "else",
        "contains",
        "propertyNames",
        "unevaluatedProperties",
        "unevaluatedItems",
    }
)
_SUBSCHEMA_LIST: Final = frozenset({"allOf", "anyOf", "oneOf", "prefixItems"})
_SUBSCHEMA_MAP: Final = frozenset({"properties", "patternProperties", "$defs", "dependentSchemas"})
_VALUE: Final = frozenset(
    {
        "$schema",
        "$ref",
        "$comment",
        "title",
        "description",
        "default",
        "examples",
        "deprecated",
        "readOnly",
        "writeOnly",
        "type",
        "enum",
        "const",
        "required",
        "dependentRequired",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minContains",
        "maxContains",
        "minProperties",
        "maxProperties",
        "minLength",
        "maxLength",
        "pattern",
        "format",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
    }
)
ALLOWED_KEYWORDS: Final = _SUBSCHEMA | _SUBSCHEMA_LIST | _SUBSCHEMA_MAP | _VALUE

_NO_REMOTE_REFS: Final = Registry()


class JsonSchemaValidator:
    def __init__(
        self,
        *,
        max_depth: int = 32,
        max_nodes: int = 2_000,
        max_pattern_length: int = 256,
        max_errors: int = 100,
    ) -> None:
        self._max_depth = max_depth
        self._max_nodes = max_nodes
        self._max_pattern_length = max_pattern_length
        self._max_errors = max_errors
        self._format_checker = FormatChecker(formats=ALLOWED_FORMATS)
        self._meta_validator = Draft202012Validator(
            Draft202012Validator.META_SCHEMA,
            registry=SPECIFICATIONS,
            format_checker=FormatChecker(formats=["regex"]),
        )

    def validate(self, schema: Mapping[str, Any], instance: Any) -> list[FieldError]:
        validator = Draft202012Validator(
            _without_false_subschemas(schema),
            registry=_NO_REMOTE_REFS,
            format_checker=self._format_checker,
        )
        errors = [
            field_error
            for error in validator.iter_errors(instance)
            for field_error in _to_field_errors(error)
        ]
        errors.sort(key=lambda e: (e.path, e.code))
        return errors[: self._max_errors]

    def check_schema(self, schema: Any) -> list[FieldError]:
        if not isinstance(schema, dict):
            return [FieldError("", "invalid_schema", "dataSchema must be a JSON object")]

        errors: list[FieldError] = []
        if schema.get("$schema", DIALECT) != DIALECT:
            errors.append(
                FieldError("/$schema", "unsupported_dialect", f"Only {DIALECT} is supported")
            )
        if schema.get("type") != "object":
            errors.append(
                FieldError(
                    "/type", "invalid_root", "dataSchema must describe an object ('type': 'object')"
                )
            )
        errors.extend(
            FieldError(to_pointer(error.absolute_path), "invalid_schema", error.message)
            for error in self._meta_validator.iter_errors(schema)
        )
        if not errors:
            errors.extend(self._check_restrictions(schema))
        errors.sort(key=lambda e: (e.path, e.code))
        return errors[: self._max_errors]

    def _check_restrictions(self, root: dict[str, Any]) -> list[FieldError]:
        errors: list[FieldError] = []
        stack: list[tuple[Any, str, int]] = [(root, "", 1)]
        nodes = 0
        while stack:
            node, path, depth = stack.pop()
            nodes += 1
            if nodes > self._max_nodes:
                errors.append(
                    FieldError(
                        "", "too_complex", f"Schema has more than {self._max_nodes} subschemas"
                    )
                )
                break
            if depth > self._max_depth:
                errors.append(
                    FieldError(path, "too_deep", f"Schema nesting exceeds {self._max_depth}")
                )
                continue
            if not isinstance(node, dict):
                continue
            for key, value in node.items():
                key_path = f"{path}/{escape_token(key)}"
                if key not in ALLOWED_KEYWORDS:
                    errors.append(
                        FieldError(
                            key_path, "unsupported_keyword", f"Keyword {key!r} is not supported"
                        )
                    )
                elif key == "$ref":
                    errors.extend(_check_ref(root, value, key_path))
                elif key == "format" and value not in ALLOWED_FORMATS:
                    allowed = ", ".join(sorted(ALLOWED_FORMATS))
                    errors.append(
                        FieldError(key_path, "unsupported_format", f"Supported formats: {allowed}")
                    )
                elif key == "pattern":
                    errors.extend(self._check_pattern(value, key_path))
                elif key in _SUBSCHEMA:
                    stack.append((value, key_path, depth + 1))
                elif key in _SUBSCHEMA_LIST:
                    stack.extend((sub, f"{key_path}/{i}", depth + 1) for i, sub in enumerate(value))
                elif key in _SUBSCHEMA_MAP:
                    for name, sub in value.items():
                        sub_path = f"{key_path}/{escape_token(name)}"
                        if key == "patternProperties":
                            errors.extend(self._check_pattern(name, sub_path))
                        stack.append((sub, sub_path, depth + 1))
        return errors

    def _check_pattern(self, pattern: str, path: str) -> list[FieldError]:
        if len(pattern) > self._max_pattern_length:
            return [
                FieldError(
                    path,
                    "pattern_too_long",
                    f"Patterns are limited to {self._max_pattern_length} characters",
                )
            ]
        try:
            parsed = _sre_parse.parse(pattern)
        except re.error as exc:
            return [FieldError(path, "invalid_pattern", f"Invalid regular expression: {exc}")]
        problem = _backtracking_risk(parsed, inside_unbounded=False)
        return [FieldError(path, "unsafe_pattern", problem)] if problem else []


def _check_ref(root: dict[str, Any], ref: Any, path: str) -> list[FieldError]:
    if not isinstance(ref, str) or not (ref == "#" or ref.startswith("#/")):
        return [
            FieldError(
                path, "remote_ref", "Only local references such as '#/$defs/name' are allowed"
            )
        ]
    target: Any = root
    try:
        for token in from_pointer(ref[1:]):
            target = target[int(token)] if isinstance(target, list) else target[token]
    except (KeyError, IndexError, ValueError, TypeError):
        return [FieldError(path, "unresolvable_ref", f"Reference {ref!r} does not resolve")]
    return []


def _backtracking_risk(subpattern: Any, *, inside_unbounded: bool) -> str | None:
    for op, av in subpattern:
        if op in (_sre.MAX_REPEAT, _sre.MIN_REPEAT, _sre.POSSESSIVE_REPEAT):
            _low, high, item = av
            unbounded = high == _sre.MAXREPEAT
            if unbounded and inside_unbounded:
                return "Nested unbounded quantifiers can cause catastrophic backtracking"
            if problem := _backtracking_risk(item, inside_unbounded=inside_unbounded or unbounded):
                return problem
        elif op == _sre.SUBPATTERN:
            if problem := _backtracking_risk(av[-1], inside_unbounded=inside_unbounded):
                return problem
        elif op == _sre.ATOMIC_GROUP:
            if problem := _backtracking_risk(av, inside_unbounded=inside_unbounded):
                return problem
        elif op == _sre.BRANCH:
            for branch in av[1]:
                if problem := _backtracking_risk(branch, inside_unbounded=inside_unbounded):
                    return problem
        elif op in (_sre.GROUPREF, _sre.GROUPREF_EXISTS):
            return "Backreferences are not supported"
        elif op in (_sre.ASSERT, _sre.ASSERT_NOT):
            return "Lookaround assertions are not supported"
    return None


_KEEP_FALSE: Final = frozenset(
    {"additionalProperties", "unevaluatedProperties", "unevaluatedItems", "items"}
)
_FORBIDDEN: Final = {"not": {}}


def _without_false_subschemas(node: Any) -> Any:
    if node is False:
        return _FORBIDDEN
    if not isinstance(node, dict):
        return node
    result: dict[str, Any] = {}
    for key, value in node.items():
        if key in _KEEP_FALSE and value is False:
            result[key] = value
        elif key in _SUBSCHEMA:
            result[key] = _without_false_subschemas(value)
        elif key in _SUBSCHEMA_LIST and isinstance(value, list):
            result[key] = [_without_false_subschemas(sub) for sub in value]
        elif key in _SUBSCHEMA_MAP and isinstance(value, dict):
            result[key] = {name: _without_false_subschemas(sub) for name, sub in value.items()}
        else:
            result[key] = value
    return result


def _to_field_errors(error: ValidationError) -> list[FieldError]:
    location = list(error.absolute_path)
    if error.validator == "not" and error.validator_value == {}:
        return [FieldError(to_pointer(location), "not_allowed", "This field is not allowed here")]
    if error.validator == "required" and isinstance(error.instance, dict):
        return [
            FieldError(to_pointer([*location, name]), "required", "This field is required")
            for name in error.validator_value
            if name not in error.instance and error.message == f"{name!r} is a required property"
        ]
    if (
        error.validator == "additionalProperties"
        and error.validator_value is False
        and isinstance(error.instance, dict)
        and isinstance(error.schema, dict)
    ):
        declared = error.schema.get("properties", {})
        patterns = error.schema.get("patternProperties", {})
        return [
            FieldError(
                to_pointer([*location, name]), "additional_property", "This field is not allowed"
            )
            for name in error.instance
            if name not in declared and not any(re.search(p, name) for p in patterns)
        ]
    return [FieldError(to_pointer(location), str(error.validator or "not_allowed"), error.message)]
