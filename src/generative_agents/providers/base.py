"""Provider-neutral request/response types and errors.

Every generation call in the system flows through ``providers.gateway.LLMGateway``; adapters
only translate an ``LLMRequest`` into one API call and back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

import numpy as np


@dataclass
class LLMRequest:
    task: str
    template_id: str
    template_hash: str
    system: str
    prompt: str
    output_schema: dict[str, Any]
    model: str
    max_output_tokens: int
    effort: str | None = None
    temperature: float | None = None
    agent_id: str | None = None
    purpose: str | None = None
    sim_time: datetime | None = None
    # Structured inputs the prompt was rendered from. The mock provider reads them; real
    # providers ignore them. They never enter cache keys (the rendered prompt does).
    variables: dict[str, Any] = field(default_factory=dict)
    attempt_kind: str = "initial"  # initial | repair


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    served_model: str
    stop_reason: str = "end_turn"
    tokens_estimated: bool = False
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class LLMProvider(Protocol):
    name: str

    def complete(self, request: LLMRequest) -> LLMResponse: ...

    def describe(self) -> dict[str, Any]: ...


class EmbeddingProvider(Protocol):
    model_id: str
    dims: int
    revision: str | None
    is_fixture: bool

    def embed(self, texts: list[str]) -> np.ndarray: ...

    def describe(self) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------- errors
class ProviderError(Exception):
    """A provider call failed. ``retryable`` follows the HTTP class of the failure."""

    def __init__(self, message: str, *, retryable: bool, kind: str = "error", metadata: dict | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.kind = kind
        self.metadata = metadata or {}


class ProviderRefusal(ProviderError):
    def __init__(self, message: str, *, category: str | None = None, metadata: dict | None = None):
        super().__init__(message, retryable=False, kind="refusal", metadata=metadata)
        self.category = category


class ProviderTruncated(ProviderError):
    def __init__(self, message: str, *, metadata: dict | None = None):
        super().__init__(message, retryable=False, kind="truncated", metadata=metadata)


class BudgetExceeded(Exception):
    """A configured ceiling would be crossed; the run must checkpoint and stop."""

    def __init__(self, limit: str, used: float, cap: float):
        super().__init__(f"budget exhausted: {limit} used {used} of cap {cap}")
        self.limit = limit
        self.used = used
        self.cap = cap


class TaskFailed(Exception):
    """A cognitive task could not produce a valid output after bounded repairs.

    Callers must not fabricate a substitute; they record the failure and degrade
    visibly (for example, the agent keeps its previous action).
    """

    def __init__(self, task: str, message: str, *, call_ids: list[int] | None = None, errors: list[str] | None = None):
        super().__init__(f"{task}: {message}")
        self.task = task
        self.call_ids = call_ids or []
        self.errors = errors or []


class ReplayMiss(Exception):
    """Replay mode needed a response that the source run never recorded."""


def estimate_tokens(text: str) -> int:
    """Rough token estimate (≈ 4 characters per token); used only when a provider reports none."""

    return max(1, (len(text) + 3) // 4)
