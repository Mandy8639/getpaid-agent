"""OpenRouter client: no-data-collection routing, failover, and the hard total spend cap."""

import contextlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
import respx
from pydantic import BaseModel

from getpaid.llm.openrouter import (
    API_URL,
    Ledger,
    OpenRouterClient,
    SpendCapReached,
    build_body,
)


class Reply(BaseModel):
    text: str


MSGS = [{"role": "user", "content": "x"}]


def ok(cost: float = 0.01, text: str = "hi") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": json.dumps({"text": text})}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": cost},
        },
    )


def ledger(tmp_path: Path, cap: float = 5.0, reserve: float = 0.05, total: float = 0.0) -> Ledger:
    led = Ledger(tmp_path / "ledger.json", cap_usd=cap, reserve_usd=reserve)
    if not led.path.exists():
        led.create()
    if total:
        led.path.write_text(json.dumps({"total_usd": total}))
    return led


def make(
    tmp_path: Path, models: list[str], cap: float = 5.0, reserve: float = 0.05, total: float = 0.0
) -> OpenRouterClient:
    return OpenRouterClient(
        api_key="test-key", models=models, ledger=ledger(tmp_path, cap, reserve, total)
    )


def sent_bodies(route: respx.Route) -> list[dict[str, object]]:
    return [json.loads(c.request.content) for c in route.calls]


# --- data_collection: "deny" on every request (Intuit terms §3.1(e)) ---


def test_build_body_always_denies_data_collection() -> None:
    body = build_body("m", MSGS, Reply)
    assert body["provider"]["data_collection"] == "deny"


@respx.mock
def test_every_attempt_including_failovers_denies_data_collection(tmp_path: Path) -> None:
    route = respx.post(API_URL).mock(side_effect=[httpx.Response(429), httpx.Response(503), ok()])
    make(tmp_path, ["a", "b", "c"]).complete(MSGS, Reply)
    bodies = sent_bodies(route)
    assert len(bodies) == 3
    assert all(b["provider"]["data_collection"] == "deny" for b in bodies)  # type: ignore[index]


# --- failover ---


@respx.mock
def test_fails_over_in_order_on_429_5xx_and_timeout(tmp_path: Path) -> None:
    route = respx.post(API_URL).mock(
        side_effect=[httpx.Response(429), httpx.Response(502), httpx.TimeoutException("t"), ok()]
    )
    result = make(tmp_path, ["a", "b", "c", "d"]).complete(MSGS, Reply)
    assert [b["model"] for b in sent_bodies(route)] == ["a", "b", "c", "d"]
    assert [a.outcome for a in result.attempts] == ["rate_limited", "server_error", "timeout", "ok"]
    assert result.model == "d"
    assert result.value == Reply(text="hi")


@respx.mock
def test_200_with_error_object_and_no_endpoints_fail_over(tmp_path: Path) -> None:
    route = respx.post(API_URL).mock(
        side_effect=[
            httpx.Response(200, json={"error": {"code": 429, "message": "upstream"}}),
            httpx.Response(
                404, json={"error": {"message": "No endpoints found matching your data policy"}}
            ),
            ok(),
        ]
    )
    result = make(tmp_path, ["a", "b", "c"]).complete(MSGS, Reply)
    assert [a.outcome for a in result.attempts] == ["rate_limited", "no_endpoints", "ok"]
    assert len(route.calls) == 3


@respx.mock
def test_bad_json_fails_over(tmp_path: Path) -> None:
    bad = httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}], "usage": {}})
    respx.post(API_URL).mock(side_effect=[bad, ok()])
    result = make(tmp_path, ["a", "b"]).complete(MSGS, Reply)
    assert [a.outcome for a in result.attempts] == ["bad_json", "ok"]


@respx.mock
def test_fenced_json_is_accepted(tmp_path: Path) -> None:
    fenced = httpx.Response(
        200, json={"choices": [{"message": {"content": '```json\n{"text": "yo"}\n```'}}]}
    )
    respx.post(API_URL).mock(return_value=fenced)
    assert make(tmp_path, ["a"]).complete(MSGS, Reply).value == Reply(text="yo")


@respx.mock
def test_all_attempts_fail_returns_none_value(tmp_path: Path) -> None:
    respx.post(API_URL).mock(return_value=httpx.Response(503))
    client = make(tmp_path, ["a", "b"])
    client.max_attempts = 3
    result = client.complete(MSGS, Reply)
    assert result.value is None
    assert len(result.attempts) == 3


@respx.mock
def test_malformed_200_replies_fail_over(tmp_path: Path) -> None:
    respx.post(API_URL).mock(
        side_effect=[
            httpx.Response(200, text="<html>oops</html>"),
            httpx.Response(200, json={"error": "string error"}),
            ok(),
        ]
    )
    result = make(tmp_path, ["a", "b", "c"]).complete(MSGS, Reply)
    assert [a.outcome for a in result.attempts] == ["bad_json", "server_error", "ok"]


@respx.mock
def test_bad_json_detail_does_not_echo_model_output(tmp_path: Path) -> None:
    secretish = httpx.Response(
        200, json={"choices": [{"message": {"content": '{"wrong": "Acme owes 1234.56"}'}}]}
    )
    respx.post(API_URL).mock(side_effect=[secretish, ok()])
    result = make(tmp_path, ["a", "b"]).complete(MSGS, Reply)
    assert "1234.56" not in result.attempts[0].detail


def test_api_key_not_in_repr(tmp_path: Path) -> None:
    assert "test-key" not in repr(make(tmp_path, ["a"]))


