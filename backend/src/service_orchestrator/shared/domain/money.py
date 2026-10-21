from __future__ import annotations

import re
from dataclasses import dataclass

_CURRENCY = re.compile(r"^[A-Z]{3}$")


class CurrencyMismatch(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Money:
    amount: int
    currency: str

    def __post_init__(self) -> None:
        if isinstance(self.amount, bool) or not isinstance(self.amount, int):
            raise TypeError("Money amount must be an integer number of minor units")
        if not isinstance(self.currency, str) or not _CURRENCY.match(self.currency):
            raise ValueError(f"Currency must be a 3-letter ISO 4217 code, got {self.currency!r}")

    @classmethod
    def zero(cls, currency: str) -> Money:
        return cls(0, currency)

    def __add__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        if other.currency != self.currency:
            raise CurrencyMismatch(f"Cannot add {other.currency} to {self.currency}")
        return Money(self.amount + other.amount, self.currency)
