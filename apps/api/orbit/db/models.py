"""
Schema DB — entites relationnelles principales (voir orbit-agent-design-guide.md §5).

SEMAINE 1 : schema initial, pas encore branche a l'orchestrateur (celui-ci
            tourne encore en memoire). SEMAINE 2 : brancher `persist()` sur ces tables.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from orbit.db.base import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String)
    icp_target_profile: Mapped[str] = mapped_column(String, nullable=True)
    icp_objectives: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    runs: Mapped[list["Run"]] = relationship(back_populates="client")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"))
    stage: Mapped[str] = mapped_column(String, default="scout")
    input_payload: Mapped[dict] = mapped_column(JSON)
    selected_event: Mapped[dict] = mapped_column(JSON, nullable=True)
    error: Mapped[str] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), onupdate=func.now())

    client: Mapped["Client"] = relationship(back_populates="runs")
    exhibitors: Mapped[list["ExhibitorClassification"]] = relationship(back_populates="run")
    itinerary_stops: Mapped[list["ItineraryStopRecord"]] = relationship(back_populates="run")


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

    run: Mapped["Run"] = relationship(back_populates="itinerary_stops")


class Lead(Base):
    """Stockage interne des leads/opportunites - pas de CRM externe (voir la charte)."""

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
