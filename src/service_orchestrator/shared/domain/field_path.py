from __future__ import annotations

import re
from typing import Any, Final

from service_orchestrator.shared.domain.validation import to_pointer

FIELD_PATH_PATTERN: Final = re.compile(r"^[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)*$")


class _Missing:
    def __repr__(self) -> str:
        return "MISSING"


MISSING: Final = _Missing()


def segments(path: str) -> list[str]:
    return path.split(".")


def get_value(data: Any, path: str) -> Any:
    current = data
    for segment in segments(path):
        if isinstance(current, dict):
            if segment not in current:
                return MISSING
            current = current[segment]
        elif isinstance(current, list) and segment.isdigit():
            index = int(segment)
            if index >= len(current):
                return MISSING
            current = current[index]
        else:
            return MISSING
    return current


def to_field_pointer(path: str) -> str:
    return to_pointer(segments(path))
