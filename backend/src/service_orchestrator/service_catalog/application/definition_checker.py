from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from functools import partial
from typing import Any, Final

from service_orchestrator.fee_policy.calculator import (
    COMPUTED_ONLY_KEYS,
    MAX_AMOUNT,
    PRICING_KEYS,
    ROUNDING_MODES,
)
from service_orchestrator.service_catalog.domain.schema_fields import field_exists
from service_orchestrator.shared.application.limits import DocumentLimits
from service_orchestrator.shared.application.ports import RuleEvaluator, SchemaValidator
from service_orchestrator.shared.domain.field_path import FIELD_PATH_PATTERN
from service_orchestrator.shared.domain.json_limits import check_json_document
from service_orchestrator.shared.domain.validation import FieldError, escape_token, from_pointer

_TEXT: Final = {
    "oneOf": [
        {"type": "string", "minLength": 1, "maxLength": 1000},
        {
            "type": "object",
            "minProperties": 1,
            "propertyNames": {"pattern": "^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$"},
            "additionalProperties": {"type": "string", "maxLength": 1000},
        },
    ]
}

DEFINITION_META_SCHEMA: Final = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["dataSchema"],
    "properties": {
        "dataSchema": {"type": "object"},
        "rules": {"type": "array", "maxItems": 100, "items": {"$ref": "#/$defs/rule"}},
        "fees": {"type": "array", "maxItems": 50, "items": {"$ref": "#/$defs/fee"}},
        "uiSchema": {"$ref": "#/$defs/uiSchema"},
    },
    "$defs": {
        "text": _TEXT,
        "identifier": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_-]{0,63}$"},
        "fieldPath": {"type": "string", "maxLength": 200, "pattern": FIELD_PATH_PATTERN.pattern},
        "fieldPaths": {
            "type": "array",
            "minItems": 1,
            "maxItems": 50,
            "uniqueItems": True,
            "items": {"$ref": "#/$defs/fieldPath"},
        },
        "expression": {"type": ["object", "array", "string", "number", "boolean", "null"]},
        "rule": {
            "type": "object",
            "additionalProperties": False,
            "required": ["id", "type"],
            "properties": {
                "id": {"$ref": "#/$defs/identifier"},
                "type": {"enum": ["require", "visible", "assert"]},
                "when": {"$ref": "#/$defs/expression"},
                "fields": {"$ref": "#/$defs/fieldPaths"},
                "assert": {"$ref": "#/$defs/expression"},
                "path": {"type": "string", "maxLength": 200, "pattern": "^(/[^/]+)*$"},
                "message": {"$ref": "#/$defs/text"},
            },
            "allOf": [
                {
                    "if": {"properties": {"type": {"const": "require"}}},
                    "then": {
                        "required": ["fields"],
                        "properties": {"assert": False, "path": False},
                    },
                },
                {
                    "if": {"properties": {"type": {"const": "visible"}}},
                    "then": {
                        "required": ["fields", "when"],
                        "properties": {"assert": False, "path": False},
                    },
                },
                {
                    "if": {"properties": {"type": {"const": "assert"}}},
                    "then": {"required": ["assert", "message"], "properties": {"fields": False}},
                },
            ],
        },
        "money": {"type": "integer", "minimum": 0, "maximum": MAX_AMOUNT},
        "rounding": {"enum": sorted(ROUNDING_MODES)},
        "fee": {
            "type": "object",
            "additionalProperties": False,
            "required": ["code", "currency"],
            "properties": {
                "code": {"type": "string", "pattern": "^[A-Z][A-Z0-9_]{0,63}$"},
                "label": {"$ref": "#/$defs/text"},
                "currency": {"type": "string", "pattern": "^[A-Z]{3}$"},
                "when": {"$ref": "#/$defs/expression"},
                "amount": {"$ref": "#/$defs/money"},
                "perUnit": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["unitAmount", "quantity"],
                    "properties": {
                        "unitAmount": {"$ref": "#/$defs/money"},
                        "quantity": {"$ref": "#/$defs/expression"},
                        "roundQuantity": {"$ref": "#/$defs/rounding"},
                    },
                },
                "tiers": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["basis", "brackets"],
                    "properties": {
                        "basis": {"$ref": "#/$defs/expression"},
                        "brackets": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": 50,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "upTo": {"type": "number"},
                                    "amount": {"$ref": "#/$defs/money"},
                                    "unitAmount": {"$ref": "#/$defs/money"},
                                },
                            },
                        },
                    },
                },
                "formula": {"$ref": "#/$defs/expression"},
                "rounding": {"$ref": "#/$defs/rounding"},
                "minAmount": {"$ref": "#/$defs/money"},
                "maxAmount": {"$ref": "#/$defs/money"},
            },
        },
        "uiSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "steps": {
                    "type": "array",
                    "maxItems": 50,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["id", "fields"],
                        "properties": {
                            "id": {"$ref": "#/$defs/identifier"},
                            "title": {"$ref": "#/$defs/text"},
                            "description": {"$ref": "#/$defs/text"},
                            "fields": {"$ref": "#/$defs/fieldPaths"},
                        },
                    },
                },
                "fields": {
                    "type": "object",
                    "maxProperties": 500,
                    "propertyNames": {"$ref": "#/$defs/fieldPath"},
                    "additionalProperties": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "label": {"$ref": "#/$defs/text"},
                            "help": {"$ref": "#/$defs/text"},
                            "placeholder": {"$ref": "#/$defs/text"},
                            "widget": {"type": "string", "maxLength": 64},
                        },
                    },
                },
            },
        },
    },
}


