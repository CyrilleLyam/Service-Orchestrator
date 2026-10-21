from __future__ import annotations

from uuid import UUID

from service_orchestrator.application_processing.application.ports import PinnedServiceVersion
from service_orchestrator.service_catalog.application.queries.published_versions import (
    PublishedVersion,
    PublishedVersions,
)


class CatalogGateway:
    def __init__(self, published_versions: PublishedVersions) -> None:
        self._published_versions = published_versions

    def current_published(self, service_code: str) -> PinnedServiceVersion:
        return _pinned(self._published_versions.current(service_code))

    def published_version(self, service_version_id: UUID) -> PinnedServiceVersion:
        return _pinned(self._published_versions.by_id(service_version_id))


def _pinned(version: PublishedVersion) -> PinnedServiceVersion:
    return PinnedServiceVersion(
        service_version_id=version.version_id,
        service_code=version.service_code,
        version=version.version,
        definition=version.definition,
    )
