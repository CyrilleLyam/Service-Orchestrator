from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from service_orchestrator.service_catalog.application.definition_checker import DefinitionChecker
from service_orchestrator.service_catalog.application.unit_of_work import CatalogUnitOfWork
from service_orchestrator.service_catalog.domain.entities import ServiceVersion
from service_orchestrator.service_catalog.domain.exceptions import (
    DefinitionInvalid,
    ServiceNotFound,
)
from service_orchestrator.shared.application.clock import Clock, utc_now
from service_orchestrator.shared.domain.validation import FieldError

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CreateDraftVersionCommand:
    service_code: str
    definition: Mapping[str, Any] | None = None


class CreateDraftVersion:
    def __init__(
        self, uow: CatalogUnitOfWork, checker: DefinitionChecker, clock: Clock = utc_now
    ) -> None:
        self._uow = uow
        self._checker = checker
        self._clock = clock

    def execute(self, command: CreateDraftVersionCommand) -> ServiceVersion:
        with self._uow as uow:
            service = uow.services.get_by_code(command.service_code, for_update=True)
            if service is None:
                raise ServiceNotFound(command.service_code)

            definition = command.definition
            if definition is None:
                if service.current_version is None:
                    raise DefinitionInvalid(
                        [
                            FieldError(
                                "",
                                "required",
                                "Provide a definition: there is no published version to copy",
                            )
                        ]
                    )
                definition = service.current_version.definition
            if errors := self._checker.check_limits(definition):
                raise DefinitionInvalid(errors)

            version = service.create_draft(definition, now=self._clock())
            uow.services.save(service)
            uow.commit()
        logger.info(
            "draft version created",
            extra={
                "service": command.service_code,
                "version": version.version,
                "copied_from_current": command.definition is None,
            },
        )
        return version
