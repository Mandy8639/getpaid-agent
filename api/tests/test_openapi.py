"""The committed web/openapi.json must match the API (the web types are generated from it)."""

import json

from getpaid.export_openapi import OUT, schema


def test_committed_openapi_schema_is_current() -> None:
    assert json.loads(OUT.read_text()) == json.loads(json.dumps(schema(), sort_keys=True)), (
        "API changed: run `make types` and commit web/openapi.json and web/src/lib/api-types.ts"
    )


def test_schema_has_the_dashboard_endpoints() -> None:
    paths = schema()["paths"]
    assert isinstance(paths, dict)
    want = {"/runs", "/drafts", "/drafts/next", "/drafts/{draft_id}/decision", "/activity", "/ask"}
    assert want <= set(paths)
