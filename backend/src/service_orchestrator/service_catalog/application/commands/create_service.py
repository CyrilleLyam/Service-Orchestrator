from __future__ import annotations

import logging
from dataclasses import dataclass

from service_orchestrator.service_catalog.application.unit_of_work import CatalogUnitOfWork
from service_orchestrator.service_catalog.domain.entities import Service
from service_orchestrator.service_catalog.domain.exceptions import ServiceCodeTaken
from service_orchestrator.shared.application.clock import Clock, utc_now

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CreateServiceCommand:
    code: str
    name: str
    description: str = ""


class CreateService:
    def __init__(self, uow: CatalogUnitOfWork, clock: Clock = utc_now) -> None:
        self._uow = uow
        self._clock = clock

    def execute(self, command: CreateServiceCommand) -> Service:
        service = Service.register(
            code=command.code, name=command.name, description=command.description, now=self._clock()
        )
        with self._uow as uow:
            if uow.services.get_by_code(command.code) is not None:
                raise ServiceCodeTaken(command.code)
            uow.services.add(service)
            uow.commit()
        logger.info("service created", extra={"service": command.code})
        return service
