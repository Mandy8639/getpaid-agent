"""API against real Postgres (make up). Runs fixture invoices, lists drafts, records decisions."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from getpaid.agent.drafter import TemplateDrafter
from getpaid.data.source import FixtureSource
from getpaid.db import approvals, drafts, make_engine, metadata
from getpaid.domain import Policy
from getpaid.llm.openrouter import SpendCapReached
from getpaid.main import create_app

TEST_DB = "postgresql+psycopg://getpaid:getpaid@127.0.0.1:5434/getpaid_test"


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    admin = make_engine(TEST_DB.rsplit("/", 1)[0] + "/getpaid", autocommit=True)
    with admin.connect() as c:
        if not c.execute(text("select 1 from pg_database where datname='getpaid_test'")).first():
            c.execute(text("create database getpaid_test"))
    admin.dispose()
    eng = make_engine(TEST_DB)
    yield eng
    eng.dispose()


@pytest.fixture
def client(engine: Engine) -> Iterator[TestClient]:
    metadata.drop_all(engine)
    metadata.create_all(engine)
    app = create_app(
        engine=engine, source=FixtureSource(), drafter=TemplateDrafter(), policy=Policy()
    )
    with TestClient(app) as c:
        yield c


def test_run_creates_drafts_and_holds(client: TestClient) -> None:
    r = client.post("/runs").json()
    assert r == {"pending": 5, "held": 3}
    held = client.get("/drafts", params={"status": "held"}).json()
    assert {d["hold_reason"] for d in held} == {"paid", "disputed", "not_overdue"}


def test_rerun_does_not_duplicate_undecided_drafts(client: TestClient) -> None:
    client.post("/runs")
    assert client.post("/runs").json() == {"pending": 0, "held": 0}
    assert len(client.get("/drafts", params={"status": "pending"}).json()) == 5


def test_rerun_after_a_decision_does_not_redraft_the_same_invoice(client: TestClient) -> None:
    client.post("/runs")
    d = client.get("/drafts/next").json()
    client.post(f"/drafts/{d['id']}/decision", json={"decision": "approve"})
    assert client.post("/runs").json() == {"pending": 0, "held": 0}


class Exploding:
    def draft(self, case, decision, policy, feedback):  # type: ignore[no-untyped-def]
        raise RuntimeError("model provider down")


def test_drafter_crash_holds_that_invoice_instead_of_failing_the_run(engine: Engine) -> None:
    metadata.drop_all(engine)
    metadata.create_all(engine)
    app = create_app(engine=engine, source=FixtureSource(), drafter=Exploding(), policy=Policy())
    with TestClient(app) as c:
        assert c.post("/runs").json() == {"pending": 0, "held": 8}
        held = c.get("/drafts", params={"status": "held"}).json()
        assert sum(d["hold_reason"] == "drafter_failed" for d in held) == 5


def test_next_returns_largest_overdue_first_with_facts(client: TestClient) -> None:
    client.post("/runs")
    d = client.get("/drafts/next").json()
    assert d["invoice_number"] == "1045"  # $9,875.25 x 74 days ranks first
    assert d["balance"] == "9875.25"
    assert d["days_overdue"] == 74
    assert d["guardrail_passed"] is True
    assert "#1045" in d["body"]


def test_approve_records_exactly_one_approval(client: TestClient, engine: Engine) -> None:
    client.post("/runs")
    d = client.get("/drafts/next").json()
    r = client.post(f"/drafts/{d['id']}/decision", json={"decision": "approve"})
    assert r.status_code == 200
    assert r.json()["status"] == "approved"
    with engine.connect() as c:
        rows = c.execute(approvals.select().where(approvals.c.draft_id == d["id"])).all()
    assert len(rows) == 1
    assert client.get("/drafts/next").json()["id"] != d["id"]


def test_second_decision_is_rejected_with_409(client: TestClient) -> None:
    client.post("/runs")
    d = client.get("/drafts/next").json()
    assert client.post(f"/drafts/{d['id']}/decision", json={"decision": "skip"}).status_code == 200
    again = client.post(f"/drafts/{d['id']}/decision", json={"decision": "approve"})
    assert again.status_code == 409


def test_held_draft_cannot_be_approved(client: TestClient) -> None:
    client.post("/runs")
    held = client.get("/drafts", params={"status": "held"}).json()[0]
    r = client.post(f"/drafts/{held['id']}/decision", json={"decision": "approve"})
    assert r.status_code == 409


def test_unknown_draft_is_404_and_bad_input_is_422(client: TestClient) -> None:
    assert client.post("/drafts/999999/decision", json={"decision": "approve"}).status_code == 404
    client.post("/runs")
    d = client.get("/drafts/next").json()
    assert client.post(f"/drafts/{d['id']}/decision", json={"decision": "send"}).status_code == 422
    bad = client.get("/drafts", params={"status": "'; drop table drafts; --"})
    assert bad.status_code == 422


def test_next_is_204_when_queue_is_empty(client: TestClient) -> None:
    assert client.get("/drafts/next").status_code == 204


class CapAfterTwo:
    """Drafts the first two cases, then behaves as if the spend cap was reached."""

    def __init__(self) -> None:
        self.n = 0
        self.inner = TemplateDrafter()

    def draft(self, case, decision, policy, feedback):  # type: ignore[no-untyped-def]
        self.n += 1
        if self.n > 2:
            raise SpendCapReached("cap")
        return self.inner.draft(case, decision, policy, feedback)


def test_spend_cap_mid_run_keeps_earlier_drafts_and_holds_the_rest(engine: Engine) -> None:
    metadata.drop_all(engine)
    metadata.create_all(engine)
    app = create_app(engine=engine, source=FixtureSource(), drafter=CapAfterTwo(), policy=Policy())
    with TestClient(app) as c:
        r = c.post("/runs")
        assert r.status_code == 200
        assert r.json() == {"pending": 2, "held": 6}
        held = c.get("/drafts", params={"status": "held"}).json()
        assert sum(d["hold_reason"] == "spend_cap" for d in held) == 3


def test_open_draft_per_invoice_is_unique_in_the_database(
    client: TestClient, engine: Engine
) -> None:
    client.post("/runs")
    with engine.connect() as c:
        row = c.execute(drafts.select().where(drafts.c.status == "pending").limit(1)).first()
    assert row is not None
    with pytest.raises(IntegrityError), engine.begin() as c:
        values = dict(row._mapping)
        values.pop("id")
        c.execute(drafts.insert().values(**values))
