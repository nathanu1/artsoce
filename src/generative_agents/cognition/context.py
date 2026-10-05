"""Builders for the agent-visible text that prompts are rendered from.

Everything here reads only the agent's own identity, own memories and own perceptions. Global
scenario metadata (event windows, other agents' private state, evaluator ground truth) is
never passed in (spec A-7).
"""

from __future__ import annotations

from datetime import datetime

from ..schemas import AgentIdentity, Memory
from ..simulation.clock import day_label


def identity_block(identity: AgentIdentity, now: datetime | None = None) -> str:
    """The authored "identity stable set" (released scratch.py:382-414).

    It is the static identity shared by every interview condition (spec M-2).
    """

    lines = [
        f"Name: {identity.name}",
        f"Age: {identity.age}",
        f"Innate traits: {identity.innate}",
        f"Learned traits: {identity.learned}",
        f"Currently: {identity.currently}",
        f"Lifestyle: {identity.lifestyle}",
    ]
    if identity.daily_plan_req:
        lines.append(f"Daily plan requirement: {identity.daily_plan_req}")
    if now is not None:
        lines.append(f"Current Date: {day_label(now)}")
    return "\n".join(lines)


def short_identity(identity: AgentIdentity) -> str:
    return f"Name: {identity.name} (age: {identity.age})\nInnate traits: {identity.innate}"


def numbered(memories: list[Memory] | list[str], start: int = 1) -> tuple[str, dict[str, str]]:
    """'1. text' lines plus a handle→memory-id map (for citation checks)."""

    lines: list[str] = []
    handles: dict[str, str] = {}
    for i, m in enumerate(memories, start=start):
        text = m.description if isinstance(m, Memory) else str(m)
        lines.append(f"{i}. {text}")
        if isinstance(m, Memory):
            handles[str(i)] = m.id
    return "\n".join(lines), handles


def bullet(memories: list[Memory] | list[str]) -> str:
    if not memories:
        return "(nothing relevant comes to mind)"
    return "\n".join(f"- {m.description if isinstance(m, Memory) else m}" for m in memories)


def statement_texts(memories: list[Memory]) -> list[str]:
    return [m.description for m in memories]
