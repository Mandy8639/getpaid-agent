import pytest

from getpaid import e2e_reset
from getpaid.config import get_settings


def test_refuses_non_e2e_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://getpaid:getpaid@127.0.0.1:5434/getpaid"
    )
    get_settings.cache_clear()
    with pytest.raises(SystemExit, match="refusing"):
        e2e_reset.main()
    get_settings.cache_clear()


def test_resets_e2e_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://getpaid:getpaid@127.0.0.1:5434/getpaid_unit_e2e"
    )
    get_settings.cache_clear()
    e2e_reset.main()
    get_settings.cache_clear()


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://u:p@db.example:5432/getpaid_e2e",
        'postgresql+psycopg://u:p@127.0.0.1:5434/x"; drop database getpaid; --_e2e',
    ],
)
def test_refuses_remote_or_odd_names(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    with pytest.raises(SystemExit, match="refusing"):
        e2e_reset.main()
    get_settings.cache_clear()
