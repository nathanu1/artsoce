"""Memory-access masks for the matched-history ablation (paper §6.2 p. 13; spec M-2).

Masks are applied *before* retrieval and before dynamic-summary construction, so an ablated
condition can never see a forbidden memory through a cached summary or an evidence link.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..schemas import Memory, MemoryKind


@dataclass(frozen=True)
class MemoryMask:
    name: str
    kinds: frozenset[MemoryKind]

    def allows(self, m: Memory) -> bool:
        return m.kind in self.kinds

    @property
    def empty(self) -> bool:
        return not self.kinds

    @property
    def key(self) -> str:
        return self.name + ":" + ",".join(sorted(k.value for k in self.kinds))


FULL = MemoryMask("full_architecture", frozenset({MemoryKind.OBSERVATION, MemoryKind.PLAN, MemoryKind.REFLECTION}))
NO_REFLECTION = MemoryMask("no_reflection", frozenset({MemoryKind.OBSERVATION, MemoryKind.PLAN}))
OBSERVATIONS_ONLY = MemoryMask("observations_only", frozenset({MemoryKind.OBSERVATION}))
NO_MEMORY = MemoryMask("no_memory_stream", frozenset())

CONDITIONS: dict[str, MemoryMask] = {m.name: m for m in (FULL, NO_REFLECTION, OBSERVATIONS_ONLY, NO_MEMORY)}
