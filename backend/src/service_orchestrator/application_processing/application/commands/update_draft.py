from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from service_orchestrator.application_processing.application.ports import (
    ApplicationUnitOfWork,
    ServiceCatalogGateway,
)
from service_orchestrator.application_processing.application.views import ApplicationView
from service_orchestrator.application_processing.domain.exceptions import (
    ApplicationDataInvalid,
    ApplicationNotFound,
)
from service_orchestrator.shared.application.clock import Clock, utc_now
from service_orchestrator.shared.application.limits import DocumentLimits
from service_orchestrator.shared.domain.json_limits import check_json_document

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class UpdateApplicationDraftCommand:
    application_id: UUID
    data_patch: Mapping[str, Any]


class UpdateApplicationDraft:
    def __init__(
        self,
        uow: ApplicationUnitOfWork,
        catalog: ServiceCatalogGateway,
        limits: DocumentLimits,
        clock: Clock = utc_now,
    ) -> None:
        self._uow = uow
        self._catalog = catalog
        self._limits = limits
        self._clock = clock

    def execute(self, command: UpdateApplicationDraftCommand) -> ApplicationView:
        self._check_limits(command.data_patch)
        with self._uow as uow:
            application = uow.applications.get(command.application_id, for_update=True)
            if application is None:
                raise ApplicationNotFound(command.application_id)
            application.apply_patch(command.data_patch, now=self._clock())
            self._check_limits(application.data)
            uow.applications.save(application)
            uow.commit()
        logger.info(
            "application updated",
            extra={"application_id": str(application.id), "fields": sorted(command.data_patch)},
        )
        pinned = self._catalog.published_version(application.service_version_id)
        return ApplicationView(application, pinned.service_code, pinned.version)

    def _check_limits(self, data: Any) -> None:
        if errors := check_json_document(
            data, max_bytes=self._limits.max_payload_bytes, max_depth=self._limits.max_payload_depth
        ):
            raise ApplicationDataInvalid([error.under("/data") for error in errors])
