from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pytest_socket import SocketBlockedError, SocketConnectBlockedError

from getpaid import spend_init
from getpaid.config import Settings, get_settings
from getpaid.llm.factory import client_from_settings
from getpaid.main import app


def test_health() -> None:
    assert TestClient(app).get("/health").json() == {"status": "ok"}


def test_real_network_is_blocked_in_tests() -> None:
    with pytest.raises((SocketBlockedError, SocketConnectBlockedError)):
        httpx.Client().get("https://93.184.215.14/")


def test_cap_above_five_dollars_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(total_spend_cap_usd=5.01)


def test_api_key_is_secret_in_settings() -> None:
    assert "sk-x" not in repr(Settings(openrouter_api_key="sk-x"))


def test_spend_init_creates_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPEND_LEDGER_PATH", str(tmp_path / "ledger.json"))
    get_settings.cache_clear()
    spend_init.main()
    with pytest.raises(FileExistsError):
        spend_init.main()
    get_settings.cache_clear()


def test_client_from_settings_uses_total_cap(tmp_path: Path) -> None:
    s = Settings(
        openrouter_api_key="k",
        openrouter_models="a/x, b/y ,",
        total_spend_cap_usd=5.0,
        spend_ledger_path=tmp_path / "l.json",
    )
    c = client_from_settings(s)
    assert c.models == ["a/x", "b/y"]
    assert c.ledger.cap_usd == 5.0


def test_client_from_settings_without_key_refuses(tmp_path: Path) -> None:
    s = Settings(openrouter_models="a/x", spend_ledger_path=tmp_path / "l.json")
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        client_from_settings(s)
