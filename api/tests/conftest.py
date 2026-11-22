"""Test-wide safety: no real outbound network, no real API key, and no local .env.

pytest-socket (configured in pyproject addopts) blocks sockets except to 127.0.0.1/::1,
so respx mocks (which never open sockets) and local Postgres still work.
"""

from collections.abc import Iterator

import pytest

from getpaid.config import Settings


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for var in ("OPENROUTER_API_KEY", "OPENROUTER_MODELS", "TOTAL_SPEND_CAP_USD"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    yield
