from __future__ import annotations

from pydantic import BaseModel


class ItineraryStop(BaseModel):
    order: int
    exhibitor_id: str
    exhibitor_name: str
    booth: str | None = None
    time_slot: str | None = None
    objective: str
    justification: str = ""  # Justification metier generee par le Planner LLM (semaine 4)
