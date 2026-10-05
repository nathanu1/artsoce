"""Validated output schemas, one per prompt task (spec §2 "structured outputs", D-4).

The JSON schema sent to providers is derived from these models by
``providers.schema.strict_json_schema``; range checks that the APIs cannot enforce
(e.g. 1–10) are validated here, client-side.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImportanceOut(_Out):
    rating: int

    @field_validator("rating")
    @classmethod
    def _range(cls, v: int) -> int:
        if not 1 <= v <= 10:
            raise ValueError("rating must be an integer from 1 to 10")
        return v


class RatingItem(_Out):
    id: str
    rating: int

    @field_validator("rating")
    @classmethod
    def _range(cls, v: int) -> int:
        if not 1 <= v <= 10:
            raise ValueError("rating must be an integer from 1 to 10")
        return v


class ImportanceBatchOut(_Out):
    ratings: list[RatingItem]


class SummaryOut(_Out):
    summary: str

    @field_validator("summary")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("summary must not be empty")
        return v.strip()


class ReflectionQuestionsOut(_Out):
    questions: list[str]


class InsightItem(_Out):
    insight: str
    evidence: list[str]


class ReflectionInsightsOut(_Out):
    insights: list[InsightItem]


class DayPlanItem(_Out):
    time: str
    activity: str


class DayPlanOut(_Out):
    wake_up_time: str
    items: list[DayPlanItem]


class HourlyBlock(_Out):
    start: str
    end: str
    activity: str


class HourlyScheduleOut(_Out):
    blocks: list[HourlyBlock]


class TaskOut(_Out):
    start: str
    duration_minutes: int
    activity: str


class DecomposeOut(_Out):
    tasks: list[TaskOut]


class LocationChoiceOut(_Out):
    choice: str


class LocationPathOut(_Out):
    sector: str
    arena: str
    object: str


class ActionGroundingOut(_Out):
    subject: str
    predicate: str
    object: str
    object_state: str


class ReactionDecisionOut(_Out):
    decision: Literal["continue", "react", "talk", "wait"]
    reason: str
    new_activity: str | None = None
    duration_minutes: int | None = None


class DialogueTurnOut(_Out):
    utterance: str
    end_conversation: bool

    @field_validator("utterance")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("utterance must not be empty")
        return v


class ConversationInferencesOut(_Out):
    planning_note: str | None = None
    memo: str | None = None


class InterviewAnswerOut(_Out):
    answer: str


class AwarenessOut(_Out):
    claims_knowledge: bool
    details: list[str] = Field(default_factory=list)
    quote: str = ""


class StatementOut(_Out):
    statement: str


class JudgeOut(_Out):
    score: int
    rationale: str


OUTPUT_MODELS: dict[str, type[BaseModel]] = {
    m.__name__: m
    for m in (
        ImportanceOut,
        ImportanceBatchOut,
        SummaryOut,
        ReflectionQuestionsOut,
        ReflectionInsightsOut,
        DayPlanOut,
        HourlyScheduleOut,
        DecomposeOut,
        LocationChoiceOut,
        LocationPathOut,
        ActionGroundingOut,
        ReactionDecisionOut,
        DialogueTurnOut,
        ConversationInferencesOut,
        InterviewAnswerOut,
        AwarenessOut,
        StatementOut,
        JudgeOut,
    )
}
