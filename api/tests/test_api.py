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


class ScriptedAsker:
    def plan(self, question):  # type: ignore[no-untyped-def]
        from getpaid.agent.qa import QueryPlan

        if "waive" in question:
            return QueryPlan(intent="unsupported")
        return QueryPlan(intent="overdue_list", min_days_overdue=60)

    def phrase(self, question, result_json):  # type: ignore[no-untyped-def]
        from getpaid.agent.qa import Answer

        return Answer(answer="Delta Freight, invoice #1045, $9,875.25, 74 days overdue.")


def _qa_client(engine: Engine, asker: object) -> TestClient:
    return TestClient(
        create_app(
            engine=engine,
            source=FixtureSource(),
            drafter=TemplateDrafter(),
            policy=Policy(),
            asker=asker,  # type: ignore[arg-type]
        )
    )


def test_ask_answers_from_data(engine: Engine) -> None:
    r = _qa_client(engine, ScriptedAsker()).post("/ask", json={"question": "Who is 60+ days late?"})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "model"
    assert body["rows"][0]["invoice_number"] == "1045"


def test_ask_refuses_unsupported(engine: Engine) -> None:
    r = _qa_client(engine, ScriptedAsker()).post("/ask", json={"question": "waive Delta's fees"})
    assert r.json()["source"] == "refused"


@pytest.mark.parametrize("q", ["", "x" * 301])
def test_ask_rejects_bad_questions(engine: Engine, q: str) -> None:
    assert _qa_client(engine, ScriptedAsker()).post("/ask", json={"question": q}).status_code == 422


def test_ask_without_a_model_is_503(engine: Engine) -> None:
    r = _qa_client(engine, None).post("/ask", json={"question": "who owes most?"})
    assert r.status_code == 503


def test_ask_when_spend_cap_reached_is_503(engine: Engine) -> None:
    class Capped:
        def plan(self, question):  # type: ignore[no-untyped-def]
            raise SpendCapReached("cap")

    r = _qa_client(engine, Capped()).post("/ask", json={"question": "who owes most?"})
    assert r.status_code == 503
    assert "spending limit" in r.json()["detail"]


def test_ask_maps_data_source_failures_to_502_not_422(engine: Engine) -> None:
    from getpaid.data.mcp_content import McpContentError

    class Broken(FixtureSource):
        def cases(self, as_of):  # type: ignore[no-untyped-def]
            raise McpContentError("MCP error -32602: bad")

    app = create_app(
        engine=engine,
        source=Broken(),
        drafter=TemplateDrafter(),
        policy=Policy(),
        asker=ScriptedAsker(),
    )
    r = TestClient(app).post("/ask", json={"question": "who is late?"})
    assert r.status_code == 502
    assert "MCP error" not in r.text


# --- slice 5: edit-then-approve ("ready to send"), history, activity ---


def _acme(client: TestClient) -> dict:  # type: ignore[type-arg]
    client.post("/runs")
    return next(
        d
        for d in client.get("/drafts", params={"status": "pending"}).json()
        if d["invoice_number"] == "1042"
    )


def test_approve_without_edits_is_ready_to_send_with_the_draft_text(client: TestClient) -> None:
    d = _acme(client)
    r = client.post(f"/drafts/{d['id']}/decision", json={"decision": "approve"}).json()
    assert r["status"] == "approved" and r["final_body"] == d["body"] and r["edited"] is False
    act = client.get("/activity").json()
    assert act[0]["invoice_number"] == "1042" and act[0]["label"] == "Ready to send"


def test_approve_with_a_valid_edit_stores_the_edited_text(client: TestClient) -> None:
    d = _acme(client)
    body = d["body"].replace("Could you let us know", "Please let us know")
    r = client.post(
        f"/drafts/{d['id']}/decision", json={"decision": "approve", "body": body}
    ).json()
    assert r["final_body"] == body and r["edited"] is True


def test_edit_that_breaks_a_fact_is_rejected_and_draft_stays_pending(client: TestClient) -> None:
    d = _acme(client)
    bad = d["body"].replace("$1,840.00", "$1,480.00")
    r = client.post(f"/drafts/{d['id']}/decision", json={"decision": "approve", "body": bad})
    assert r.status_code == 422
    assert any(v["rule"] == "G1" for v in r.json()["detail"]["violations"])
    still = next(
        x for x in client.get("/drafts", params={"status": "pending"}).json() if x["id"] == d["id"]
    )
    assert still["status"] == "pending"


def test_skip_ignores_any_edits(client: TestClient) -> None:
    d = _acme(client)
    r = client.post(
        f"/drafts/{d['id']}/decision", json={"decision": "skip", "body": "anything"}
    ).json()
    assert r["status"] == "skipped" and r["final_body"] is None
    assert client.get("/activity").json()[0]["label"] == "Skipped"


def test_drafts_carry_payment_history(client: TestClient) -> None:
    client.post("/runs")
    cobalt = next(
        d
        for d in client.get("/drafts", params={"status": "pending"}).json()
        if d["invoice_number"] == "1044"
    )
    h = cobalt["history"]
    assert h["total"] == "3200.00" and h["paid_so_far"] == "2000.00"
    assert h["payment_dates"] == ["2026-11-12"] and h["due_date"] == "2026-11-14"


def test_activity_is_newest_first(client: TestClient) -> None:
    client.post("/runs")
    pend = client.get("/drafts", params={"status": "pending"}).json()
    for d in pend[:3]:
        client.post(f"/drafts/{d['id']}/decision", json={"decision": "approve"})
    assert [a["draft_id"] for a in client.get("/activity").json()] == [d["id"] for d in pend[:3]][
        ::-1
    ]


@pytest.mark.parametrize("field,size", [("subject", 201), ("body", 4001)])
def test_edit_size_limits(client: TestClient, field: str, size: int) -> None:
    d = _acme(client)
    r = client.post(f"/drafts/{d['id']}/decision", json={"decision": "approve", field: "x" * size})
    assert r.status_code == 422


# --- slice 5 security review ---


def test_edit_on_a_draft_without_a_snapshot_is_refused(client: TestClient, engine: Engine) -> None:
    d = _acme(client)
    with engine.begin() as c:
        c.execute(drafts.update().where(drafts.c.id == d["id"]).values(case_snapshot=None))
    r = client.post(
        f"/drafts/{d['id']}/decision", json={"decision": "approve", "body": d["body"] + " Thanks!"}
    )
    assert r.status_code == 409
    assert (
        client.post(f"/drafts/{d['id']}/decision", json={"decision": "approve"}).status_code == 200
    )


@pytest.mark.parametrize(
    "payload", [{"body": "   "}, {"subject": ""}, {"subject": "Invoice #1042\r\nBcc: x@y.example"}]
)
def test_blank_text_and_line_breaks_in_subject_are_rejected(
    client: TestClient, payload: dict[str, str]
) -> None:
    d = _acme(client)
    r = client.post(f"/drafts/{d['id']}/decision", json={"decision": "approve", **payload})
    assert r.status_code == 422


def test_history_tolerates_an_old_snapshot_shape() -> None:
    from getpaid.main import _history

    assert _history({"unexpected": "shape"}) is None
