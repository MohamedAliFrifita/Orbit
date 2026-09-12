"""
generate_itinerary_groq — version Groq (Llama 3.3 70B) du Planner.

Reçoit un prompt_worker généré par GROK (contient déjà les contraintes ICP).
Appel unique (pas de batching) : le Planner raisonne sur l'ensemble des exposants.
"""

from __future__ import annotations

import asyncio
import json

from pydantic import ValidationError

from orbit.schemas.exhibitor import ClassificationOutput
from orbit.schemas.itinerary import ItineraryStop
from orbit.tools.groq_client import GROQ_MODEL, get_groq_client

_MAX_RETRIES = 2


class PlannerGroqError(Exception):
    pass


async def generate_itinerary_groq(
    exhibitors: list[ClassificationOutput],
    prompt_worker: str,
) -> list[ItineraryStop]:
    """Génère l'itinéraire via Groq Llama 3.3."""
    relevant = [e for e in exhibitors if e.category != "irrelevant"]
    if not relevant:
        raise PlannerGroqError("Aucun exposant pertinent pour générer un itinéraire.")

    exhibitors_json = json.dumps(
        [e.model_dump() for e in relevant], ensure_ascii=False, indent=2
    )

    for attempt in range(_MAX_RETRIES):
        client = get_groq_client()
        resp = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": prompt_worker},
                {
                    "role": "user",
                    "content": (
                        f"Génère l'itinéraire de visite pour ces {len(relevant)} exposants.\n"
                        f"Retourne un tableau JSON d'objets ItineraryStop.\n\n"
                        f"Exposants classifiés :\n{exhibitors_json}"
                    ),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )

        raw = resp.choices[0].message.content
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                data = next(iter(data.values()))
            stops = []
            for item in data:
                try:
                    stops.append(ItineraryStop(**item))
                except ValidationError:
                    continue
            if stops:
                return stops
        except (json.JSONDecodeError, StopIteration):
            await asyncio.sleep(1.0 * (attempt + 1))

    raise PlannerGroqError("Impossible de générer un itinéraire valide après plusieurs tentatives.")