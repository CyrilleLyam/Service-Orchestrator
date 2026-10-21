from __future__ import annotations

import copy
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from service_orchestrator.service_catalog.domain.exceptions import (
    DefinitionInvalid,
    DraftAlreadyExists,
    VersionNotDraft,
    VersionNotFound,
)
from service_orchestrator.service_catalog.domain.value_objects import ServiceCode, VersionStatus
from service_orchestrator.shared.domain.ids import new_id
from service_orchestrator.shared.domain.validation import FieldError

DefinitionCheck = Callable[[Mapping[str, Any]], Sequence[FieldError]]


class ServiceVersion:
    def __init__(
        self,
        *,
        id: UUID,
        service_id: UUID,
        version: int,
        status: VersionStatus,
        definition: Mapping[str, Any],
        created_at: datetime,
        updated_at: datetime,
        published_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.service_id = service_id
        self.version = version
        self.created_at = created_at
        self._status = status
        self._definition = copy.deepcopy(dict(definition))
        self._updated_at = updated_at
        self._published_at = published_at

    @property
    def status(self) -> VersionStatus:
        return self._status

    @property
    def is_draft(self) -> bool:
        return self._status is VersionStatus.DRAFT

    @property
    def definition(self) -> dict[str, Any]:
        return copy.deepcopy(self._definition)

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    @property
    def published_at(self) -> datetime | None:
        return self._published_at

    def _replace_definition(self, definition: Mapping[str, Any], now: datetime) -> None:
        self._ensure_draft()
        self._definition = copy.deepcopy(dict(definition))
        self._updated_at = now

    def _publish(self, check: DefinitionCheck, now: datetime) -> None:
        self._ensure_draft()
        problems = check(self._definition)
        if problems:
            raise DefinitionInvalid(problems)
        self._status = VersionStatus.PUBLISHED
        self._published_at = now
        self._updated_at = now

    def _ensure_draft(self) -> None:
        if not self.is_draft:
            raise VersionNotDraft(self.version)


class Service:
    def __init__(
        self,
        *,
        id: UUID,
        code: ServiceCode,
        name: str,
        description: str,
        created_at: datetime,
        current_version_id: UUID | None = None,
        versions: Iterable[ServiceVersion] = (),
    ) -> None:
        self.id = id
        self.code = code
        self.name = name
        self.description = description
        self.created_at = created_at
        self._current_version_id = current_version_id
        self._versions = sorted(versions, key=lambda v: v.version)

    @classmethod
    def register(cls, *, code: str, name: str, description: str, now: datetime) -> Service:
        return cls(
            id=new_id(), code=ServiceCode(code), name=name, description=description, created_at=now
        )

    @property
    def versions(self) -> tuple[ServiceVersion, ...]:
        return tuple(self._versions)

    @property
    def current_version_id(self) -> UUID | None:
        return self._current_version_id

    @property
    def current_version(self) -> ServiceVersion | None:
        return next((v for v in self._versions if v.id == self._current_version_id), None)

    @property
    def draft(self) -> ServiceVersion | None:
        return next((v for v in self._versions if v.is_draft), None)

    def version(self, number: int) -> ServiceVersion:
        for candidate in self._versions:
            if candidate.version == number:
                return candidate
        raise VersionNotFound(str(self.code), number)

    def create_draft(self, definition: Mapping[str, Any], *, now: datetime) -> ServiceVersion:
        if (draft := self.draft) is not None:
            raise DraftAlreadyExists(str(self.code), draft.version)
        number = self._versions[-1].version + 1 if self._versions else 1
        version = ServiceVersion(
            id=new_id(),
            service_id=self.id,
            version=number,
            status=VersionStatus.DRAFT,
            definition=definition,
            created_at=now,
            updated_at=now,
        )
        self._versions.append(version)
        return version

    def edit_draft(
        self, number: int, definition: Mapping[str, Any], *, now: datetime
    ) -> ServiceVersion:
        version = self.version(number)
        version._replace_definition(definition, now)
        return version

    def publish(self, number: int, *, check: DefinitionCheck, now: datetime) -> ServiceVersion:
        version = self.version(number)
        version._publish(check, now)
        self._current_version_id = version.id
        return version
