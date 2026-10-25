from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Response, status

from service_orchestrator.application_processing.application.commands.create_draft import (
    CreateApplicationDraftCommand,
)
from service_orchestrator.application_processing.application.commands.update_draft import (
    UpdateApplicationDraftCommand,
)
from service_orchestrator.application_processing.domain.value_objects import ApplicationStatus
from service_orchestrator.application_processing.presentation.schemas import (
    ApplicationDetailOut,
    ApplicationOut,
    ApplicationPreviewRequest,
    ApplicationQuoteOut,
    ApplicationSummaryOut,
    ApplicationValidationOut,
    CreateApplicationRequest,
    PatchApplicationRequest,
)
from service_orchestrator.bootstrap.dependencies import ContainerDep
from service_orchestrator.shared.presentation.pagination import PageParams
from service_orchestrator.shared.presentation.schemas import ApiResponse, ErrorOut, ok, paged

router = APIRouter(
    prefix="/v1/applications",
    tags=["applications"],
    responses={status_code: {"model": ApiResponse[ErrorOut]} for status_code in (404, 409, 422)},
)

IdempotencyKey = Annotated[
    str | None,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=128,
        description="Repeat a creation safely: the same key returns the original application.",
    ),
]


@router.get("")
def list_applications(
    container: ContainerDep,
    page: PageParams,
    service_code: Annotated[
        str | None, Query(alias="serviceCode", min_length=1, max_length=64)
    ] = None,
    status: ApplicationStatus | None = None,
) -> ApiResponse[list[ApplicationSummaryOut]]:
    result = container.list_applications().execute(page, service_code=service_code, status=status)
    return paged([ApplicationSummaryOut.of(item) for item in result.items], result)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_application(
    body: CreateApplicationRequest,
    response: Response,
    container: ContainerDep,
    idempotency_key: IdempotencyKey = None,
) -> ApiResponse[ApplicationOut]:
    result = container.create_application_draft().execute(
        CreateApplicationDraftCommand(
            service_code=body.service_code, data=body.data, idempotency_key=idempotency_key
        )
    )
    if result.replayed:
        response.status_code = status.HTTP_200_OK
    return ok(ApplicationOut.of(result.view))


@router.patch(
    "/{application_id}",
    openapi_extra={"requestBody": {"content": {"application/merge-patch+json": {}}}},
)
def update_application(
    application_id: UUID, body: PatchApplicationRequest, container: ContainerDep
) -> ApiResponse[ApplicationOut]:
    view = container.update_application_draft().execute(
        UpdateApplicationDraftCommand(application_id=application_id, data_patch=body.data)
    )
    return ok(ApplicationOut.of(view))


@router.post("/{application_id}/submit")
def submit_application(
    application_id: UUID, container: ContainerDep
) -> ApiResponse[ApplicationOut]:
    return ok(ApplicationOut.of(container.submit_application().execute(application_id)))


@router.get("/{application_id}")
def get_application(
    application_id: UUID, container: ContainerDep
) -> ApiResponse[ApplicationDetailOut]:
    return ok(ApplicationDetailOut.of(container.get_application().execute(application_id)))


@router.post("/{application_id}/validate")
def validate_application(
    application_id: UUID,
    container: ContainerDep,
    body: ApplicationPreviewRequest | None = None,
) -> ApiResponse[ApplicationValidationOut]:
    result = container.validate_application().execute(
        application_id, body.data if body is not None else None
    )
    return ok(ApplicationValidationOut.of(result))


@router.post("/{application_id}/quote")
def quote_application(
    application_id: UUID,
    container: ContainerDep,
    body: ApplicationPreviewRequest | None = None,
) -> ApiResponse[ApplicationQuoteOut]:
    result = container.quote_application().execute(
        application_id, body.data if body is not None else None
    )
    return ok(ApplicationQuoteOut.of(result))
