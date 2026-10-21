from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from service_orchestrator.application_processing.application.ports import (
    ApplicationUnitOfWork,
    ServiceCatalogGateway,
)
from service_orchestrator.application_processing.application.views import ApplicationView
from service_orchestrator.application_processing.domain.entities import Application
from service_orchestrator.application_processing.domain.exceptions import (
    ApplicationDataInvalid,
    IdempotencyKeyReused,
)
from service_orchestrator.shared.application.clock import Clock, utc_now
from service_orchestrator.shared.application.limits import DocumentLimits
from service_orchestrator.shared.domain.json_limits import check_json_document

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CreateApplicationDraftCommand:
    service_code: str
    data: Mapping[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class CreatedApplication:
    view: ApplicationView
    replayed: bool


class CreateApplicationDraft:
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

    def execute(self, command: CreateApplicationDraftCommand) -> CreatedApplication:
        if errors := check_json_document(
            command.data,
            max_bytes=self._limits.max_payload_bytes,
            max_depth=self._limits.max_payload_depth,
        ):
            raise ApplicationDataInvalid([error.under("/data") for error in errors])

        if command.idempotency_key and (replay := self._replay(command)):
            return replay

        pinned = self._catalog.current_published(command.service_code)
        application = Application.start(
            service_version_id=pinned.service_version_id,
            data=command.data,
            now=self._clock(),
            idempotency_key=command.idempotency_key,
        )
        with self._uow as uow:
            uow.applications.add(application)
            uow.commit()
        logger.info(
            "application created",
            extra={
                "application_id": str(application.id),
                "service": pinned.service_code,
                "version": pinned.version,
            },
        )
        return CreatedApplication(
            ApplicationView(application, pinned.service_code, pinned.version), replayed=False
        )

    def _replay(self, command: CreateApplicationDraftCommand) -> CreatedApplication | None:
        assert command.idempotency_key is not None
        with self._uow as uow:
            existing = uow.applications.get_by_idempotency_key(command.idempotency_key)
        if existing is None:
            return None
        pinned = self._catalog.published_version(existing.service_version_id)
        if pinned.service_code != command.service_code:
            raise IdempotencyKeyReused()
        logger.info(
            "application creation replayed",
            extra={"application_id": str(existing.id), "service": pinned.service_code},
        )
        return CreatedApplication(
            ApplicationView(existing, pinned.service_code, pinned.version), replayed=True
        )
