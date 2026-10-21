from __future__ import annotations

from typing import Any

import pytest

from service_orchestrator.fee_policy.calculator import (
    FeeBreakdown,
    FeeCalculationError,
    calculate_fees,
)
from service_orchestrator.shared.domain.money import CurrencyMismatch, Money
from service_orchestrator.shared.infrastructure.rule_evaluator import JsonLogicEvaluator

RULES = JsonLogicEvaluator()

FEES = [
    {"code": "BASE", "amount": 5000, "currency": "KHR"},
    {"code": "EXPRESS", "amount": 3000, "currency": "KHR", "when": {"var": "express"}},
    {"code": "FRAGILE", "amount": 1500, "currency": "KHR", "when": {"var": "fragile"}},
]


def price(fees: list[dict[str, Any]], data: dict[str, Any]) -> FeeBreakdown:
    return calculate_fees(fees, lambda c: RULES.test(c, data), lambda e: RULES.evaluate(e, data))


def amounts(breakdown: FeeBreakdown) -> list[tuple[str, int]]:
    return [(line.code, line.amount.amount) for line in breakdown.lines]


def dynamic(**pricing: Any) -> list[dict[str, Any]]:
    return [{"code": "FEE", "currency": "KHR", **pricing}]


class TestFixedAndConditional:
    def test_fixed_fees_always_apply_and_conditional_fees_follow_their_condition(self) -> None:
        breakdown = price(FEES, {"express": True})
        assert amounts(breakdown) == [("BASE", 5000), ("EXPRESS", 3000)]
        assert breakdown.total == Money(8000, "KHR")

    def test_snapshot_uses_integer_amounts(self) -> None:
        snapshot = price(FEES, {}).to_snapshot()
        assert snapshot == {
            "currency": "KHR",
            "items": [
                {
                    "code": "BASE",
                    "amount": 5000,
                    "label": None,
                    "quantity": None,
                    "unitAmount": None,
                }
            ],
            "total": 5000,
        }

    def test_no_fees_configured(self) -> None:
        assert price([], {}).to_snapshot() == {"currency": None, "items": [], "total": 0}


class TestPerUnit:
    def test_quantity_times_unit_amount(self) -> None:
        fees = dynamic(perUnit={"unitAmount": 500, "quantity": {"var": "km"}})
        breakdown = price(fees, {"km": 12})
        assert amounts(breakdown) == [("FEE", 6000)]
        assert breakdown.to_snapshot()["items"][0] | {"label": None} == {
            "code": "FEE",
            "amount": 6000,
            "label": None,
            "quantity": 12,
            "unitAmount": 500,
        }

    def test_fractional_quantity_rounds_the_amount_to_nearest_by_default(self) -> None:
        fees = dynamic(perUnit={"unitAmount": 333, "quantity": {"var": "km"}})
        assert amounts(price(fees, {"km": 1.5})) == [("FEE", 500)]

    def test_quantity_can_be_rounded_per_started_unit(self) -> None:
        fees = dynamic(
            perUnit={"unitAmount": 500, "quantity": {"var": "km"}, "roundQuantity": "up"}
        )
        breakdown = price(fees, {"km": 12.1})
        assert amounts(breakdown) == [("FEE", 6500)]
        assert breakdown.lines[0].quantity == 13

    def test_decimal_quantities_do_not_drift(self) -> None:
        fees = dynamic(perUnit={"unitAmount": 500, "quantity": {"var": "km"}}, rounding="up")
        assert amounts(price(fees, {"km": 12.3})) == [("FEE", 6150)]

    def test_missing_quantity_is_reported(self) -> None:
        fees = dynamic(perUnit={"unitAmount": 500, "quantity": {"var": "km"}})
        with pytest.raises(FeeCalculationError, match="'FEE'.*quantity must be a number, got null"):
            price(fees, {})

    def test_default_keeps_optional_quantities_simple(self) -> None:
        fees = dynamic(perUnit={"unitAmount": 2000, "quantity": {"var": ["extraBags", 0]}})
        assert amounts(price(fees, {})) == [("FEE", 0)]


class TestTiers:
    BRACKETS = [
        {"upTo": 2, "amount": 0},
        {"upTo": 10, "amount": 2000},
        {"unitAmount": 300},
    ]

    @pytest.mark.parametrize(
        ("weight", "expected", "unit"),
        [(0.5, 0, None), (2, 0, None), (2.01, 2000, None), (10, 2000, None), (12, 3600, 300)],
    )
    def test_first_bracket_covering_the_basis_applies(self, weight, expected, unit) -> None:
        fees = dynamic(tiers={"basis": {"var": "kg"}, "brackets": self.BRACKETS})
        breakdown = price(fees, {"kg": weight})
        assert amounts(breakdown) == [("FEE", expected)]
        assert breakdown.lines[0].quantity == weight
        assert breakdown.lines[0].unit_amount == unit


class TestFormula:
    def test_formula_result_is_rounded(self) -> None:
        fees = dynamic(formula={"*": [{"var": "subtotal"}, 0.075]})
        assert amounts(price(fees, {"subtotal": 10010})) == [("FEE", 751)]

    def test_floating_point_noise_does_not_round_up(self) -> None:
        fees = dynamic(formula={"*": [0.1, 3, 40000]}, rounding="up")
        assert amounts(price(fees, {})) == [("FEE", 12000)]

    @pytest.mark.parametrize(("mode", "expected"), [("nearest", 3), ("up", 3), ("down", 2)])
    def test_rounding_modes(self, mode, expected) -> None:
        fees = dynamic(formula={"/": [5, 2]}, rounding=mode)
        assert amounts(price(fees, {})) == [("FEE", expected)]

    def test_min_and_max_clamp_computed_amounts(self) -> None:
        fees = [
            {"code": "LOW", "currency": "KHR", "formula": 100, "minAmount": 1500},
            {"code": "HIGH", "currency": "KHR", "formula": 99999, "maxAmount": 50000},
        ]
        assert amounts(price(fees, {})) == [("LOW", 1500), ("HIGH", 50000)]

    def test_negative_amounts_are_rejected(self) -> None:
        with pytest.raises(FeeCalculationError, match="outside"):
            price(dynamic(formula={"-": [5]}), {})

    def test_evaluation_errors_name_the_fee(self) -> None:
        with pytest.raises(FeeCalculationError, match="'FEE'.*Division by zero"):
            price(dynamic(formula={"/": [1, {"var": "n"}]}), {"n": 0})

    def test_condition_errors_name_the_fee(self) -> None:
        fees = dynamic(amount=1, when={">": [{"/": [1, 0]}, 1]})
        with pytest.raises(FeeCalculationError, match="'FEE'"):
            price(fees, {})


def test_money_rejects_floats_and_bad_currencies() -> None:
    with pytest.raises(TypeError):
        Money(10.5, "KHR")
    with pytest.raises(TypeError):
        Money(True, "KHR")
    with pytest.raises(ValueError):
        Money(10, "riel")


def test_money_never_mixes_currencies() -> None:
    with pytest.raises(CurrencyMismatch):
        Money(1, "KHR") + Money(1, "USD")