@respx.mock
def test_other_http_error_and_network_error_fail_over(tmp_path: Path) -> None:
    respx.post(API_URL).mock(
        side_effect=[httpx.Response(400, text="bad"), httpx.ConnectError("down"), ok()]
    )
    result = make(tmp_path, ["a", "b", "c"]).complete(MSGS, Reply)
    assert [a.outcome for a in result.attempts] == ["http_400", "network", "ok"]


# --- hard total spend cap ---


@respx.mock
def test_cost_is_recorded_cumulatively_across_clients(tmp_path: Path) -> None:
    respx.post(API_URL).mock(return_value=ok(cost=0.25))
    make(tmp_path, ["a"]).complete(MSGS, Reply)
    make(tmp_path, ["a"]).complete(MSGS, Reply)
    assert ledger(tmp_path).spent() == pytest.approx(0.50)


@respx.mock
def test_cap_blocks_before_calling_when_reserve_would_reach_cap(tmp_path: Path) -> None:
    route = respx.post(API_URL).mock(return_value=ok())
    with pytest.raises(SpendCapReached):
        make(tmp_path, ["a"], cap=5.0, reserve=0.05, total=4.96).complete(MSGS, Reply)
    assert len(route.calls) == 0


@respx.mock
def test_cap_blocks_at_exactly_the_cap(tmp_path: Path) -> None:
    route = respx.post(API_URL).mock(return_value=ok())
    with pytest.raises(SpendCapReached):
        make(tmp_path, ["a"], cap=5.0, reserve=0.0, total=5.0).complete(MSGS, Reply)
    assert len(route.calls) == 0


@respx.mock
def test_cap_checked_before_each_failover_attempt(tmp_path: Path) -> None:
    costly_bad = httpx.Response(
        200, json={"choices": [{"message": {"content": "x"}}], "usage": {"cost": 0.97}}
    )
    route = respx.post(API_URL).mock(side_effect=[costly_bad, ok()])
    with pytest.raises(SpendCapReached):
        make(tmp_path, ["a", "b"], cap=1.0, reserve=0.05).complete(MSGS, Reply)
    assert len(route.calls) == 1


@pytest.mark.parametrize(
    "raw",
    [
        "{not json",
        '{"total_usd": NaN}',
        '{"total_usd": -100}',
        '{"total_usd": Infinity}',
        '{"total_usd": "1"}',
        "{}",
    ],
)
def test_bad_ledger_values_fail_closed(tmp_path: Path, raw: str) -> None:
    led = ledger(tmp_path)
    led.path.write_text(raw)
    with pytest.raises(SpendCapReached):
        led.check()


def test_missing_ledger_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(SpendCapReached, match="spend-init"):
        Ledger(tmp_path / "ledger.json", cap_usd=5.0).check()


def test_create_refuses_to_reset_an_existing_ledger(tmp_path: Path) -> None:
    led = ledger(tmp_path, total=1.5)
    with pytest.raises(FileExistsError):
        led.create()
    assert led.spent() == pytest.approx(1.5)


@respx.mock
@pytest.mark.parametrize(
    "usage", [{}, {"cost": None}, {"cost": "abc"}, {"cost": float("nan")}, {"cost": -3}]
)
def test_ok_reply_with_unusable_cost_is_charged_the_reserve(
    tmp_path: Path, usage: dict[str, object]
) -> None:
    body = {"choices": [{"message": {"content": json.dumps({"text": "hi"})}}], "usage": usage}
    respx.post(API_URL).mock(return_value=httpx.Response(200, content=json.dumps(body)))
    client = make(tmp_path, ["a"], reserve=0.05)
    assert client.complete(MSGS, Reply).value == Reply(text="hi")
    assert client.ledger.spent() == pytest.approx(0.05)


@respx.mock
def test_failures_that_may_bill_keep_the_reserve_and_unbilled_ones_refund(tmp_path: Path) -> None:
    respx.post(API_URL).mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(503),
            httpx.TimeoutException("t"),
            ok(cost=0.01),
        ]
    )
    client = make(tmp_path, ["a"], reserve=0.05)
    client.complete(MSGS, Reply)
    # 429 refunded; 503 and timeout keep $0.05 each; ok settles to its real $0.01
    assert client.ledger.spent() == pytest.approx(0.11)


@respx.mock
def test_parallel_calls_never_lose_spend(tmp_path: Path) -> None:
    respx.post(API_URL).mock(return_value=ok(cost=0.1))
    client = make(tmp_path, ["a"], cap=5.0, reserve=0.05)
    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(lambda _: client.complete(MSGS, Reply), range(20)))
    assert client.ledger.spent() == pytest.approx(2.0)


@respx.mock
def test_parallel_calls_cannot_overshoot_the_cap(tmp_path: Path) -> None:
    route = respx.post(API_URL).mock(return_value=ok(cost=0.05))
    client = make(tmp_path, ["a"], cap=0.5, reserve=0.05)
    client.max_attempts = 1

    def call(_: int) -> None:
        with contextlib.suppress(SpendCapReached):
            client.complete(MSGS, Reply)

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(call, range(30)))
    assert client.ledger.spent() < 0.5
    assert len(route.calls) <= 9


# --- config ---


def test_missing_api_key_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        OpenRouterClient(api_key="", models=["a"], ledger=ledger(tmp_path))


def test_no_models_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="OPENROUTER_MODELS"):
        OpenRouterClient(api_key="k", models=[], ledger=ledger(tmp_path))


@respx.mock
def test_api_key_sent_as_bearer_and_never_in_body(tmp_path: Path) -> None:
    route = respx.post(API_URL).mock(return_value=ok())
    make(tmp_path, ["a"]).complete(MSGS, Reply)
    req = route.calls[0].request
    assert req.headers["Authorization"] == "Bearer test-key"
    assert b"test-key" not in req.content
