from __future__ import annotations

import logging
from dataclasses import dataclass

from service_orchestrator.service_catalog.application.definition_checker import DefinitionChecker
from service_orchestrator.service_catalog.application.unit_of_work import CatalogUnitOfWork
from service_orchestrator.service_catalog.domain.entities import ServiceVersion
from service_orchestrator.service_catalog.domain.exceptions import ServiceNotFound
from service_orchestrator.shared.application.clock import Clock, utc_now

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PublishVersionCommand:
    service_code: str
    version: int


class PublishVersion:
    def __init__(
        self, uow: CatalogUnitOfWork, checker: DefinitionChecker, clock: Clock = utc_now
    ) -> None:
        self._uow = uow
        self._checker = checker
        self._clock = clock

    def execute(self, command: PublishVersionCommand) -> ServiceVersion:
        with self._uow as uow:
            service = uow.services.get_by_code(command.service_code, for_update=True)
            if service is None:
                raise ServiceNotFound(command.service_code)
            version = service.publish(command.version, check=self._checker.check, now=self._clock())
            uow.services.save(service)
            uow.commit()
        logger.info(
            "version published",
            extra={"service": command.service_code, "version": version.version},
        )
        return version
