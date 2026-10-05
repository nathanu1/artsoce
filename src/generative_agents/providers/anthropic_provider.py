"""Anthropic Messages API adapter (official ``anthropic`` Python SDK, 1.x).

Usage follows the SDK documentation consulted for this project:

* structured output via ``output_config={"format": {"type": "json_schema", "schema": ...}}``;
* ``output_config["effort"]`` when configured (current Opus/Sonnet models; not Haiku 4.5);
* no sampling parameters on models that reject them (the 1.x ``messages.create`` signature
  does not expose ``temperature``), so ``temperature`` is recorded as "not sent";
* optional server-side refusal fallback (``fallbacks="default"`` with beta
  ``server-side-fallback-2026-07-01``). When a fallback serves a call, the serving model is
  recorded per call and flagged in the run report, because it changes model provenance;
* typed exception chain, most specific first.
"""

from __future__ import annotations

import time
from typing import Any

from .base import LLMRequest, LLMResponse, ProviderError, ProviderRefusal, ProviderTruncated

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str, *, timeout_s: float = 120.0, max_retries: int = 2, refusal_fallback: str = "off"):
        import anthropic  # optional dependency

        self._anthropic = anthropic
        self.client = anthropic.Anthropic(timeout=timeout_s, max_retries=max_retries)
        self.model = model
        self.refusal_fallback = refusal_fallback

    def describe(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "model": self.model,
            "sdk": f"anthropic {self._anthropic.__version__}",
            "refusal_fallback": self.refusal_fallback,
            "sampling": "temperature not sent (not exposed for current models)",
        }

    def complete(self, request: LLMRequest) -> LLMResponse:
        anthropic = self._anthropic
        output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": request.output_schema}}
        if request.effort:
            output_config["effort"] = request.effort
        kwargs: dict[str, Any] = {
            "model": request.model,
            "max_tokens": request.max_output_tokens,
            "system": request.system,
            "messages": [{"role": "user", "content": request.prompt}],
            "output_config": output_config,
        }
        started = time.monotonic()
        try:
            if self.refusal_fallback == "default":
                message = self.client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
            else:
                message = self.client.messages.create(**kwargs)
        except anthropic.NotFoundError as exc:  # 404: unknown model or endpoint
            raise ProviderError(f"anthropic 404: {exc.message}", retryable=False) from exc
        except anthropic.RateLimitError as exc:  # 429
            raise ProviderError(f"anthropic rate limited: {exc.message}", retryable=True) from exc
        except anthropic.APIStatusError as exc:  # other non-2xx
            raise ProviderError(f"anthropic {exc.status_code}: {exc.message}", retryable=exc.status_code >= 500) from exc
        except anthropic.APIConnectionError as exc:  # network failure or timeout
            raise ProviderError(f"anthropic connection error: {exc}", retryable=True) from exc
        latency = (time.monotonic() - started) * 1000

        usage = message.usage
        fallback_used = any(getattr(entry, "type", None) == "fallback_message" for entry in (getattr(usage, "iterations", None) or []))
        metadata = {
            "request_id": getattr(message, "_request_id", None),
            "stop_reason": message.stop_reason,
            "fallback_used": fallback_used,
        }
        if message.stop_reason == "refusal":
            details = getattr(message, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            raise ProviderRefusal(f"model declined (category={category})", category=category, metadata=metadata)
        if message.stop_reason == "max_tokens":
            raise ProviderTruncated("output hit max_tokens before completing the JSON", metadata=metadata)
        text = "".join(block.text for block in message.content if getattr(block, "type", None) == "text")
        return LLMResponse(
            text=text,
            input_tokens=int(usage.input_tokens or 0),
            output_tokens=int(usage.output_tokens or 0),
            served_model=message.model,
            stop_reason=message.stop_reason or "end_turn",
            cache_read_tokens=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
            cache_write_tokens=int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
            latency_ms=latency,
            metadata=metadata,
        )
