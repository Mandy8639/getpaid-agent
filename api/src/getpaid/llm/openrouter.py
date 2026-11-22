"""OpenRouter client with no-data-collection routing, model failover and a hard total spend cap.

Why `data_collection: "deny"`: Intuit's developer terms (§3.1(e)) forbid letting any third
party we share Intuit data with use it to train models. OpenRouter provider routing with
`data_collection: "deny"` only uses providers that don't store or train on prompts.
`build_body` is the only place request bodies are made, and it always sets it.

Spend cap: one cumulative ledger for the whole build (default and maximum $5).
- The ledger must be created once (`make spend-init`); a missing, unreadable, negative or
  non-finite ledger fails closed.
- Before every attempt (including failovers), under a file lock, the reserve is booked
  if spent + reserve stays below the cap; otherwise SpendCapReached and no call is made.
- After the attempt the booking is settled: real cost when the reply reports a usable one;
  the reserve is kept when the request may have billed without reporting a cost (5xx,
  timeout, other errors, unusable cost); refunded only for 429 and "no endpoints".
- Backstop outside this code: set a $5 credit limit on the OpenRouter key itself.
"""

from __future__ import annotations

import fcntl
import json
import math
import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

API_URL = "https://openrouter.ai/api/v1/chat/completions"
APP_TITLE = "getpaid-agent"
UNBILLED_OUTCOMES = {"rate_limited", "no_endpoints"}

Message = dict[str, str]


class SpendCapReached(RuntimeError):
    """Raised instead of making a call that could take total spend to or past the cap."""


def _usable_cost(raw: object) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        return None
    value = float(raw)
    return value if math.isfinite(value) and value >= 0 else None


@dataclass
class Ledger:
    path: Path
    cap_usd: float
    reserve_usd: float = 0.05

    @property
    def _lock_path(self) -> Path:
        return self.path.with_name(self.path.name + ".lock")

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path, "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def create(self) -> None:
        """Start a new ledger at $0. Refuses to overwrite an existing one."""
        with self._locked():
            if self.path.exists():
                raise FileExistsError(f"{self.path} already exists; spend is never reset")
            self._write(0.0)

    def _read(self) -> float:
        try:
            raw = self.path.read_text()
        except FileNotFoundError as e:
            raise SpendCapReached(
                f"no spend ledger at {self.path}; run `make spend-init` once"
            ) from e
        try:
            value = json.loads(raw)["total_usd"]
        except (ValueError, KeyError, TypeError) as e:
            raise SpendCapReached(f"spend ledger {self.path} is unreadable") from e
        total = _usable_cost(value)
        if total is None:
            raise SpendCapReached(f"spend ledger {self.path} holds an invalid total: {value!r}")
        return total

    def _write(self, total: float) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".ledger-", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump({"total_usd": round(total, 6)}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def spent(self) -> float:
        with self._locked():
            return self._read()

    def check(self) -> None:
        with self._locked():
            self._check(self._read())

    def _check(self, spent: float) -> None:
        if spent + self.reserve_usd >= self.cap_usd:
            raise SpendCapReached(
                f"total spend ${spent:.4f} + reserve ${self.reserve_usd:.2f} "
                f"reaches the ${self.cap_usd:.2f} cap"
            )

    def reserve(self) -> None:
        """Book the reserve before a call, or raise if that would reach the cap."""
        with self._locked():
            spent = self._read()
            self._check(spent)
            self._write(spent + self.reserve_usd)

    def settle(self, actual_usd: float | None, billed: bool) -> None:
        """Replace the booked reserve with the real cost (or keep it when cost is unknown)."""
        if billed and actual_usd is None:
            return
        charge = actual_usd if (billed and actual_usd is not None) else 0.0
        with self._locked():
            self._write(max(0.0, self._read() - self.reserve_usd + charge))


@dataclass
class Attempt:
    model: str
    # ok | rate_limited | server_error | timeout | network | no_endpoints | bad_json | http_<code>
    outcome: str
    latency_ms: int
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None
    detail: str = ""


@dataclass
class Completion[T: BaseModel]:
    value: T | None
    model: str
    attempts: list[Attempt]


def build_body(
    model: str, messages: list[Message], schema: type[BaseModel], *, max_tokens: int = 800
) -> dict[str, Any]:
    """The only constructor of request bodies. Always denies provider data collection."""
    json_schema = schema.model_json_schema()
    # Strict structured output needs every property listed as required (nullable if optional).
    json_schema["required"] = list(json_schema.get("properties", {}))
    return {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema.__name__,
                "strict": True,
                "schema": json_schema,
            },
        },
        "usage": {"include": True},
        "provider": {"data_collection": "deny"},
    }