class DefinitionChecker:
    def __init__(
        self,
        schema_validator: SchemaValidator,
        rule_evaluator: RuleEvaluator,
        limits: DocumentLimits,
    ) -> None:
        self._schemas = schema_validator
        self._rules = rule_evaluator
        self._limits = limits

    def check_limits(self, definition: Any) -> list[FieldError]:
        return check_json_document(
            definition,
            max_bytes=self._limits.max_definition_bytes,
            max_depth=self._limits.max_definition_depth,
        )

    def check(self, definition: Mapping[str, Any]) -> list[FieldError]:
        if errors := self.check_limits(definition):
            return errors
        if errors := self._schemas.validate(DEFINITION_META_SCHEMA, definition):
            return errors
        data_schema = definition["dataSchema"]
        if errors := self._schemas.check_schema(data_schema):
            return [error.under("/dataSchema") for error in errors]

        exists = partial(field_exists, data_schema)
        return [
            *self._check_rules(definition.get("rules", []), exists),
            *self._check_fees(definition.get("fees", []), exists),
            *self._check_ui(definition.get("uiSchema", {}), exists),
        ]

    def _check_expression(
        self, expression: Any, path: str, exists: Callable[[str], bool]
    ) -> list[FieldError]:
        return [error.under(path) for error in self._rules.check(expression, exists)]

    def _check_rules(
        self, rules: Sequence[Mapping[str, Any]], exists: Callable[[str], bool]
    ) -> list[FieldError]:
        errors: list[FieldError] = []
        seen: set[str] = set()
        for index, rule in enumerate(rules):
            base = f"/rules/{index}"
            if rule["id"] in seen:
                errors.append(
                    FieldError(f"{base}/id", "duplicate_id", f"Rule id {rule['id']!r} is repeated")
                )
            seen.add(rule["id"])
            errors.extend(_unknown_fields(rule.get("fields", []), f"{base}/fields", exists))
            for key in ("when", "assert"):
                if key in rule:
                    errors.extend(self._check_expression(rule[key], f"{base}/{key}", exists))
            target = rule.get("path", "")
            if target and not exists(".".join(from_pointer(target))):
                errors.append(
                    FieldError(
                        f"{base}/path", "unknown_field", f"{target!r} is not a field in dataSchema"
                    )
                )
        return errors

    def _check_fees(
        self, fees: Sequence[Mapping[str, Any]], exists: Callable[[str], bool]
    ) -> list[FieldError]:
        errors: list[FieldError] = []
        codes: set[str] = set()
        for index, fee in enumerate(fees):
            base = f"/fees/{index}"
            if fee["code"] in codes:
                errors.append(
                    FieldError(
                        f"{base}/code", "duplicate_code", f"Fee code {fee['code']!r} is repeated"
                    )
                )
            codes.add(fee["code"])
            errors.extend(_check_pricing(fee, base))
            for path, expression in _fee_expressions(fee, base):
                errors.extend(self._check_expression(expression, path, exists))
        if len({fee["currency"] for fee in fees}) > 1:
            errors.append(
                FieldError("/fees", "mixed_currencies", "All fees must use the same currency")
            )
        return errors

    @staticmethod
    def _check_ui(ui: Mapping[str, Any], exists: Callable[[str], bool]) -> list[FieldError]:
        errors: list[FieldError] = []
        step_ids: set[str] = set()
        for index, step in enumerate(ui.get("steps", [])):
            base = f"/uiSchema/steps/{index}"
            if step["id"] in step_ids:
                errors.append(
                    FieldError(f"{base}/id", "duplicate_id", f"Step id {step['id']!r} is repeated")
                )
            step_ids.add(step["id"])
            errors.extend(_unknown_fields(step["fields"], f"{base}/fields", exists))
        for name in ui.get("fields", {}):
            if not exists(name):
                errors.append(
                    FieldError(
                        f"/uiSchema/fields/{escape_token(name)}",
                        "unknown_field",
                        f"{name!r} is not a field in dataSchema",
                    )
                )
        return errors


