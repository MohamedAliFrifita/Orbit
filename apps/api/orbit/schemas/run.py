from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class Objective(str, Enum):
    FIND_CLIENTS = "find_clients"
    FIND_PARTNERS = "find_partners"
    COMPETITIVE_INTEL = "competitive_intel"


class ICPContext(BaseModel):
    target_client_profile: str
    objectives: list[Objective]


class RunInput(BaseModel):
    sector: str
    icp: ICPContext
    region: str
    date_range_start: date | None = None
    date_range_end: date | None = None


class EventCandidate(BaseModel):
    name: str
    dates: str
    location: str
    exhibitor_count: int | None = None
    source_url: str | None = None
    relevance_note: str | None = None


class SelectedEvent(BaseModel):
    name: str
    dates: str
    location: str
    exhibitor_count: int | None = None
    source_url: str | None = None


class RunStage(str, Enum):
    SCOUT = "scout"
    AWAITING_SELECTION = "awaiting_selection"
    ANALYST = "analyst"
    CLASSIFIER = "classifier"
    PLANNER = "planner"
    DONE = "done"
    FAILED = "failed"


class SubPhase(str, Enum):
    PLANNING = "planning"
    WORKING = "working"
    JUDGING = "judging"


class StagePlan(BaseModel):
    """Output de la sous-phase Planning GROK pour un stage donné."""
    prompt_worker: str
    success_criteria: dict[str, Any]


class RunState(BaseModel):
    """Source de vérité unique d'un run ORBIT."""

    run_id: str = Field(default_factory=lambda: str(uuid4()))
    client_id: str
    stage: RunStage = RunStage.SCOUT

    input: RunInput
    candidate_events: list[EventCandidate] = Field(default_factory=list)
    selected_event: SelectedEvent | None = None

    raw_exhibitor_count: int = 0
    raw_exhibitors: list = Field(default_factory=list)
    exhibitors: list = Field(default_factory=list)
    itinerary: list = Field(default_factory=list)

    error: str | None = None

    # ── Sous-phases et Planning ──────────────────────────────────────
    # { "scout": {"prompt_worker": "...", "success_criteria": {...}}, ... }
    stage_plans: dict[str, dict] = Field(default_factory=dict)
    # { "scout": 0, "analyst": 1, ... } — nombre de retries déjà consommés
    retry_counts: dict[str, int] = Field(default_factory=dict)

    # ── Pause / Reprise ──────────────────────────────────────────────
    paused: bool = False
    paused_at_stage: RunStage | None = None
    paused_at_subphase: SubPhase | None = None

    # ── Qualité du résultat ──────────────────────────────────────────
    low_confidence: bool = False
    low_confidence_stages: list[str] = Field(default_factory=list)