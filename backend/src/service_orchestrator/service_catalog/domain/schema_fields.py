from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from service_orchestrator.shared.domain.field_path import segments
from service_orchestrator.shared.domain.validation import from_pointer

_MAX_EXPANSION = 200


def field_exists(schema: Mapping[str, Any], path: str) -> bool:
    nodes: list[Any] = [schema]
    for segment in segments(path):
        nodes = [child for node in nodes for child in _children(schema, node, segment)]
        if not nodes:
            return False
    return True


def _children(root: Mapping[str, Any], node: Any, segment: str) -> list[Any]:
    children = []
    for candidate in _applicable_subschemas(root, node):
        properties = candidate.get("properties", {})
        if segment in properties:
            children.append(properties[segment])
        if segment.isdigit():
            prefix = candidate.get("prefixItems", [])
            if int(segment) < len(prefix):
                children.append(prefix[int(segment)])
            elif isinstance(candidate.get("items"), dict):
                children.append(candidate["items"])
    return children


def _applicable_subschemas(root: Mapping[str, Any], node: Any) -> list[Mapping[str, Any]]:
    found: list[Mapping[str, Any]] = []
    stack = [node]
    while stack and len(found) < _MAX_EXPANSION:
        current = stack.pop()
        if not isinstance(current, Mapping):
            continue
        found.append(current)
        ref = current.get("$ref")
        if isinstance(ref, str) and (ref == "#" or ref.startswith("#/")):
            stack.append(_resolve(root, ref))
        for keyword in ("allOf", "anyOf", "oneOf"):
            stack.extend(current.get(keyword, []))
        stack.extend(current[keyword] for keyword in ("then", "else") if keyword in current)
    return found


def _resolve(root: Mapping[str, Any], ref: str) -> Any:
    target: Any = root
    for token in from_pointer(ref[1:]):
        if isinstance(target, Mapping) and token in target:
            target = target[token]
        else:
            return None
    return target
