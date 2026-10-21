from __future__ import annotations

from uuid import UUID

from service_orchestrator.application_processing.application.ports import (
    ApplicationUnitOfWork,
    ServiceCatalogGateway,
)
from service_orchestrator.application_processing.application.views import ApplicationView
from service_orchestrator.application_processing.domain.exceptions import ApplicationNotFound


class GetApplication:
    def __init__(self, uow: ApplicationUnitOfWork, catalog: ServiceCatalogGateway) -> None:
        self._uow = uow
        self._catalog = catalog

    def execute(self, application_id: UUID) -> ApplicationView:
        with self._uow as uow:
            application = uow.applications.get(application_id)
            if application is None:
                raise ApplicationNotFound(application_id)
            events = uow.applications.events_for(application_id)
        pinned = self._catalog.published_version(application.service_version_id)
        return ApplicationView(application, pinned.service_code, pinned.version, tuple(events))
