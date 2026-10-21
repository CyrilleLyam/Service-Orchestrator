from __future__ import annotations

import copy

import pytest

from service_orchestrator.service_catalog.application.definition_checker import DefinitionChecker
from service_orchestrator.shared.application.limits import DocumentLimits
from service_orchestrator.shared.infrastructure.rule_evaluator import JsonLogicEvaluator
from service_orchestrator.shared.infrastructure.schema_validator import JsonSchemaValidator
from tests.conftest import load_example


@pytest.mark.parametrize(
    "example", ["delivery_service.json", "event_registration.json", "equipment_rental.json"]
)
def test_example_definitions_are_publishable(definition_checker, example) -> None:
    assert definition_checker.check(load_example(example)["definition"]) == []


def codes(errors) -> list[tuple[str, str]]:
    return [(e.path, e.code) for e in errors]


def test_definition_must_match_the_platform_meta_schema(definition_checker) -> None:
    errors = definition_checker.check({"rules": [], "script": "rm -rf /"})
    assert ("/dataSchema", "required") in codes(errors)
    assert ("/script", "additional_property") in codes(errors)


def test_data_schema_problems_are_reported_under_data_schema(
    definition_checker, delivery_definition
) -> None:
    delivery_definition["dataSchema"]["properties"]["notes"]["$ref"] = "https://evil.example/x"
    assert codes(definition_checker.check(delivery_definition)) == [
        ("/dataSchema/properties/notes/$ref", "remote_ref")
    ]


def test_rules_must_reference_known_fields(definition_checker, delivery_definition) -> None:
    delivery_definition["rules"].append(
        {"id": "r2", "type": "require", "when": {"var": "ghost"}, "fields": ["phantom"]}
    )
    assert codes(definition_checker.check(delivery_definition)) == [
        ("/rules/1/fields/0", "unknown_field"),
        ("/rules/1/when/var", "unknown_field"),
    ]


def test_rules_reject_unsupported_operators(definition_checker, delivery_definition) -> None:
    delivery_definition["rules"][0]["assert"] = {"method": ["__import__('os')"]}
    assert codes(definition_checker.check(delivery_definition)) == [
        ("/rules/0/assert/method", "unsupported_operator")
    ]


def test_rule_ids_must_be_unique(definition_checker, delivery_definition) -> None:
    delivery_definition["rules"].append(copy.deepcopy(delivery_definition["rules"][0]))
    assert codes(definition_checker.check(delivery_definition)) == [("/rules/1/id", "duplicate_id")]


def test_rule_shape_depends_on_rule_type(definition_checker, delivery_definition) -> None:
    delivery_definition["rules"] = [
        {"id": "a", "type": "assert", "assert": True},
        {"id": "b", "type": "visible", "fields": ["express"]},
        {"id": "c", "type": "require", "fields": ["express"], "assert": True},
    ]
    found = codes(definition_checker.check(delivery_definition))
    assert ("/rules/0/message", "required") in found
    assert ("/rules/1/when", "required") in found
    assert ("/rules/2/assert", "not_allowed") in found


def test_assert_path_must_point_at_a_field(definition_checker, delivery_definition) -> None:
    delivery_definition["rules"][0]["path"] = "/nowhere"
    assert codes(definition_checker.check(delivery_definition)) == [
        ("/rules/0/path", "unknown_field")
    ]


def test_fee_codes_unique_amounts_integer_and_one_currency(
    definition_checker, delivery_definition
) -> None:
    delivery_definition["fees"] += [
        {"code": "BASE", "amount": 1, "currency": "KHR"},
        {"code": "ROUNDED", "amount": 10.0, "currency": "KHR"},
        {"code": "DOLLARS", "amount": 1, "currency": "USD"},
    ]
    assert codes(definition_checker.check(delivery_definition)) == [
        ("/fees/2/code", "duplicate_code"),
        ("/fees/3/amount", "invalid_amount"),
        ("/fees", "mixed_currencies"),
    ]


def test_negative_fee_amounts_are_rejected(definition_checker, delivery_definition) -> None:
    delivery_definition["fees"][0]["amount"] = -1
    assert codes(definition_checker.check(delivery_definition)) == [("/fees/0/amount", "minimum")]


def test_fee_conditions_are_checked(definition_checker, delivery_definition) -> None:
    delivery_definition["fees"][1]["when"] = {"==": [{"var": "ghost"}, True]}
    assert codes(definition_checker.check(delivery_definition)) == [
        ("/fees/1/when/==/0/var", "unknown_field")
    ]


def test_ui_fields_must_exist(definition_checker, delivery_definition) -> None:
    delivery_definition["uiSchema"]["steps"][0]["fields"].append("ghost")
    delivery_definition["uiSchema"]["fields"]["phantom"] = {"widget": "text"}
    assert codes(definition_checker.check(delivery_definition)) == [
        ("/uiSchema/steps/0/fields/3", "unknown_field"),
        ("/uiSchema/fields/phantom", "unknown_field"),
    ]


