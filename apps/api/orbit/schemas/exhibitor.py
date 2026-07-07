from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ExhibitorInput(BaseModel):
    """Raw exhibitor record, as produced by the Analyst stage."""

    id: str
    name: str
    booth: str | None = None
    raw_description: str
    enrichment: dict | None = None


class ClassificationOutput(BaseModel):
    """
    Output contract of the Classifier agent. Every LLM response must validate
    against this model before being written to state — see orbit-coding-guide.md §5.
    """

    exhibitor_id: str
    name: str
    booth: str | None = None
    category: Literal["client", "partner", "supplier", "competitor", "irrelevant"]
    potential_score: float = Field(ge=0.0, le=1.0)
    rationale: str
    confidence: Literal["low", "medium", "high"]
    sources_used: list[str] = Field(default_factory=list)
