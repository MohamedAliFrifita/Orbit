"""
generate_itinerary — Planner tool reel (semaine 4).

DECISIONS D'AI ENGINEERING :

1. response_schema natif : JSON garanti conforme, pas de post-parsing fragile.
   Meme pattern que classify_exhibitor.py.

2. Appel unique (pas de batching) : l'itineraire est une tache globale qui
   necessite de raisonner sur l'ensemble des exposants simultanement pour
   optimiser l'ordre et les creneaux. Un appel par exposant perdrait le
   contexte d'ordonnancement.

3. Temperature=0.3 : bas pour garantir un itineraire coherent et reproductible,
   suffisant pour des justifications variees et non-mecaniques.

4. Retry/backoff sur 429 : 3 tentatives max, backoff 1s->2s->4s.
   Meme pattern que classify_exhibitor.py.

5. Validation Pydantic stricte : chaque ItineraryStop est valide
   individuellement avant d'etre ajoute a la liste finale.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from google import genai
from google.genai import types
from pydantic import ValidationError

from orbit.config import settings
from orbit.prompts import load_prompt
from orbit.schemas.exhibitor import ClassificationOutput
from orbit.schemas.itinerary import ItineraryStop
from orbit.schemas.run import ICPContext

MODEL_NAME = os.environ.get("ORBIT_PLANNER_MODEL", "gemini-2.5-flash")
_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0  # secondes

_ITINERARY_RESPONSE_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "order":           {"type": "INTEGER"},
            "exhibitor_id":    {"type": "STRING"},
            "exhibitor_name":  {"type": "STRING"},
            "booth":           {"type": "STRING", "nullable": True},
            "time_slot":       {"type": "STRING"},
            "objective":       {"type": "STRING"},
            "justification":   {"type": "STRING"},
        },
        "required": [
            "order", "exhibitor_id", "exhibitor_name",
            "time_slot", "objective", "justification",
        ],
    },
}


class PlannerError(Exception):
    """
    Levee quand l'itineraire ne peut pas etre genere apres les tentatives.
    L'appelant (agents/planner.py) doit loguer et retourner un fallback
    (tri par potential_score) plutot que de faire planter le run.
    Meme pattern Option A que ClassificationError.
    """
    pass


def _get_client() -> genai.Client:
    if not settings.gemini_api_key:
        raise PlannerError(
            "GEMINI_API_KEY manquante dans .env — voir aistudio.google.com/apikey"
        )
    return genai.Client(api_key=settings.gemini_api_key)


def _build_config(system_prompt: str) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type="application/json",
        response_schema=_ITINERARY_RESPONSE_SCHEMA,
        temperature=0.3,
    )


def _build_planner_prompt(
    exhibitors: list[ClassificationOutput],
    icp: ICPContext,
) -> str:
    """Construit le prompt utilisateur : ICP + liste des exposants classes."""
    relevant = [e for e in exhibitors if e.category != "irrelevant"]
    exhibitors_json = json.dumps(
        [e.model_dump() for e in relevant],
        ensure_ascii=False, indent=2
    )
    return (
        f"ICP:\n{icp.model_dump_json(indent=2)}\n\n"
        f"Exposants classes ({len(relevant)} exposants pertinents) :\n"
        f"{exhibitors_json}\n\n"
        "Genere l'itineraire de visite optimal pour cette journee salon."
    )


async def _call_with_retry(
    client: genai.Client,
    config: types.GenerateContentConfig,
    prompt: str,
) -> str:
    """Appel Gemini avec retry/backoff sur 429 (RESOURCE_EXHAUSTED)."""
    for attempt in range(_MAX_RETRIES):
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=MODEL_NAME,
                contents=prompt,
                config=config,
            )
            return response.text
        except Exception as exc:
            if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
                if attempt < _MAX_RETRIES - 1:
                    wait = _BACKOFF_BASE * (2 ** attempt)
                    await asyncio.sleep(wait)
                    continue
            raise PlannerError(f"Erreur API Gemini: {exc}") from exc
    raise PlannerError("Quota depasse — max tentatives atteint.")


def _validate_stop(raw_item: dict[str, Any], index: int) -> tuple[ItineraryStop | None, str]:
    """
    Valide un arret brut. Retourne (stop, '') ou (None, message_erreur).
    Corrige l'order si absent ou incorrect.
    """
    try:
        if not raw_item.get("order"):
            raw_item["order"] = index + 1
        stop = ItineraryStop.model_validate(raw_item)
        return stop, ""
    except (ValidationError, ValueError) as exc:
        return None, str(exc)


async def generate_itinerary(
    exhibitors: list[ClassificationOutput],
    icp: ICPContext,
) -> list[ItineraryStop]:
    """
    Genere un itineraire de visite optimal via le Planner LLM.

    - Filtre les exposants "irrelevant" avant d'envoyer au modele.
    - Valide chaque ItineraryStop individuellement via Pydantic.
    - Leve PlannerError si la reponse est inutilisable apres les retries.

    L'appelant (agents/planner.py) doit attraper PlannerError et
    basculer sur le fallback tri-par-score.
    """
    relevant = [e for e in exhibitors if e.category != "irrelevant"]
    if not relevant:
        return []

    client = _get_client()
    system_prompt = load_prompt("planner", version="v1")
    config = _build_config(system_prompt)
    prompt = _build_planner_prompt(exhibitors, icp)

    raw_text = await _call_with_retry(client, config, prompt)

    try:
        raw_list = json.loads(raw_text)
        if not isinstance(raw_list, list):
            raw_list = [raw_list]
    except (json.JSONDecodeError, TypeError) as exc:
        raise PlannerError(f"Reponse JSON invalide du Planner LLM: {exc}") from exc

    stops: list[ItineraryStop] = []
    for i, raw_item in enumerate(raw_list):
        if not isinstance(raw_item, dict):
            print(f"[PLANNER] Item {i} ignore : pas un dict — {raw_item!r}")
            continue
        stop, error_msg = _validate_stop(raw_item, i)
        if stop is not None:
            stops.append(stop)
        else:
            print(f"[PLANNER] Item {i} invalide : {error_msg}")

    if not stops:
        raise PlannerError(
            "Aucun arret valide genere par le Planner LLM. "
            "Verifier le prompt et le response_schema."
        )

    # Re-numerote les stops dans l'ordre final
    for i, stop in enumerate(stops):
        stop.order = i + 1

    return stops
