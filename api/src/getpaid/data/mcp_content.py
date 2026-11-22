"""Parse MCP tool results into entity dicts.

Seen in the live server (slice 2 probe): a summary line ("Found 8 invoices"), then either one
JSON object per text item (invoices) or one JSON array in a single item (payments). Validation
errors come back as plain text ("MCP error -32602 …"), and unsupported parameters as a
"WARNING: … IGNORED" line; both mean the result can't be trusted, so they raise.
"""

import json
from typing import Any


class McpContentError(ValueError):
    pass


_FAILURE_PREFIXES = ("Error", "Invalid", "MCP error", "WARNING")


def parse_entities(content: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    for item in content:
        if item.get("type") != "text":
            continue
        text = str(item.get("text", "")).strip()
        if text.startswith(_FAILURE_PREFIXES):
            raise McpContentError(text[:200])
        if not text.startswith(("{", "[")):
            continue  # summary line such as "Found 8 invoices"
        value = json.loads(text)
        values = value if isinstance(value, list) else [value]
        if not all(isinstance(v, dict) for v in values):
            raise McpContentError("entity item is not a JSON object")
        entities.extend(values)
    return entities
