"""Optional OpenAI chat-completions adapter (official ``openai`` Python SDK).

Provided for historically closer configurations (the released code used OpenAI models).
Uses ``response_format={"type": "json_schema", ...}``; ``temperature`` and ``seed`` are sent
only when configured. Signatures were checked against the installed SDK.
"""

from __future__ import annotations

import time
from typing import Any

from .base import LLMRequest, LLMResponse, ProviderError, ProviderRefusal, ProviderTruncated


class OpenAIProvider:
    name = "openai"

    def __init__(self, model: str, *, timeout_s: float = 120.0, max_retries: int = 2, seed: int | None = None):
        import openai  # optional dependency

        self._openai = openai
        self.client = openai.OpenAI(timeout=timeout_s, max_retries=max_retries)
        self.model = model
        self.seed = seed

    def describe(self) -> dict[str, Any]:
        return {"provider": self.name, "model": self.model, "sdk": f"openai {self._openai.__version__}", "seed": self.seed}

    def complete(self, request: LLMRequest) -> LLMResponse:
        openai = self._openai
        kwargs: dict[str, Any] = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.prompt},
            ],
            "max_completion_tokens": request.max_output_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": request.task, "schema": request.output_schema, "strict": True},
            },
        }
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if self.seed is not None:
            kwargs["seed"] = self.seed
        started = time.monotonic()
        try:
            resp = self.client.chat.completions.create(**kwargs)
        except openai.NotFoundError as exc:
            raise ProviderError(f"openai 404: {exc}", retryable=False) from exc
        except openai.RateLimitError as exc:
            raise ProviderError(f"openai rate limited: {exc}", retryable=True) from exc
        except openai.APIStatusError as exc:
            raise ProviderError(f"openai {exc.status_code}: {exc}", retryable=exc.status_code >= 500) from exc
        except openai.APIConnectionError as exc:
            raise ProviderError(f"openai connection error: {exc}", retryable=True) from exc
        latency = (time.monotonic() - started) * 1000
        choice = resp.choices[0]
        metadata = {"finish_reason": choice.finish_reason, "system_fingerprint": getattr(resp, "system_fingerprint", None)}
        if getattr(choice.message, "refusal", None) or choice.finish_reason == "content_filter":
            raise ProviderRefusal("model declined", metadata=metadata)
        if choice.finish_reason == "length":
            raise ProviderTruncated("output hit the token limit", metadata=metadata)
        usage = resp.usage
        return LLMResponse(
            text=choice.message.content or "",
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            served_model=resp.model,
            stop_reason=choice.finish_reason or "stop",
            latency_ms=latency,
            metadata=metadata,
        )
