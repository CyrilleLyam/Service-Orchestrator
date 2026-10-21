from __future__ import annotations

import json
import math
from typing import Any

from service_orchestrator.shared.domain.validation import FieldError


def check_json_document(value: Any, *, max_bytes: int, max_depth: int) -> list[FieldError]:
    stack: list[tuple[Any, int]] = [(value, 1)]
    while stack:
        node, depth = stack.pop()
        if depth > max_depth:
            return [FieldError("", "too_deep", f"Document nesting exceeds {max_depth} levels")]
        if isinstance(node, dict):
            if not all(isinstance(key, str) for key in node):
                return [FieldError("", "invalid_json", "Object keys must be strings")]
            stack.extend((child, depth + 1) for child in node.values())
        elif isinstance(node, list):
            stack.extend((child, depth + 1) for child in node)
        elif isinstance(node, float):
            if not math.isfinite(node):
                return [FieldError("", "invalid_json", "Numbers must be finite")]
        elif not (node is None or isinstance(node, str | int | bool)):
            return [FieldError("", "invalid_json", f"Unsupported value type {type(node).__name__}")]

    size = len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())
    if size > max_bytes:
        return [FieldError("", "too_large", f"Document is {size} bytes; the limit is {max_bytes}")]
    return []
