"""Assemble providers, gateway, ledger, embeddings and budget from a config."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import GAConfig, repo_path
from ..memory.store import MemoryStore
from ..prompting import PromptRegistry
from ..providers.embeddings import EmbeddingCache, EmbeddingService, build_embedding_provider
from ..providers.gateway import GatewaySettings, LLMGateway
from ..providers.ledger import CallLedger
from ..providers.mock import MockLLM
from ..providers.pricing import PriceTable
from .budget import Budget


def build_llm_provider(cfg: GAConfig) -> Any:
    llm = cfg.providers.llm
    if llm.kind == "mock":
        return MockLLM(seed=cfg.run.seed, model=llm.model)
    if llm.kind == "anthropic":
        from ..providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(llm.model, timeout_s=llm.timeout_s, max_retries=llm.max_retries, refusal_fallback=llm.refusal_fallback)
    if llm.kind == "openai":
        from ..providers.openai_provider import OpenAIProvider

        return OpenAIProvider(llm.model, timeout_s=llm.timeout_s, max_retries=llm.max_retries, seed=cfg.run.seed)
    if llm.kind == "replay":
        return _NoCallProvider()
    raise ValueError(f"unknown llm provider {llm.kind!r}")


class _NoCallProvider:
    """Replay mode: any request that is not in the recorded ledger is an error, never a call."""

    name = "replay"

    def describe(self) -> dict[str, Any]:
        return {"provider": "replay", "fresh_calls": False}

    def complete(self, request: Any) -> Any:  # pragma: no cover - gateway raises ReplayMiss first
        raise RuntimeError("replay mode never calls a model")


@dataclass
class Runtime:
    gateway: LLMGateway
    embeddings: EmbeddingService
    ledger: CallLedger
    budget: Budget
    registry: PromptRegistry
    pricing: PriceTable
    provider: Any
    provider_name: str


def build_runtime(
    cfg: GAConfig,
    *,
    store: MemoryStore | None,
    ledger_path: str | Path | None,
    scope: str,
    step_getter: Callable[[], int | None] | None = None,
    replay_scope: str | None = None,
    provider: Any = None,
    embedding_provider: Any = None,
    sleep: Callable[[float], None] | None = None,
) -> Runtime:
    registry = PromptRegistry()
    pricing = PriceTable.load(repo_path(cfg.budget.pricing_file) if cfg.budget.pricing_file else None)
    ledger = CallLedger(ledger_path, scope=scope)
    replay = replay_scope is not None or cfg.providers.llm.kind == "replay"
    if replay_scope is not None:
        ledger.readonly_scope = replay_scope
    budget = Budget.from_config(cfg.budget)
    if replay:
        budget = Budget()  # replays never call a model; ceilings do not apply
    llm = cfg.providers.llm
    prov = provider or build_llm_provider(cfg)
    settings = GatewaySettings(
        model=llm.model,
        max_output_tokens=None if llm.kind == "mock" else llm.max_output_tokens,
        effort=llm.effort,
        temperature=llm.temperature,
        max_retries=llm.max_retries,
        max_validation_repairs=llm.max_validation_repairs,
        backoff_s=0.0 if llm.kind == "mock" else 2.0,
        task_overrides=llm.task_overrides,
    )
    kwargs: dict[str, Any] = {}
    if sleep is not None:
        kwargs["sleep"] = sleep
    gateway = LLMGateway(prov, registry, ledger, budget, settings, pricing=pricing, step_getter=step_getter, replay=replay, **kwargs)
    emb_cfg = cfg.providers.embeddings
    emb_provider = embedding_provider or build_embedding_provider(emb_cfg)
    cache = EmbeddingCache(repo_path(emb_cfg.cache_dir) / "embeddings.sqlite" if emb_cfg.kind != "mock-hash" else None)
    embeddings = EmbeddingService(emb_provider, store=store, cache=cache, ledger=ledger)
    return Runtime(gateway, embeddings, ledger, budget, registry, pricing, prov, getattr(prov, "name", "unknown"))
