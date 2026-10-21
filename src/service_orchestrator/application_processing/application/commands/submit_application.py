from __future__ import annotations

import logging
from uuid import UUID

from service_orchestrator.application_processing.application.ports import (
    ApplicationUnitOfWork,
    ServiceCatalogGateway,
)
from service_orchestrator.application_processing.application.views import ApplicationView
from service_orchestrator.application_processing.domain.exceptions import (
    ApplicationNotFound,
    SubmissionRejected,
)
from service_orchestrator.shared.application.clock import Clock, utc_now
from service_orchestrator.shared.application.payload_checker import PayloadChecker

logger = logging.getLogger(__name__)


class SubmitApplication:
    def __init__(
        self,
        uow: ApplicationUnitOfWork,
        catalog: ServiceCatalogGateway,
        checker: PayloadChecker,
        clock: Clock = utc_now,
    ) -> None:
        self._uow = uow
        self._catalog = catalog
        self._checker = checker
        self._clock = clock

    def execute(self, application_id: UUID) -> ApplicationView:
        with self._uow as uow:
            application = uow.applications.get(application_id, for_update=True)
            if application is None:
                raise ApplicationNotFound(application_id)
            application.ensure_draft()

            pinned = self._catalog.published_version(application.service_version_id)
            evaluation = self._checker.evaluate(pinned.definition, application.data)
            context = {
                "application_id": str(application_id),
                "service": pinned.service_code,
                "version": pinned.version,
            }
            if evaluation.fees is None:
                logger.info(
                    "submission rejected", extra={**context, "errors": len(evaluation.errors)}
                )
                raise SubmissionRejected(evaluation.errors)

            application.submit(evaluation.fees, now=self._clock())
            uow.applications.save(application)
            uow.commit()
        logger.info(
            "application submitted",
            extra={
                **context,
                "total": evaluation.fees.total.amount if evaluation.fees.total else 0,
                "currency": evaluation.fees.currency,
            },
        )
        return ApplicationView(application, pinned.service_code, pinned.version)
