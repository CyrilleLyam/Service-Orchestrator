from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from service_orchestrator.fee_policy.calculator import FeeBreakdown
from service_orchestrator.shared.application.pagination import Page
from service_orchestrator.shared.domain.validation import FieldError
from service_orchestrator.shared.infrastructure.log_config import request_id_var


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class FieldErrorOut(ApiModel):
    path: str
    code: str
    message: str
    rule_id: str | None = None

    @classmethod
    def of(cls, error: FieldError) -> FieldErrorOut:
        return cls(path=error.path, code=error.code, message=error.message, rule_id=error.rule_id)


class ErrorOut(ApiModel):
    code: str
    message: str
    errors: list[FieldErrorOut] = []
    request_id: str | None = None


class PageMeta(ApiModel):
    page: int
    page_size: int
    total: int
    total_pages: int

    @classmethod
    def of(cls, page: Page[Any]) -> PageMeta:
        return cls(
            page=page.request.page,
            page_size=page.request.size,
            total=page.total,
            total_pages=page.total_pages,
        )


class ApiResponse[T](ApiModel):
    error: bool = False
    data: T
    pagination: PageMeta | None = None


def ok[T](data: T) -> ApiResponse[T]:
    return ApiResponse[T](data=data)


def paged[T](items: list[T], page: Page[Any]) -> ApiResponse[list[T]]:
    return ApiResponse[list[T]](data=items, pagination=PageMeta.of(page))


def error_body(code: str, message: str, errors: Sequence[FieldError] = ()) -> dict[str, Any]:
    detail = ErrorOut(
        code=code,
        message=message,
        errors=[FieldErrorOut.of(e) for e in errors],
        request_id=request_id_var.get(),
    )
    return ApiResponse[ErrorOut](error=True, data=detail).model_dump(by_alias=True, mode="json")


class FeeItemOut(ApiModel):
    code: str
    amount: int
    label: str | dict[str, str] | None = None
    quantity: int | float | None = None
    unit_amount: int | None = None


class FeeBreakdownOut(ApiModel):
    currency: str | None
    items: list[FeeItemOut]
    total: int

    @classmethod
    def of(cls, fees: FeeBreakdown) -> FeeBreakdownOut:
        return cls.from_snapshot(fees.to_snapshot())

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any]) -> FeeBreakdownOut:
        return cls.model_validate(snapshot)
