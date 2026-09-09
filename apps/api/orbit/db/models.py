"""
Schema DB — entités relationnelles principales.

Nouvelles tables : User, AICallLog, JudgeVerdict.
Colonnes ajoutées sur Run : paused, stage_plans, low_confidence, etc.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from orbit.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    clients: Mapped[list["Client"]] = relationship(back_populates="user")


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String)
    icp_target_profile: Mapped[str] = mapped_column(String, nullable=True)
    icp_objectives: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="clients")
    runs: Mapped[list["Run"]] = relationship(back_populates="client")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"))
    stage: Mapped[str] = mapped_column(String, default="scout")
    input_payload: Mapped[dict] = mapped_column(JSON)
    selected_event: Mapped[dict] = mapped_column(JSON, nullable=True)
    error: Mapped[str] = mapped_column(String, nullable=True)

    # ── Nouveaux champs ──────────────────────────────────────────────
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_at_stage: Mapped[str | None] = mapped_column(String, nullable=True)
    paused_at_subphase: Mapped[str | None] = mapped_column(String, nullable=True)  # planning|working|judging
    low_confidence: Mapped[bool] = mapped_column(Boolean, default=False)
    low_confidence_stages: Mapped[list] = mapped_column(JSON, default=list)
    # stage_plans : { "scout": {"prompt_worker": "...", "success_criteria": {...}}, ... }
    stage_plans: Mapped[dict] = mapped_column(JSON, default=dict)
    retry_counts: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    client: Mapped["Client"] = relationship(back_populates="runs")
    exhibitors: Mapped[list["ExhibitorClassification"]] = relationship(back_populates="run")
    itinerary_stops: Mapped[list["ItineraryStopRecord"]] = relationship(back_populates="run")
    ai_call_logs: Mapped[list["AICallLog"]] = relationship(back_populates="run")
    judge_verdicts: Mapped[list["JudgeVerdictRecord"]] = relationship(back_populates="run")


class ExhibitorClassification(Base):
    __tablename__ = "exhibitor_classifications"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    exhibitor_external_id: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    booth: Mapped[str] = mapped_column(String, nullable=True)
    category: Mapped[str] = mapped_column(String)
    potential_score: Mapped[float] = mapped_column(Float)
    rationale: Mapped[str] = mapped_column(String)
    confidence: Mapped[str] = mapped_column(String)

    run: Mapped["Run"] = relationship(back_populates="exhibitors")


class ItineraryStopRecord(Base):
    __tablename__ = "itinerary_stops"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    order: Mapped[int] = mapped_column()
    exhibitor_external_id: Mapped[str] = mapped_column(String)
    exhibitor_name: Mapped[str] = mapped_column(String)
    booth: Mapped[str] = mapped_column(String, nullable=True)
    time_slot: Mapped[str] = mapped_column(String, nullable=True)
    objective: Mapped[str] = mapped_column(String)
    justification: Mapped[str] = mapped_column(Text, nullable=True)

    run: Mapped["Run"] = relationship(back_populates="itinerary_stops")


class AICallLog(Base):
    """Enregistrement de chaque appel LLM (Planning GROK, Working, Judging)."""

    __tablename__ = "ai_call_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    stage: Mapped[str] = mapped_column(String)                   # scout | analyst | classifier | planner
    subphase: Mapped[str] = mapped_column(String)                # planning | working | judging
    model: Mapped[str] = mapped_column(String)                   # grok-2-latest | gemini-2.5-flash | ...
    role: Mapped[str] = mapped_column(String)                    # orchestrator | worker | judge
    prompt_version: Mapped[str | None] = mapped_column(String, nullable=True)   # grok_scout/v1
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    run: Mapped["Run"] = relationship(back_populates="ai_call_logs")


class JudgeVerdictRecord(Base):
    """Historique des verdicts Mistral par stage."""

    __tablename__ = "judge_verdicts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"))
    stage: Mapped[str] = mapped_column(String)
    attempt_number: Mapped[int] = mapped_column(Integer)
    verdict: Mapped[str] = mapped_column(String)        # PASS | REFINE | REWORK
    score: Mapped[float] = mapped_column(Float)
    reasoning: Mapped[str] = mapped_column(Text)
    suggestions: Mapped[str | None] = mapped_column(Text, nullable=True)
    forced_pass: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped["Run"] = relationship(back_populates="judge_verdicts")


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"))
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), nullable=True)
    exhibitor_name: Mapped[str] = mapped_column(String)
    contact_name: Mapped[str] = mapped_column(String, nullable=True)
    contact_email: Mapped[str] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="new")
    notes: Mapped[str] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())