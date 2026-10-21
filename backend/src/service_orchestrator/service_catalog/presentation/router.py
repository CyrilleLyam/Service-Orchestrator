from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, status

from service_orchestrator.bootstrap.dependencies import ContainerDep
from service_orchestrator.service_catalog.application.commands.create_service import (
    CreateServiceCommand,
)
from service_orchestrator.service_catalog.application.commands.create_version import (
    CreateDraftVersionCommand,
)
from service_orchestrator.service_catalog.application.commands.publish_version import (
    PublishVersionCommand,
)
from service_orchestrator.service_catalog.application.commands.update_version import (
    EditDraftVersionCommand,
)
from service_orchestrator.service_catalog.presentation.schemas import (
    CreateServiceRequest,
    CreateVersionRequest,
    PayloadRequest,
    QuoteOut,
    ServiceOut,
    ServiceSummaryOut,
    UpdateVersionRequest,
    ValidationResultOut,
    VersionOut,
    VersionSummaryOut,
)
from service_orchestrator.shared.application.pagination import Page
from service_orchestrator.shared.presentation.pagination import PageParams
from service_orchestrator.shared.presentation.schemas import ApiResponse, ErrorOut, ok, paged

router = APIRouter(
    prefix="/v1/services",
    tags=["services"],
    responses={status_code: {"model": ApiResponse[ErrorOut]} for status_code in (404, 409, 422)},
)

VersionNumber = Annotated[int, Path(ge=1, le=1_000_000)]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_service(body: CreateServiceRequest, container: ContainerDep) -> ApiResponse[ServiceOut]:
    service = container.create_service().execute(
        CreateServiceCommand(code=body.code, name=body.name, description=body.description)
    )
    return ok(ServiceOut.of(service))


@router.get("")
def list_services(
    container: ContainerDep, page: PageParams
) -> ApiResponse[list[ServiceSummaryOut]]:
    result = container.list_services().execute(page)
    return paged([ServiceSummaryOut.of(s) for s in result.items], result)


@router.get("/{code}")
def get_service(code: str, container: ContainerDep) -> ApiResponse[ServiceOut]:
    return ok(ServiceOut.of(container.get_service().execute(code)))


@router.get("/{code}/versions")
def list_versions(
    code: str, container: ContainerDep, page: PageParams
) -> ApiResponse[list[VersionSummaryOut]]:
    versions = Page.of(container.get_service().execute(code).versions, page)
    return paged([VersionSummaryOut.of(v) for v in versions.items], versions)


@router.get("/{code}/versions/{version}")
def get_version(
    code: str, version: VersionNumber, container: ContainerDep
) -> ApiResponse[VersionOut]:
    return ok(VersionOut.of_version(code, container.get_service_version().execute(code, version)))


@router.post("/{code}/versions", status_code=status.HTTP_201_CREATED)
def create_version(
    code: str, body: CreateVersionRequest, container: ContainerDep
) -> ApiResponse[VersionOut]:
    version = container.create_draft_version().execute(
        CreateDraftVersionCommand(service_code=code, definition=body.definition)
    )
    return ok(VersionOut.of_version(code, version))


@router.put("/{code}/versions/{version}")
def update_version(
    code: str, version: VersionNumber, body: UpdateVersionRequest, container: ContainerDep
) -> ApiResponse[VersionOut]:
    updated = container.edit_draft_version().execute(
        EditDraftVersionCommand(service_code=code, version=version, definition=body.definition)
    )
    return ok(VersionOut.of_version(code, updated))


@router.post("/{code}/versions/{version}/publish")
def publish_version(
    code: str, version: VersionNumber, container: ContainerDep
) -> ApiResponse[VersionOut]:
    published = container.publish_version().execute(
        PublishVersionCommand(service_code=code, version=version)
    )
    return ok(VersionOut.of_version(code, published))


@router.post("/{code}/validate")
def validate_payload(
    code: str, body: PayloadRequest, container: ContainerDep
) -> ApiResponse[ValidationResultOut]:
    return ok(ValidationResultOut.of(container.validate_payload().execute(code, body.data)))


@router.post("/{code}/quote")
def quote_fees(code: str, body: PayloadRequest, container: ContainerDep) -> ApiResponse[QuoteOut]:
    return ok(QuoteOut.of(container.quote_fees().execute(code, body.data)))
