"""Any server that speaks the OpenAI chat-completions wire format (LM Studio, llama.cpp's
``llama-server``, vLLM, Ollama's ``/v1``), over plain HTTP without the OpenAI SDK.

Requests: ``POST {base_url}/chat/completions`` with a system and a user message,
``response_format = {"type": "json_schema", "json_schema": {"name", "schema", "strict"}}``,
``max_tokens``, and ``temperature``/``seed`` when configured. Embeddings:
``POST {base_url}/embeddings``. An API key is read from the environment variable named in the
config, if any (local servers usually accept anything).

This follows the OpenAI wire format; it has not been exercised against LM Studio from this
project. Servers differ in how strictly they enforce ``json_schema``; the gateway validates
every reply and repairs or fails visibly either way.
"""

from __future__ import annotations

import os
import time
from typing import Any

import numpy as np

from .base import LLMRequest, LLMResponse, ProviderError, ProviderRefusal, ProviderTruncated, estimate_tokens
from .local_http import JSONClient, inline_refs, is_local_url

DEFAULT_URL = "http://localhost:1234/v1"


def _client(base_url: str, api_key_env: str | None, timeout_s: float) -> JSONClient:
    headers = {}
    key = os.environ.get(api_key_env) if api_key_env else None
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return JSONClient(base_url, timeout_s=timeout_s, use_env_proxy=not is_local_url(base_url), headers=headers, label="openai-compatible server")


class OpenAICompatibleProvider:
    name = "openai_compatible"

    def __init__(
        self,
        model: str,
        *,
        base_url: str | None = None,
        api_key_env: str | None = None,
        seed: int | None = None,
        timeout_s: float = 600.0,
        client: JSONClient | None = None,
    ):
        self.model = model
        self.base_url = (base_url or DEFAULT_URL).rstrip("/")
        self.seed = seed
        self.client = client or _client(self.base_url, api_key_env, timeout_s)

    def describe(self) -> dict[str, Any]:
        return {"provider": self.name, "model": self.model, "base_url": self.base_url, "seed": self.seed, "local": is_local_url(self.base_url)}

    def complete(self, request: LLMRequest) -> LLMResponse:
        body: dict[str, Any] = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.prompt},
            ],
            "max_tokens": request.max_output_tokens,
            "stream": False,
            "response_format": {"type": "json_schema", "json_schema": {"name": request.task, "schema": inline_refs(request.output_schema), "strict": True}},
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if self.seed is not None:
            body["seed"] = self.seed
        started = time.monotonic()
        data = self.client.request("POST", "/chat/completions", body)
        latency = (time.monotonic() - started) * 1000
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError("server returned no choices", retryable=True)
        choice = choices[0]
        message = choice.get("message") or {}
        finish = choice.get("finish_reason") or "stop"
        metadata = {"finish_reason": finish, "system_fingerprint": data.get("system_fingerprint")}
        if message.get("refusal") or finish == "content_filter":
            raise ProviderRefusal("model declined", metadata=metadata)
        if finish == "length":
            raise ProviderTruncated("output hit max_tokens before the JSON was complete", metadata=metadata)
        text = message.get("content") or ""
        usage = data.get("usage") or {}
        estimated = "prompt_tokens" not in usage or "completion_tokens" not in usage
        return LLMResponse(
            text=text,
            input_tokens=int(usage.get("prompt_tokens") or estimate_tokens(request.system + request.prompt)),
            output_tokens=int(usage.get("completion_tokens") or estimate_tokens(text)),
            served_model=str(data.get("model") or request.model),
            stop_reason=finish,
            tokens_estimated=estimated,
            latency_ms=latency,
            metadata=metadata,
        )


class OpenAICompatibleEmbedding:
    is_fixture = False

    def __init__(
        self,
        model: str,
        dims: int | None = None,
        *,
        base_url: str | None = None,
        api_key_env: str | None = None,
        revision: str | None = None,
        timeout_s: float = 120.0,
        client: JSONClient | None = None,
    ):
        self.model_id = model
        self.dims = int(dims or 0)
        self.revision = revision
        self.base_url = (base_url or DEFAULT_URL).rstrip("/")
        self.client = client or _client(self.base_url, api_key_env, timeout_s)

    def prepare(self) -> None:
        if not self.dims:
            self.dims = int(self.embed(["dimension probe"]).shape[1])

    def embed(self, texts: list[str]) -> np.ndarray:
        data = self.client.request("POST", "/embeddings", {"model": self.model_id, "input": texts})
        rows = sorted(data.get("data") or [], key=lambda d: d.get("index", 0))
        if len(rows) != len(texts):
            raise ProviderError(f"server returned {len(rows)} embeddings for {len(texts)} texts", retryable=False)
        arr = np.asarray([r["embedding"] for r in rows], dtype=np.float32)
        if self.dims and arr.shape[1] != self.dims:
            raise ProviderError(f"{self.model_id} returned {arr.shape[1]} dimensions but the config says {self.dims}", retryable=False)
        self.dims = int(arr.shape[1])
        return arr

    def describe(self) -> dict[str, Any]:
        return {"kind": "openai_compatible", "model": self.model_id, "dims": self.dims, "revision": self.revision, "base_url": self.base_url, "fixture": False}
