from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Any, Final

from service_orchestrator.shared.domain.exceptions import RuleEvaluationError
from service_orchestrator.shared.domain.money import Money

MAX_AMOUNT: Final = 1_000_000_000_000
PRICING_KEYS: Final = ("amount", "perUnit", "tiers", "formula")
COMPUTED_ONLY_KEYS: Final = ("rounding", "minAmount", "maxAmount")
ROUNDING_MODES: Final = {"nearest": ROUND_HALF_UP, "up": ROUND_CEILING, "down": ROUND_FLOOR}

_PRECISION: Final = Decimal("0.000001")
_MAX_MAGNITUDE: Final = Decimal(10) ** 15


class FeeCalculationError(Exception):
    def __init__(self, fee_code: str, reason: str) -> None:
        super().__init__(f"Fee {fee_code!r} could not be calculated: {reason}")
        self.fee_code = fee_code


@dataclass(frozen=True, slots=True)
class FeeLine:
    code: str
    amount: Money
    label: Any = None
    quantity: int | float | None = None
    unit_amount: int | None = None


@dataclass(frozen=True, slots=True)
class FeeBreakdown:
    currency: str | None
    lines: tuple[FeeLine, ...]
    total: Money | None

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "currency": self.currency,
            "items": [
                {
                    "code": line.code,
                    "amount": line.amount.amount,
                    "label": line.label,
                    "quantity": line.quantity,
                    "unitAmount": line.unit_amount,
                }
                for line in self.lines
            ],
            "total": self.total.amount if self.total else 0,
        }


def calculate_fees(
    fees: Sequence[Mapping[str, Any]],
    condition_holds: Callable[[Any], bool],
    evaluate: Callable[[Any], Any],
) -> FeeBreakdown:
    currency = fees[0]["currency"] if fees else None
    lines = []
    for fee in fees:
        try:
            if "when" in fee and not condition_holds(fee["when"]):
                continue
            lines.append(_price(fee, evaluate))
        except RuleEvaluationError as exc:
            raise FeeCalculationError(fee["code"], str(exc)) from exc
    total = sum((line.amount for line in lines), Money.zero(currency)) if currency else None
    return FeeBreakdown(currency, tuple(lines), total)


def _price(fee: Mapping[str, Any], evaluate: Callable[[Any], Any]) -> FeeLine:
    code, currency, label = fee["code"], fee["currency"], fee.get("label")
    if "amount" in fee:
        return FeeLine(code, Money(fee["amount"], currency), label)

    quantity: Decimal | None = None
    unit_amount: int | None = None
    if "perUnit" in fee:
        spec = fee["perUnit"]
        quantity = _number(code, evaluate(spec["quantity"]), "quantity")
        if "roundQuantity" in spec:
            quantity = _round(quantity, spec["roundQuantity"])
        unit_amount = spec["unitAmount"]
        raw = quantity * unit_amount
    elif "tiers" in fee:
        spec = fee["tiers"]
        quantity = _number(code, evaluate(spec["basis"]), "basis")
        bracket = _bracket_for(code, quantity, spec["brackets"])
        unit_amount = bracket.get("unitAmount")
        raw = quantity * unit_amount if unit_amount is not None else Decimal(bracket["amount"])
    else:
        raw = _number(code, evaluate(fee["formula"]), "formula result")

    amount = int(_round(raw, fee.get("rounding", "nearest")))
    amount = max(amount, fee.get("minAmount", amount))
    amount = min(amount, fee.get("maxAmount", amount))
    if not 0 <= amount <= MAX_AMOUNT:
        raise FeeCalculationError(code, f"amount {amount} is outside 0..{MAX_AMOUNT}")
    return FeeLine(code, Money(amount, currency), label, _plain(quantity), unit_amount)


def _bracket_for(
    code: str, basis: Decimal, brackets: Sequence[Mapping[str, Any]]
) -> Mapping[str, Any]:
    for bracket in brackets:
        if "upTo" not in bracket or basis <= _number(code, bracket["upTo"], "upTo"):
            return bracket
    raise FeeCalculationError(code, f"no bracket covers {_plain(basis)}")


def _number(code: str, value: Any, what: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, int | float):
        kind = "null" if value is None else type(value).__name__
        raise FeeCalculationError(code, f"{what} must be a number, got {kind}")
    if isinstance(value, float) and not math.isfinite(value):
        raise FeeCalculationError(code, f"{what} must be finite")
    number = Decimal(repr(value)) if isinstance(value, float) else Decimal(value)
    if abs(number) > _MAX_MAGNITUDE:
        raise FeeCalculationError(code, f"{what} is out of range")
    return number.quantize(_PRECISION)


def _round(value: Decimal, mode: str) -> Decimal:
    return value.to_integral_value(rounding=ROUNDING_MODES[mode])


def _plain(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    return int(value) if value == value.to_integral_value() else float(value)
