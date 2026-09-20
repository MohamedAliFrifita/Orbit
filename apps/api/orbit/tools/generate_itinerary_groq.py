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
    relevant = [
        e for e in exhibitors
        if (e.category if hasattr(e, "category") else e.get("category")) != "irrelevant"
    ]
    if not relevant:
        raise PlannerGroqError("Aucun exposant pertinent pour générer un itinéraire.")

    exhibitors_json = json.dumps(
        [e.model_dump() if hasattr(e, "model_dump") else e for e in relevant],
        ensure_ascii=False,
        indent=2,
    )

    schema_instruction = (
        "Pour chaque étape d'itinéraire, produis un objet JSON avec EXACTEMENT :\n"
        "{\n"
        '  "order": <entier 1, 2, 3...>,\n'
        '  "exhibitor_id": "<id de l\'exposant>",\n'
        '  "exhibitor_name": "<nom de l\'exposant>",\n'
        '  "booth": "<stand ou null>",\n'
        '  "time_slot": "<créneau horaire ex: 09:30 - 10:00>",\n'
        '  "objective": "<objectif business court>",\n'
        '  "justification": "<justification métier de la visite>"\n'
        "}\n"
        'Retourne un JSON avec la clé "stops" contenant la liste : {"stops": [...]}'
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
                        f"Génère l'itinéraire de visite pour ces {len(relevant)} exposants.\n\n"
                        f"{schema_instruction}\n\n"
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
            items_list: list = []
            if isinstance(data, list):
                items_list = data
            elif isinstance(data, dict):
                for val in data.values():
                    if isinstance(val, list):
                        items_list = val
                        break
                if not items_list and all(isinstance(v, dict) for v in data.values()):
                    items_list = list(data.values())

            stops = []
            for i, item in enumerate(items_list):
                if not isinstance(item, dict):
                    continue
                normalized = {
                    "order": int(item.get("order") or (i + 1)),
                    "exhibitor_id": str(item.get("exhibitor_id") or item.get("id") or f"ex_{i+1}"),
                    "exhibitor_name": str(item.get("exhibitor_name") or item.get("name") or "Inconnu"),
                    "booth": item.get("booth"),
                    "time_slot": item.get("time_slot"),
                    "objective": str(item.get("objective") or "Visite commerciale"),
                    "justification": str(item.get("justification") or item.get("rationale") or "Sélectionné par IA"),
                }
                try:
                    stops.append(ItineraryStop(**normalized))
                except ValidationError:
                    continue
            if stops:
                return stops
        except Exception as exc:
            print(f"[PLANNER RETRY] Erreur parsing itinéraire (tentative {attempt+1}): {exc}")
            await asyncio.sleep(1.0 * (attempt + 1))

    raise PlannerGroqError("Impossible de générer un itinéraire valide après plusieurs tentatives.")