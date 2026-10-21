from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace


@dataclass(frozen=True, slots=True)
class FieldError:
    path: str
    code: str
    message: str
    rule_id: str | None = None

    def under(self, prefix: str) -> FieldError:
        return replace(self, path=prefix + self.path)


def escape_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def unescape_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def to_pointer(segments: Iterable[str | int]) -> str:
    return "".join("/" + escape_token(str(segment)) for segment in segments)


def from_pointer(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise ValueError(f"Invalid JSON Pointer: {pointer!r}")
    return [unescape_token(token) for token in pointer[1:].split("/")]


def dedupe(errors: Iterable[FieldError]) -> list[FieldError]:
    seen: set[tuple[str, str]] = set()
    unique = []
    for error in errors:
        key = (error.path, error.code)
        if key not in seen:
            seen.add(key)
            unique.append(error)
    return unique