def test_field_references_follow_refs_and_nesting(definition_checker) -> None:
    definition = {
        "dataSchema": {
            "type": "object",
            "$defs": {"address": {"type": "object", "properties": {"city": {"type": "string"}}}},
            "properties": {
                "home": {"$ref": "#/$defs/address"},
                "items": {"type": "array", "items": {"type": "object", "properties": {"sku": {}}}},
            },
        },
        "uiSchema": {"steps": [{"id": "s", "fields": ["home.city", "items.0.sku"]}]},
    }
    assert definition_checker.check(definition) == []


def test_definition_size_is_limited(schema_validator, rule_evaluator, delivery_definition) -> None:
    checker = DefinitionChecker(
        schema_validator, rule_evaluator, DocumentLimits(max_definition_bytes=500)
    )
    assert codes(checker.check(delivery_definition)) == [("", "too_large")]


def test_definition_checker_uses_configured_rule_limits(delivery_definition) -> None:
    checker = DefinitionChecker(
        JsonSchemaValidator(), JsonLogicEvaluator(max_depth=1), DocumentLimits()
    )
    assert ("/rules/0/assert/<=/0", "too_deep") in codes(checker.check(delivery_definition))


def fee(**pricing):
    return {"code": "FEE", "currency": "KHR", **pricing}


@pytest.mark.parametrize(
    ("bad_fee", "expected"),
    [
        (fee(), ("/fees/2", "invalid_pricing")),
        (fee(amount=1, formula=2), ("/fees/2", "invalid_pricing")),
        (fee(amount=1, rounding="up"), ("/fees/2/rounding", "not_applicable")),
        (fee(amount=1, minAmount=5), ("/fees/2/minAmount", "not_applicable")),
        (fee(formula=1, minAmount=9, maxAmount=5), ("/fees/2/minAmount", "invalid_range")),
        (fee(formula=1, rounding="sideways"), ("/fees/2/rounding", "enum")),
        (
            fee(perUnit={"unitAmount": 2.0, "quantity": {"var": "distanceKm"}}),
            ("/fees/2/perUnit/unitAmount", "invalid_amount"),
        ),
        (
            fee(perUnit={"unitAmount": 5, "quantity": {"var": "ghost"}}),
            ("/fees/2/perUnit/quantity/var", "unknown_field"),
        ),
        (fee(formula={"pow": [2, 64]}), ("/fees/2/formula/pow", "unsupported_operator")),
        (
            fee(tiers={"basis": {"var": "weightKg"}, "brackets": [{"upTo": 5, "amount": 1}]}),
            ("/fees/2/tiers/brackets/0/upTo", "not_allowed"),
        ),
        (
            fee(tiers={"basis": {"var": "weightKg"}, "brackets": [{"amount": 1}, {"amount": 2}]}),
            ("/fees/2/tiers/brackets/0/upTo", "required"),
        ),
        (
            fee(
                tiers={
                    "basis": {"var": "weightKg"},
                    "brackets": [{"upTo": 5, "amount": 1}, {"upTo": 5, "amount": 2}, {"amount": 3}],
                }
            ),
            ("/fees/2/tiers/brackets/1/upTo", "not_ascending"),
        ),
        (
            fee(tiers={"basis": {"var": "weightKg"}, "brackets": [{"amount": 1, "unitAmount": 2}]}),
            ("/fees/2/tiers/brackets/0", "invalid_pricing"),
        ),
        (
            fee(tiers={"basis": {"var": "ghost"}, "brackets": [{"amount": 1}]}),
            ("/fees/2/tiers/basis/var", "unknown_field"),
        ),
    ],
)
def test_dynamic_fee_configuration_is_checked(
    definition_checker, delivery_definition, bad_fee, expected
):
    delivery_definition["fees"].append(bad_fee)
    assert expected in codes(definition_checker.check(delivery_definition))


def test_valid_dynamic_fees_publish(definition_checker, delivery_definition) -> None:
    delivery_definition["fees"] += [
        fee(perUnit={"unitAmount": 300, "quantity": {"var": "distanceKm"}, "roundQuantity": "up"}),
        {
            "code": "WEIGHT",
            "currency": "KHR",
            "tiers": {
                "basis": {"var": "weightKg"},
                "brackets": [
                    {"upTo": 2, "amount": 0},
                    {"upTo": 10, "amount": 2000},
                    {"unitAmount": 300},
                ],
            },
        },
        {
            "code": "HANDLING",
            "currency": "KHR",
            "formula": {"*": [{"var": "weightKg"}, {"var": "distanceKm"}, 2]},
            "rounding": "down",
            "minAmount": 500,
            "maxAmount": 20000,
        },
    ]
    assert definition_checker.check(delivery_definition) == []
