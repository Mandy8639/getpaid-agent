"""Preview protection: access code on every route but /health, and per-client rate limits."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from getpaid.agent.drafter import TemplateDrafter
from getpaid.data.source import FixtureSource
from getpaid.db import make_engine, metadata
from getpaid.domain import Policy
from getpaid.main import create_app
from getpaid.security import RateLimiter

DB = "postgresql+psycopg://getpaid:getpaid@127.0.0.1:5434/getpaid_sec_test"


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    from sqlalchemy import text

    admin = make_engine(DB.rsplit("/", 1)[0] + "/getpaid", autocommit=True)
    with admin.connect() as c:
        if not c.execute(
            text("select 1 from pg_database where datname='getpaid_sec_test'")
        ).first():
            c.execute(text("create database getpaid_sec_test"))
    admin.dispose()
    eng = make_engine(DB)
    yield eng
    eng.dispose()


CODE = "preview-code-123"


@pytest.fixture
def locked(engine: Engine) -> Iterator[TestClient]:
    metadata.drop_all(engine)
    metadata.create_all(engine)
    app = create_app(
        engine=engine,
        source=FixtureSource(),
        drafter=TemplateDrafter(),
        policy=Policy(),
        access_code=CODE,
    )
    with TestClient(app) as c:
        yield c


def test_health_is_open(locked: TestClient) -> None:
    assert locked.get("/health").status_code == 200


@pytest.mark.parametrize(
    "method,path", [("post", "/runs"), ("get", "/drafts"), ("get", "/activity")]
)
def test_routes_need_the_access_code(locked: TestClient, method: str, path: str) -> None:
    assert getattr(locked, method)(path).status_code == 401
    assert (
        getattr(locked, method)(path, headers={"Authorization": "Bearer wrong"}).status_code == 401
    )
    ok = getattr(locked, method)(path, headers={"Authorization": f"Bearer {CODE}"})
    assert ok.status_code == 200


def test_runs_are_rate_limited(locked: TestClient) -> None:
    h = {"Authorization": f"Bearer {CODE}"}
    codes = [locked.post("/runs", headers=h).status_code for _ in range(7)]
    assert codes[:5] == [200] * 5 and codes[5:] == [429, 429]


def test_rate_limiter_window_slides() -> None:
    t = [0.0]
    rl = RateLimiter(limits={"/x": (2, 60)}, clock=lambda: t[0])
    assert rl.allow("ip", "/x") and rl.allow("ip", "/x") and not rl.allow("ip", "/x")
    assert rl.allow("other-ip", "/x")
    t[0] = 61
    assert rl.allow("ip", "/x")


def test_no_access_code_means_open_for_local_use(engine: Engine) -> None:
    app = create_app(
        engine=engine, source=FixtureSource(), drafter=TemplateDrafter(), policy=Policy()
    )
    assert TestClient(app).get("/activity").status_code == 200
