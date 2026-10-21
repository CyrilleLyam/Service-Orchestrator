from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DocumentLimits:
    max_definition_bytes: int = 256 * 1024
    max_definition_depth: int = 64
    max_payload_bytes: int = 64 * 1024
    max_payload_depth: int = 16
