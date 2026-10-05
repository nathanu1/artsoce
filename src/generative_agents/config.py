"""Run configuration: YAML in, validated pydantic models out.

Every field carries a default that matches the settings registry in
docs/reproduction_spec.md §5. ``fidelity`` tags (P/C/E/X) are recorded in the run manifest so
each run states which values are paper-reported, released-code, engineering or extension.
"""

from __future__ import annotations

import copy
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

REPO_ROOT = Path(__file__).resolve().parents[2]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunSection(_Base):
    name: str = "run"
    output_dir: str = "runs"
    seed: int = 7
    label: str | None = None  # free text shown in the viewer


class ScenarioSection(_Base):
    path: str = "scenarios/pilot5/scenario.yaml"
    population: list[str] | None = None  # agent ids; None = all agents in the scenario
    start: datetime = datetime(2023, 2, 13, 0, 0, 0)
    end: datetime = datetime(2023, 2, 15, 0, 0, 0)
    seconds_per_step: int = 10
    candidacy_seed_policy: Literal["paper_originator_only", "released_csv"] = "paper_originator_only"
    seed_rendering: Literal["verbatim", "inner_thought_llm"] = "verbatim"


class ArchitectureSection(_Base):
    """Which cognitive modules run. The reflection extension flips ``reflection``."""

    reflection: bool = True
    planning: bool = True
    fidelity: Literal["paper", "released_code"] = "paper"
    post_conversation_inferences: bool | None = None  # None: follow fidelity (off in paper mode)

    def conversation_inferences_enabled(self) -> bool:
        if not self.reflection:
            return False  # reflection-off disables every inferential path (spec R-2)
        if self.post_conversation_inferences is not None:
            return self.post_conversation_inferences
        return self.fidelity == "released_code"


class RetrievalWeights(_Base):
    recency: float = 1.0
    importance: float = 1.0
    relevance: float = 1.0


class RetrievalSection(_Base):
    mode: Literal["paper", "released_code"] = "paper"
    weights: RetrievalWeights = Field(default_factory=RetrievalWeights)
    decay_per_hour: float = 0.995
    compat_decay: float = 0.995  # n25 scratch.json value; class default in code is 0.99
    equal_component_value: float = 0.5
    budget_tokens: int = 1200
    max_items: int = 30
    tokens_per_char: float = 0.25  # budget estimate: ~4 characters per token


class ImportanceSection(_Base):
    idle_shortcut: bool = True
    batch_statements: bool = True


class ReflectionSection(_Base):
    mode: Literal["paper", "released_code"] = "paper"
    threshold: float = 150.0
    compat_trigger_max: float = 250.0
    recent_records: int = 100
    questions: int = 3
    insights_per_question: int = 5
    retrieval_items: int = 30
    retry_cooldown_minutes: int = 30
    max_repairs: int = 1


class SummarySection(_Base):
    refresh_every_minutes: int = 180
    refresh_on_new_day: bool = True
    retrieval_items: int = 15


class PlanningSection(_Base):
    day_chunks_min: int = 5
    day_chunks_max: int = 8
    task_min_minutes: int = 5
    task_max_minutes: int = 15
    jit_window_minutes: int = 60
    max_repairs: int = 1
    store_hourly_in_memory: bool = True


class PerceptionSection(_Base):
    vision_r: int | None = None  # None: use each agent's scenario value (n25: 8)
    att_bandwidth: int | None = None
    retention: int | None = None


class LocationSection(_Base):
    strategy: Literal["recursive", "single_call"] = "recursive"
    reuse_within_block: bool = False


class DialogueSection(_Base):
    max_utterances: int = 16
    cooldown_minutes: int = 133
    relationship_items: int = 25
    turn_items: int = 10
    no_chat_after_hour: int = 23


class ConstraintsSection(_Base):
    policy: Literal["strict-v1", "none"] = "strict-v1"


class LLMProviderSection(_Base):
    kind: Literal["mock", "anthropic", "openai", "replay"] = "mock"
    model: str = "mock-llm-v1"
    max_output_tokens: int = 1024
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
    temperature: float | None = None  # only sent where the model exposes it
    timeout_s: float = 120.0
    max_retries: int = 2
    max_validation_repairs: int = 1
    refusal_fallback: Literal["default", "off"] = "off"
    replay_from: str | None = None  # run dir to replay
    task_overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)


class EmbeddingProviderSection(_Base):
    kind: Literal["mock-hash", "openai", "sentence-transformers"] = "mock-hash"
    model: str = "mock-hash-256"
    dims: int | None = 256
    revision: str | None = None
    local_dir: str | None = None
    cache_dir: str = ".ga_cache"


class ProvidersSection(_Base):
    llm: LLMProviderSection = Field(default_factory=LLMProviderSection)
    embeddings: EmbeddingProviderSection = Field(default_factory=EmbeddingProviderSection)


class BudgetSection(_Base):
    max_calls: int | None = 5000
    max_input_tokens: int | None = 5_000_000
    max_output_tokens: int | None = 1_000_000
    max_runtime_s: float | None = None
    max_cost_usd: float | None = None
    pricing_file: str | None = None  # YAML price table; absent => cost "unpriced"


class OutputSection(_Base):
    checkpoint_every_steps: int = 360
    record_frames: bool = True


class InterviewSection(_Base):
    retrieval_items: int = 30
    max_output_tokens: int = 400


