from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from service_orchestrator.service_catalog.domain.exceptions import InvalidServiceCode

_SERVICE_CODE: Final = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


@dataclass(frozen=True, slots=True)
class ServiceCode:
    value: str

    def __post_init__(self) -> None:
        if not (2 <= len(self.value) <= 64 and _SERVICE_CODE.match(self.value)):
            raise InvalidServiceCode(self.value)

    def __str__(self) -> str:
        return self.value


class VersionStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
