"""Open-weight models on your own computer through Ollama's native HTTP API (no API cost).

Endpoints, as documented in Ollama's API reference (``docs/api.md``):

* ``POST /api/chat`` with ``stream: false``, a system and a user message, ``format`` set to
  the task's JSON schema (structured outputs) and ``options`` ``{num_ctx, num_predict,
  temperature, seed}``. Reply: ``message.content``, ``done_reason``, ``prompt_eval_count``,
  ``eval_count``, ``model``.
* ``POST /api/embed`` ``{model, input: [...]}`` → ``{embeddings: [[...], ...]}``.
* ``GET /api/tags`` → ``models[].digest``: the exact weights, recorded with every call.
* ``GET /api/version``.

Choices that matter for the research record:

* ``num_ctx`` is always sent. A prompt that would not fit is refused before sending (the server
  would otherwise drop the start of the prompt without telling us).
* ``done_reason == "length"`` (``num_predict`` reached) is a truncation, never a valid answer.
* A seed and temperature make Ollama's sampling repeatable on one machine and version, but not
  guaranteed across hardware or releases; exact replay comes from the call ledger.
* Nothing is downloaded at run time. Pull models yourself (``ollama pull llama3.1:8b``);
  ``ga doctor`` checks they are present.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from .base import LLMRequest, LLMResponse, ProviderError, ProviderTruncated, estimate_tokens
from .local_http import JSONClient, inline_refs

DEFAULT_URL = "http://localhost:11434"


def _model_names(tags: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for m in tags.get("models") or []:
        for key in (m.get("name"), m.get("model")):
            if key:
                out[key] = m
    return out


def find_model(tags: dict[str, Any], model: str) -> dict[str, Any] | None:
    names = _model_names(tags)
    return names.get(model) or (names.get(f"{model}:latest") if ":" not in model else None)


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        model: str,
        *,
        base_url: str | None = None,
        num_ctx: int = 8192,
        keep_alive: str | None = "30m",
        seed: int | None = None,
        think: bool | None = None,
        timeout_s: float = 600.0,
        client: JSONClient | None = None,
    ):
        self.model = model
        self.base_url = (base_url or DEFAULT_URL).rstrip("/")
        self.num_ctx = int(num_ctx)
        self.keep_alive = keep_alive
        self.seed = seed
        self.think = think
        self.client = client or JSONClient(self.base_url, timeout_s=timeout_s, label="ollama")
        self._digests: dict[str, str | None] = {}
        self._version: str | None = None

    # ------------------------------------------------------------------ provenance
    def digest(self, model: str) -> str | None:
        if model not in self._digests:
            try:
                found = find_model(self.client.request("GET", "/api/tags", timeout_s=10), model)
            except ProviderError:
                return None  # transient; try again on the next call
            self._digests[model] = found.get("digest") if found else None
        return self._digests[model]

    def describe(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "model": self.model,
            "base_url": self.base_url,
            "num_ctx": self.num_ctx,
            "seed": self.seed,
            "digest": self._digests.get(self.model, "not fetched yet"),
            "server_version": self._version,
            "api_cost": "none (local model)",
        }

    # ------------------------------------------------------------------ chat
    def complete(self, request: LLMRequest) -> LLMResponse:
        needed = int(estimate_tokens(request.system + request.prompt) * 1.15) + request.max_output_tokens
        if needed > self.num_ctx:
            raise ProviderError(
                f"prompt for {request.task} needs about {needed} tokens with its output, more than num_ctx={self.num_ctx}; "
                "raise providers.llm.num_ctx (and check the model supports it)",
                retryable=False,
            )
        options: dict[str, Any] = {"num_ctx": self.num_ctx, "num_predict": request.max_output_tokens}
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if self.seed is not None:
            options["seed"] = self.seed
        body: dict[str, Any] = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.prompt},
            ],
            "stream": False,
            "format": inline_refs(request.output_schema),
            "options": options,
        }
        if self.keep_alive is not None:
            body["keep_alive"] = self.keep_alive
        if self.think is not None:
            body["think"] = self.think
        started = time.monotonic()
        try:
            data = self.client.request("POST", "/api/chat", body)
        except ProviderError as exc:
            if exc.metadata.get("status") == 404:
                raise ProviderError(f"{exc} (pull it first: ollama pull {request.model})", retryable=False, metadata=exc.metadata) from exc
            raise
        latency = (time.monotonic() - started) * 1000
        message = data.get("message") or {}
        text = message.get("content") or ""
        done_reason = data.get("done_reason") or ("stop" if data.get("done") else "incomplete")
        metadata = {
            "done_reason": done_reason,
            "digest": self.digest(request.model),
            "total_duration_ns": data.get("total_duration"),
            "load_duration_ns": data.get("load_duration"),
            "num_ctx": self.num_ctx,
            "seed": self.seed,
        }
        if done_reason == "length":
            raise ProviderTruncated(f"output hit num_predict={request.max_output_tokens} before the JSON was complete", metadata=metadata)
        if not data.get("done", True) or done_reason not in ("stop", "length"):
            raise ProviderError(f"ollama returned an unfinished reply (done_reason={done_reason})", retryable=True, metadata=metadata)
        prompt_tokens = data.get("prompt_eval_count")
        output_tokens = data.get("eval_count")
        estimated = prompt_tokens is None or output_tokens is None
        return LLMResponse(
            text=text,
            input_tokens=int(prompt_tokens if prompt_tokens is not None else estimate_tokens(request.system + request.prompt)),
            output_tokens=int(output_tokens if output_tokens is not None else estimate_tokens(text)),
            served_model=str(data.get("model") or request.model),
            stop_reason=done_reason,
            tokens_estimated=estimated,
            latency_ms=latency,
            metadata=metadata,
        )


class OllamaEmbedding:
    """Embeddings from a local Ollama model (for example ``nomic-embed-text``, 768 dimensions).

    ``dims`` should be configured: it is part of the cache key, and a replay must be able to
    rebuild that key without contacting the server. If it is left empty, the first use makes one
    probe call to learn it.
    """

    is_fixture = False

    def __init__(
        self,
        model: str,
        dims: int | None = None,
        *,
        base_url: str | None = None,
        revision: str | None = None,
        timeout_s: float = 120.0,
        batch_size: int = 64,
        client: JSONClient | None = None,
    ):
        self.model_id = model
        self.dims = int(dims or 0)
        self.revision = revision
        self.base_url = (base_url or DEFAULT_URL).rstrip("/")
        self.batch_size = batch_size
        self.client = client or JSONClient(self.base_url, timeout_s=timeout_s, label="ollama")
        self.digest: str | None = None

    def prepare(self) -> None:
        if not self.dims:
            self.dims = int(self._embed_batch(["dimension probe"]).shape[1])

    def _embed_batch(self, texts: list[str]) -> np.ndarray:
        try:
            data = self.client.request("POST", "/api/embed", {"model": self.model_id, "input": texts, "truncate": True})
        except ProviderError as exc:
            if exc.metadata.get("status") == 404:
                raise ProviderError(f"{exc} (pull it first: ollama pull {self.model_id})", retryable=False, metadata=exc.metadata) from exc
            raise
        vecs = data.get("embeddings")
        if not isinstance(vecs, list) or len(vecs) != len(texts):
            raise ProviderError(f"ollama /api/embed returned {len(vecs) if isinstance(vecs, list) else 'no'} vectors for {len(texts)} texts", retryable=False)
        arr = np.asarray(vecs, dtype=np.float32)
        if arr.ndim != 2:
            raise ProviderError("ollama /api/embed returned ragged vectors", retryable=False)
        return arr

    def embed(self, texts: list[str]) -> np.ndarray:
        parts = [self._embed_batch(texts[i : i + self.batch_size]) for i in range(0, len(texts), self.batch_size)]
        arr = np.concatenate(parts, axis=0) if parts else np.zeros((0, max(1, self.dims)), dtype=np.float32)
        if self.dims and arr.shape[1] != self.dims:
            raise ProviderError(
                f"{self.model_id} returned {arr.shape[1]}-dimensional vectors but providers.embeddings.dims is {self.dims}; fix the config",
                retryable=False,
            )
        self.dims = int(arr.shape[1])
        return arr

    def describe(self) -> dict[str, Any]:
        return {"kind": "ollama", "model": self.model_id, "dims": self.dims, "revision": self.revision, "base_url": self.base_url, "fixture": False}


def ollama_status(base_url: str | None, models: list[str], *, timeout_s: float = 5.0) -> dict[str, Any]:
    """Server version and which of ``models`` are pulled. Never raises."""

    client = JSONClient(base_url or DEFAULT_URL, timeout_s=timeout_s, label="ollama")
    out: dict[str, Any] = {"base_url": client.base_url, "reachable": False, "version": None, "present": {}, "error": None}
    try:
        out["version"] = client.request("GET", "/api/version").get("version")
        tags = client.request("GET", "/api/tags")
    except ProviderError as exc:
        out["error"] = str(exc)
        return out
    out["reachable"] = True
    for m in models:
        found = find_model(tags, m)
        out["present"][m] = {"digest": found.get("digest"), "size": found.get("size")} if found else None
    return out
