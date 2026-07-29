from __future__ import annotations

from datetime import date
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class Objective(str, Enum):
    FIND_CLIENTS = "find_clients"
    FIND_PARTNERS = "find_partners"
    COMPETITIVE_INTEL = "competitive_intel"


class ICPContext(BaseModel):
    """Ideal Customer Profile - persists across runs for a given client account."""

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


class RunState(BaseModel):
    """
    The single source of truth for a reconnaissance run.
    Persisted after every stage transition (see orchestrator.run.persist).
    """

    run_id: str = Field(default_factory=lambda: str(uuid4()))
    client_id: str
    stage: RunStage = RunStage.SCOUT

    input: RunInput
    candidate_events: list[EventCandidate] = Field(default_factory=list)
    selected_event: SelectedEvent | None = None

    raw_exhibitor_count: int = 0
    raw_exhibitors: list = Field(default_factory=list)  # list[ExhibitorInput], avant classification
    exhibitors: list = Field(default_factory=list)  # list[ClassificationOutput]
    itinerary: list = Field(default_factory=list)  # list[ItineraryStop]

    error: str | None = None
