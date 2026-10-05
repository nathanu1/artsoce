"""The single path every model call takes (spec O-1).

``LLMGateway.run(task, variables)`` renders the versioned template, consults the
exact-request ledger, enforces the budget, calls the provider with bounded retries, validates
the JSON output against the task schema (plus an optional semantic check), performs bounded
repair attempts, and records everything. It never invents an output: if repairs fail it
raises ``TaskFailed``.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from ..db import sha256_text, stable_json
from ..prompting import PromptRegistry, PromptTemplate
from .base import (
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ProviderError,
    ProviderRefusal,
    ProviderTruncated,
    ReplayMiss,
    TaskFailed,
    estimate_tokens,
)
from .ledger import CallLedger
from .pricing import PriceTable
from .schema import strict_json_schema

T = TypeVar("T", bound=BaseModel)

Validator = Callable[[Any], list[str]]


@dataclass
class TaskResult(Generic[T]):
    output: T
    call_ids: list[int]
    cached: bool
    raw: str
    template_id: str


def extract_json(text: str) -> Any:
    """Parse the first JSON object in ``text`` (tolerates code fences and leading prose)."""

    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in output")
    decoder = json.JSONDecoder()
    obj, _ = decoder.raw_decode(text[start:])
    return obj


@dataclass
class GatewaySettings:
    model: str
    max_output_tokens: int | None = None
    effort: str | None = None
    temperature: float | None = None
    max_retries: int = 2
    max_validation_repairs: int = 1
    backoff_s: float = 2.0
    task_overrides: dict[str, dict[str, Any]] | None = None


class LLMGateway:
    def __init__(
        self,
        provider: LLMProvider,
        registry: PromptRegistry,
        ledger: CallLedger,
        budget: Any,
        settings: GatewaySettings,
        *,
        pricing: PriceTable | None = None,
        step_getter: Callable[[], int | None] | None = None,
        replay: bool = False,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.provider = provider
        self.registry = registry
        self.ledger = ledger
        self.budget = budget
        self.settings = settings
        self.pricing = pricing or PriceTable(None)
        self.step_getter = step_getter or (lambda: None)
        self.replay = replay
        self.sleep = sleep

    # ------------------------------------------------------------------ public
    def run(
        self,
        task: str,
        variables: dict[str, Any],
        *,
        agent_id: str | None = None,
        sim_time: datetime | None = None,
        purpose: str | None = None,
        validate: Validator | None = None,
    ) -> TaskResult[Any]:
        template = self.registry.get(task)
        system, prompt = template.render(variables)
        schema = strict_json_schema(template.output_model)
        knobs = self._knobs(template)
        call_ids: list[int] = []
        all_errors: list[str] = []
        attempt_prompt = prompt
        any_cached = True
        for attempt in range(1 + self.settings.max_validation_repairs):
            request = LLMRequest(
                task=task,
                template_id=template.template_id,
                template_hash=template.sha256,
                system=system,
                prompt=attempt_prompt,
                output_schema=schema,
                model=self.settings.model,
                max_output_tokens=knobs["max_output_tokens"],
                effort=knobs["effort"],
                temperature=knobs["temperature"],
                agent_id=agent_id,
                purpose=purpose or task,
                sim_time=sim_time,
                variables=variables,
                attempt_kind="initial" if attempt == 0 else "repair",
            )
            raw, call_id, cached = self._call(request)
            call_ids.append(call_id)
            any_cached = any_cached and cached
            parsed, errors = self._validate(raw, template.output_model, validate)
            self._mark(call_id, parsed, errors)
            if not errors:
                return TaskResult(parsed, call_ids, any_cached, raw, template.template_id)
            all_errors.extend(errors)
            attempt_prompt = (
                prompt
                + "\n\nYour previous answer was not usable:\n"
                + "\n".join(f"- {e}" for e in errors)
                + f"\nPrevious answer: {raw.strip()[:2000]}\nReturn corrected JSON only."
            )
        raise TaskFailed(task, "output invalid after bounded repairs", call_ids=call_ids, errors=all_errors)

    # ------------------------------------------------------------------ internals
    def _knobs(self, template: PromptTemplate) -> dict[str, Any]:
        knobs = {
            "max_output_tokens": template.max_output_tokens,
            "effort": template.effort,
            "temperature": self.settings.temperature,
        }
        if self.settings.max_output_tokens is not None:
            knobs["max_output_tokens"] = max(knobs["max_output_tokens"], self.settings.max_output_tokens)
        if self.settings.effort is not None:
            knobs["effort"] = self.settings.effort
        override = (self.settings.task_overrides or {}).get(template.id, {})
        for key in ("max_output_tokens", "effort", "temperature"):
            if key in override:
                knobs[key] = override[key]
        return knobs

    def request_hash(self, request: LLMRequest) -> str:
        return sha256_text(
            stable_json(
                {
                    # The provider is not part of the key: the scope (run ID) already isolates
                    # runs, and replay must match the source run's requests (spec K-4).
                    "model": request.model,
                    "max_output_tokens": request.max_output_tokens,
                    "effort": request.effort,
                    "temperature": request.temperature,
                    "template": request.template_id,
                    "template_hash": request.template_hash,
                    "system": request.system,
                    "prompt": request.prompt,
                    "schema": request.output_schema,
                    "agent_id": request.agent_id,
                }
            )
        )

    def _call(self, request: LLMRequest) -> tuple[str, int, bool]:
        h = self.request_hash(request)
        last_error: ProviderError | None = None
        for attempt in range(1 + self.settings.max_retries):
            occurrence = self.ledger.next_occurrence(h)
            record = self.ledger.lookup(h, occurrence)
            if record is not None:
                self.budget.record_cache_hit()
                if record.status in ("refusal", "truncated"):
                    raise TaskFailed(request.task, record.error or record.status, call_ids=[record.id], errors=[record.status])
                if record.status == "error":
                    last_error = ProviderError(record.error or "error", retryable=record.error_retryable)
                    if last_error.retryable and attempt < self.settings.max_retries:
                        continue
                    raise last_error
                return record.raw_output or "", record.id, True
            if self.replay:
                raise ReplayMiss(f"no recorded response for {request.task} (agent={request.agent_id}, occurrence={occurrence})")
            est_in = estimate_tokens(request.system + request.prompt)
            self.budget.check(est_in, request.max_output_tokens)
            started = time.monotonic()
            try:
                response = self.provider.complete(request)
            except ProviderError as exc:
                latency = (time.monotonic() - started) * 1000
                call_id = self._record(request, h, occurrence, None, exc, latency)
                last_error = exc
                if exc.retryable and attempt < self.settings.max_retries:
                    self.sleep(self.settings.backoff_s * (2**attempt))
                    continue
                if isinstance(exc, ProviderRefusal | ProviderTruncated):
                    raise TaskFailed(request.task, str(exc), call_ids=[call_id], errors=[exc.kind]) from exc
                raise
            latency = (time.monotonic() - started) * 1000
            call_id = self._record(request, h, occurrence, response, None, latency)
            return response.text, call_id, False
        assert last_error is not None
        raise last_error

    def _record(
        self,
        request: LLMRequest,
        request_hash: str,
        occurrence: int,
        response: LLMResponse | None,
        error: ProviderError | None,
        latency_ms: float,
    ) -> int:
        settings = {
            "max_output_tokens": request.max_output_tokens,
            "effort": request.effort,
            "temperature": request.temperature,
        }
        if response is not None:
            cost = self.pricing.cost(
                response.served_model or request.model,
                response.input_tokens,
                response.output_tokens,
                response.cache_read_tokens,
                response.cache_write_tokens,
            )
            self.budget.record(response.input_tokens, response.output_tokens, cost)
            status = "received"
            fields = dict(
                served_model=response.served_model,
                raw_output=response.text,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                tokens_estimated=1 if response.tokens_estimated else 0,
                cache_read_tokens=response.cache_read_tokens,
                cache_write_tokens=response.cache_write_tokens,
                cost_usd=cost,
                metadata_json=stable_json(response.metadata),
            )
        else:
            status = error.kind if error and error.kind in ("refusal", "truncated") else "error"
            fields = dict(
                error=str(error),
                error_retryable=1 if error and error.retryable else 0,
                metadata_json=stable_json(error.metadata if error else {}),
            )
            self.budget.record(0, 0, 0.0)
        return self.ledger.record(
            request_hash=request_hash,
            occurrence=occurrence,
            step=self.step_getter(),
            sim_time=request.sim_time.isoformat() if request.sim_time else None,
            task=request.task,
            template_id=request.template_id,
            template_hash=request.template_hash,
            agent_id=request.agent_id,
            purpose=request.purpose,
            provider=self.provider.name,
            model=request.model,
            settings_json=stable_json(settings),
            system=request.system,
            prompt=request.prompt,
            schema_json=stable_json(request.output_schema),
            status=status,
            latency_ms=latency_ms,
            attempt_kind=request.attempt_kind,
            **fields,
        )

    @staticmethod
    def _validate(raw: str, model: type[BaseModel], validate: Validator | None) -> tuple[Any, list[str]]:
        try:
            data = extract_json(raw)
        except (ValueError, json.JSONDecodeError) as exc:
            return None, [f"output is not valid JSON: {exc}"]
        try:
            parsed = model.model_validate(data)
        except ValidationError as exc:
            return None, [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]
        if validate is not None:
            errors = validate(parsed)
            if errors:
                return parsed, list(errors)
        return parsed, []

    def _mark(self, call_id: int, parsed: Any, errors: list[str]) -> None:
        if self.ledger.readonly_scope is not None:
            return
        self.ledger.conn.execute(
            "UPDATE calls SET status=?, parsed_json=?, validation_errors=? WHERE id=? AND status IN ('received','ok','invalid')",
            (
                "invalid" if errors else "ok",
                parsed.model_dump_json() if parsed is not None else None,
                json.dumps(errors) if errors else None,
                call_id,
            ),
        )
        self.ledger.conn.commit()
