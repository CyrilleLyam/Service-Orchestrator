from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil


@dataclass(frozen=True, slots=True)
class PageRequest:
    page: int = 1
    size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


@dataclass(frozen=True, slots=True)
class Page[T]:
    items: tuple[T, ...]
    total: int
    request: PageRequest

    @property
    def total_pages(self) -> int:
        return ceil(self.total / self.request.size)

    @classmethod
    def of(cls, items: Sequence[T], request: PageRequest) -> Page[T]:
        window = items[request.offset : request.offset + request.size]
        return cls(tuple(window), len(items), request)