def _unknown_fields(
    fields: Sequence[str], base: str, exists: Callable[[str], bool]
) -> list[FieldError]:
    return [
        FieldError(f"{base}/{index}", "unknown_field", f"{field!r} is not a field in dataSchema")
        for index, field in enumerate(fields)
        if not exists(field)
    ]


def _check_pricing(fee: Mapping[str, Any], base: str) -> list[FieldError]:
    errors: list[FieldError] = []
    if len([key for key in PRICING_KEYS if key in fee]) != 1:
        errors.append(
            FieldError(
                base, "invalid_pricing", "Use exactly one of amount, perUnit, tiers or formula"
            )
        )
    if "amount" in fee:
        errors.extend(
            FieldError(
                f"{base}/{key}",
                "not_applicable",
                "Only computed fees (perUnit, tiers, formula) take this setting",
            )
            for key in COMPUTED_ONLY_KEYS
            if key in fee
        )
    if "tiers" in fee:
        errors.extend(_check_brackets(fee["tiers"]["brackets"], f"{base}/tiers/brackets"))
    if fee.get("minAmount", 0) > fee.get("maxAmount", MAX_AMOUNT):
        errors.append(
            FieldError(f"{base}/minAmount", "invalid_range", "minAmount cannot exceed maxAmount")
        )
    errors.extend(
        FieldError(path, "invalid_amount", "Amounts are integers in minor currency units")
        for path, value in _money_values(fee, base)
        if type(value) is not int
    )
    return errors


def _check_brackets(brackets: Sequence[Mapping[str, Any]], base: str) -> list[FieldError]:
    errors: list[FieldError] = []
    previous: float | None = None
    last = len(brackets) - 1
    for index, bracket in enumerate(brackets):
        path = f"{base}/{index}"
        if ("amount" in bracket) == ("unitAmount" in bracket):
            errors.append(
                FieldError(path, "invalid_pricing", "Use exactly one of amount or unitAmount")
            )
        if index == last:
            if "upTo" in bracket:
                errors.append(
                    FieldError(
                        f"{path}/upTo",
                        "not_allowed",
                        "The last bracket has no upTo so it covers every larger value",
                    )
                )
        elif "upTo" not in bracket:
            errors.append(
                FieldError(f"{path}/upTo", "required", "Every bracket but the last needs upTo")
            )
        else:
            if previous is not None and bracket["upTo"] <= previous:
                errors.append(
                    FieldError(f"{path}/upTo", "not_ascending", "upTo values must increase")
                )
            previous = bracket["upTo"]
    return errors


def _money_values(fee: Mapping[str, Any], base: str) -> list[tuple[str, Any]]:
    values = [
        (f"{base}/{key}", fee[key]) for key in ("amount", "minAmount", "maxAmount") if key in fee
    ]
    if "perUnit" in fee:
        values.append((f"{base}/perUnit/unitAmount", fee["perUnit"]["unitAmount"]))
    if "tiers" in fee:
        values.extend(
            (f"{base}/tiers/brackets/{index}/{key}", bracket[key])
            for index, bracket in enumerate(fee["tiers"]["brackets"])
            for key in ("amount", "unitAmount")
            if key in bracket
        )
    return values


def _fee_expressions(fee: Mapping[str, Any], base: str) -> list[tuple[str, Any]]:
    expressions = []
    if "when" in fee:
        expressions.append((f"{base}/when", fee["when"]))
    if "perUnit" in fee:
        expressions.append((f"{base}/perUnit/quantity", fee["perUnit"]["quantity"]))
    if "tiers" in fee:
        expressions.append((f"{base}/tiers/basis", fee["tiers"]["basis"]))
    if "formula" in fee:
        expressions.append((f"{base}/formula", fee["formula"]))
    return expressions