class GAConfig(_Base):
    """Top-level configuration."""

    run: RunSection = Field(default_factory=RunSection)
    scenario: ScenarioSection = Field(default_factory=ScenarioSection)
    architecture: ArchitectureSection = Field(default_factory=ArchitectureSection)
    retrieval: RetrievalSection = Field(default_factory=RetrievalSection)
    importance: ImportanceSection = Field(default_factory=ImportanceSection)
    reflection: ReflectionSection = Field(default_factory=ReflectionSection)
    summary: SummarySection = Field(default_factory=SummarySection)
    planning: PlanningSection = Field(default_factory=PlanningSection)
    perception: PerceptionSection = Field(default_factory=PerceptionSection)
    location: LocationSection = Field(default_factory=LocationSection)
    dialogue: DialogueSection = Field(default_factory=DialogueSection)
    constraints: ConstraintsSection = Field(default_factory=ConstraintsSection)
    providers: ProvidersSection = Field(default_factory=ProvidersSection)
    budget: BudgetSection = Field(default_factory=BudgetSection)
    output: OutputSection = Field(default_factory=OutputSection)
    interview: InterviewSection = Field(default_factory=InterviewSection)

    @model_validator(mode="after")
    def _fidelity_defaults(self) -> GAConfig:
        if self.scenario.end <= self.scenario.start:
            raise ValueError("scenario.end must be after scenario.start")
        if self.scenario.seconds_per_step <= 0:
            raise ValueError("scenario.seconds_per_step must be positive")
        return self

    # ------------------------------------------------------------------ helpers
    @property
    def run_mode(self) -> str:
        kind = self.providers.llm.kind
        if kind == "mock":
            return "mock"
        if kind == "replay":
            return "replay"
        return "live"

    def fidelity_table(self) -> list[dict[str, Any]]:
        """Active value and class of each registry setting (spec §5)."""

        rows = [
            ("retrieval.mode", self.retrieval.mode, "P" if self.retrieval.mode == "paper" else "C"),
            ("retrieval.weights", self.retrieval.weights.model_dump(), "P" if self.retrieval.weights == RetrievalWeights() else "X"),
            ("retrieval.decay_per_hour", self.retrieval.decay_per_hour, "P"),
            ("retrieval.equal_component_value", self.retrieval.equal_component_value, "C"),
            ("retrieval.budget_tokens", self.retrieval.budget_tokens, "E"),
            ("retrieval.max_items", self.retrieval.max_items, "E"),
            ("importance.idle_shortcut", self.importance.idle_shortcut, "C"),
            ("importance.batch_statements", self.importance.batch_statements, "E"),
            ("reflection.mode", self.reflection.mode, "P" if self.reflection.mode == "paper" else "C"),
            ("reflection.threshold", self.reflection.threshold, "P" if self.reflection.mode == "paper" else "C"),
            ("reflection.recent_records", self.reflection.recent_records, "P"),
            ("architecture.reflection", self.architecture.reflection, "P" if self.architecture.reflection else "X"),
            ("architecture.post_conversation_inferences", self.architecture.conversation_inferences_enabled(), "C"),
            ("summary.refresh_every_minutes", self.summary.refresh_every_minutes, "E"),
            ("planning.day_chunks", f"{self.planning.day_chunks_min}-{self.planning.day_chunks_max}", "P"),
            ("planning.task_minutes", f"{self.planning.task_min_minutes}-{self.planning.task_max_minutes}", "P"),
            ("planning.jit_window_minutes", self.planning.jit_window_minutes, "C"),
            ("location.strategy", self.location.strategy, "P" if self.location.strategy == "recursive" else "E"),
            ("dialogue.max_utterances", self.dialogue.max_utterances, "C"),
            ("dialogue.cooldown_minutes", self.dialogue.cooldown_minutes, "C"),
            ("clock.seconds_per_step", self.scenario.seconds_per_step, "C" if self.scenario.seconds_per_step == 10 else "E"),
            ("constraints.policy", self.constraints.policy, "E"),
            ("scenario.seed_rendering", self.scenario.seed_rendering, "P" if self.scenario.seed_rendering == "verbatim" else "C"),
            (
                "scenario.candidacy_seed_policy",
                self.scenario.candidacy_seed_policy,
                "P" if self.scenario.candidacy_seed_policy == "paper_originator_only" else "C",
            ),
        ]
        return [{"setting": k, "value": v, "class": c} for k, v, c in rows]


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _resolve(path: str | Path, relative_to: Path | None = None) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    if relative_to is not None and (relative_to / p).exists():
        return relative_to / p
    if (REPO_ROOT / p).exists():
        return REPO_ROOT / p
    return p


def load_raw(path: str | Path) -> dict[str, Any]:
    """Load a YAML config, following ``extends:`` chains (paths relative to the file or repo)."""

    p = _resolve(path)
    data = yaml.safe_load(p.read_text()) or {}
    parent = data.pop("extends", None)
    if parent:
        base = load_raw(_resolve(parent, p.parent))
        data = _deep_merge(base, data)
    return data


def apply_overrides(data: dict[str, Any], overrides: list[str] | None) -> dict[str, Any]:
    """Apply ``a.b.c=value`` overrides; values are parsed as YAML scalars."""

    data = copy.deepcopy(data)
    for item in overrides or []:
        if "=" not in item:
            raise ValueError(f"override must look like key=value: {item!r}")
        key, raw = item.split("=", 1)
        value = yaml.safe_load(raw)
        node = data
        parts = key.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return data


def load_config(path: str | Path | None = None, overrides: list[str] | None = None) -> GAConfig:
    data: dict[str, Any] = load_raw(path) if path else {}
    data = apply_overrides(data, overrides)
    return GAConfig.model_validate(data)


def repo_path(rel: str | Path) -> Path:
    return _resolve(rel)
