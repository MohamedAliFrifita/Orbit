"""Schemas Pydantic pour le Judge Mistral."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class JudgeInput(BaseModel):
    stage: str
    icp_context: str          # JSON sérialisé de ICPContext
    success_criteria: dict[str, Any]
    worker_output: str        # JSON sérialisé du résultat du worker


class JudgeVerdict(BaseModel):
    verdict: Literal["PASS", "REFINE", "REWORK"]
    score: float = Field(ge=0.0, le=10.0)
    reasoning: str
    suggestions: str | None = None
    forced_pass: bool = False
    attempt_number: int = 1