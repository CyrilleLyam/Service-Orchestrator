from __future__ import annotations

from service_orchestrator.service_catalog.application.unit_of_work import CatalogUnitOfWork
from service_orchestrator.service_catalog.domain.entities import Service, ServiceVersion
from service_orchestrator.service_catalog.domain.exceptions import ServiceNotFound
from service_orchestrator.shared.application.pagination import Page, PageRequest


class GetService:
    def __init__(self, uow: CatalogUnitOfWork) -> None:
        self._uow = uow

    def execute(self, service_code: str) -> Service:
        with self._uow as uow:
            service = uow.services.get_by_code(service_code)
        if service is None:
            raise ServiceNotFound(service_code)
        return service


class ListServices:
    def __init__(self, uow: CatalogUnitOfWork) -> None:
        self._uow = uow

    def execute(self, request: PageRequest | None = None) -> Page[Service]:
        request = request or PageRequest()
        with self._uow as uow:
            items = uow.services.list_page(request.offset, request.size)
            total = uow.services.count()
        return Page(tuple(items), total, request)


class GetServiceVersion:
    def __init__(self, uow: CatalogUnitOfWork) -> None:
        self._uow = uow

    def execute(self, service_code: str, version: int) -> ServiceVersion:
        return GetService(self._uow).execute(service_code).version(version)
