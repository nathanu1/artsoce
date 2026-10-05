"""Per-run ceilings on calls, tokens, runtime and (optionally) cost (spec O-3).

``check`` is called before every provider call with a conservative estimate; ``record`` adds
the actual usage afterwards. Crossing a ceiling raises ``BudgetExceeded``; the engine then
rolls back the current step, writes a checkpoint and stops with status ``budget_exhausted``.
Nothing is fabricated to finish the step.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ..providers.base import BudgetExceeded


@dataclass
class BudgetUsage:
    calls: int = 0
    cache_hits: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    unpriced_calls: int = 0
    runtime_s: float = 0.0  # accumulated across resumes

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass
class Budget:
    max_calls: int | None = None
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    max_runtime_s: float | None = None
    max_cost_usd: float | None = None
    usage: BudgetUsage = field(default_factory=BudgetUsage)
    _session_start: float = field(default_factory=time.monotonic)
    _session_base_runtime: float = 0.0

    @classmethod
    def from_config(cls, cfg: Any) -> Budget:
        return cls(
            max_calls=cfg.max_calls,
            max_input_tokens=cfg.max_input_tokens,
            max_output_tokens=cfg.max_output_tokens,
            max_runtime_s=cfg.max_runtime_s,
            max_cost_usd=cfg.max_cost_usd,
        )

    def restore(self, usage: dict[str, Any] | None) -> None:
        if usage:
            self.usage = BudgetUsage(**usage)
        self._session_base_runtime = self.usage.runtime_s
        self._session_start = time.monotonic()

    def runtime(self) -> float:
        return self._session_base_runtime + (time.monotonic() - self._session_start)

    def snapshot(self) -> dict[str, Any]:
        self.usage.runtime_s = self.runtime()
        return self.usage.to_dict()

    def check(self, est_input_tokens: int = 0, est_output_tokens: int = 0) -> None:
        u = self.usage
        if self.max_calls is not None and u.calls + 1 > self.max_calls:
            raise BudgetExceeded("calls", u.calls, self.max_calls)
        if self.max_input_tokens is not None and u.input_tokens + est_input_tokens > self.max_input_tokens:
            raise BudgetExceeded("input_tokens", u.input_tokens, self.max_input_tokens)
        if self.max_output_tokens is not None and u.output_tokens + est_output_tokens > self.max_output_tokens:
            raise BudgetExceeded("output_tokens", u.output_tokens, self.max_output_tokens)
        if self.max_runtime_s is not None and self.runtime() > self.max_runtime_s:
            raise BudgetExceeded("runtime_s", round(self.runtime(), 1), self.max_runtime_s)
        if self.max_cost_usd is not None and u.cost_usd > self.max_cost_usd:
            raise BudgetExceeded("cost_usd", round(u.cost_usd, 4), self.max_cost_usd)

    def record(self, input_tokens: int, output_tokens: int, cost: float | None) -> None:
        self.usage.calls += 1
        self.usage.input_tokens += input_tokens
        self.usage.output_tokens += output_tokens
        if cost is None:
            self.usage.unpriced_calls += 1
        else:
            self.usage.cost_usd += cost

    def record_cache_hit(self) -> None:
        self.usage.cache_hits += 1

    def limits(self) -> dict[str, Any]:
        return {
            "max_calls": self.max_calls,
            "max_input_tokens": self.max_input_tokens,
            "max_output_tokens": self.max_output_tokens,
            "max_runtime_s": self.max_runtime_s,
            "max_cost_usd": self.max_cost_usd,
        }
