from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query

from service_orchestrator.shared.application.pagination import PageRequest


def page_request(
    page: Annotated[int, Query(ge=1, le=100_000)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
) -> PageRequest:
    return PageRequest(page=page, size=page_size)


PageParams = Annotated[PageRequest, Depends(page_request)]
