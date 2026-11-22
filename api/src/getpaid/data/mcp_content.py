"""Parse MCP tool results: a summary text item, then one JSON entity per text item."""

import json
from typing import Any


class McpContentError(ValueError):
    pass


def parse_entities(content: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    for item in content:
        if item.get("type") != "text":
            continue
        text = str(item.get("text", "")).strip()
        if text.startswith(("Error", "Invalid")):
            raise McpContentError(text[:200])
        if not text.startswith(("{", "[")):
            continue  # summary line such as "Found 8 invoices"
        value = json.loads(text)
        if not isinstance(value, dict):
            raise McpContentError("entity item is not a JSON object")
        entities.append(value)
    return entities