def _parse[T: BaseModel](content: str, schema: type[T]) -> T:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    return schema.model_validate(json.loads(text))


@dataclass
class OpenRouterClient:
    api_key: str = field(repr=False)
    models: list[str]
    ledger: Ledger
    max_attempts: int = 4
    timeout_s: float = 60.0
    max_tokens: int = 800
    http: httpx.Client = field(default_factory=httpx.Client, repr=False)

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("OPENROUTER_API_KEY is not set")
        if not self.models:
            raise ValueError("no models configured (OPENROUTER_MODELS)")

    def close(self) -> None:
        self.http.close()

    def _attempt[T: BaseModel](
        self, model: str, messages: list[Message], schema: type[T]
    ) -> tuple[Attempt, T | None]:
        body = build_body(model, messages, schema, max_tokens=self.max_tokens)
        headers = {"Authorization": f"Bearer {self.api_key}", "X-Title": APP_TITLE}
        t0 = time.monotonic()

        def ms() -> int:
            return int((time.monotonic() - t0) * 1000)

        try:
            r = self.http.post(API_URL, json=body, headers=headers, timeout=self.timeout_s)
        except httpx.TimeoutException:
            return Attempt(model, "timeout", ms()), None
        except httpx.TransportError as e:
            return Attempt(model, "network", ms(), detail=type(e).__name__), None
        if r.status_code == 429:
            return Attempt(model, "rate_limited", ms()), None
        if r.status_code >= 500:
            return Attempt(model, "server_error", ms(), detail=str(r.status_code)), None
        if r.status_code == 404 and "no endpoints" in r.text.lower():
            return Attempt(model, "no_endpoints", ms()), None
        if r.status_code != 200:
            return Attempt(model, f"http_{r.status_code}", ms()), None
        try:
            data = r.json()
        except ValueError:
            return Attempt(model, "bad_json", ms(), detail="non-JSON response body"), None
        if not isinstance(data, dict):
            return Attempt(model, "bad_json", ms(), detail="response is not an object"), None
        if "error" in data:  # OpenRouter can return 200 with an upstream error
            err = data["error"]
            code = err.get("code") if isinstance(err, dict) else None
            outcome = "rate_limited" if code == 429 else "server_error"
            return Attempt(model, outcome, ms(), detail=f"upstream error code={code}"), None
        raw_usage = data.get("usage")
        usage: dict[str, Any] = raw_usage if isinstance(raw_usage, dict) else {}
        attempt = Attempt(
            model,
            "ok",
            ms(),
            int(usage.get("prompt_tokens") or 0),
            int(usage.get("completion_tokens") or 0),
            _usable_cost(usage.get("cost")),
        )
        try:
            content = data["choices"][0]["message"]["content"] or ""
            return attempt, _parse(content, schema)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError) as e:
            attempt.outcome, attempt.detail = "bad_json", type(e).__name__
            return attempt, None

    def complete[T: BaseModel](self, messages: list[Message], schema: type[T]) -> Completion[T]:
        attempts: list[Attempt] = []
        for i in range(self.max_attempts):
            model = self.models[i % len(self.models)]
            self.ledger.reserve()
            attempt, value = self._attempt(model, messages, schema)
            attempts.append(attempt)
            self.ledger.settle(attempt.cost_usd, billed=attempt.outcome not in UNBILLED_OUTCOMES)
            if value is not None:
                return Completion(value, model, attempts)
        return Completion(None, "none", attempts)
