"""
Planner — délègue à generate_itinerary_groq (Llama 3.3 70B via Groq).

Reçoit le prompt_worker généré par GROK en sous-phase Planning.
Fallback sur le tri par score si le Planner Groq échoue.
"""

from orbit.schemas.exhibitor import ClassificationOutput
from orbit.schemas.itinerary import ItineraryStop
from orbit.schemas.run import ICPContext
from orbit.tools.generate_itinerary_groq import PlannerGroqError, generate_itinerary_groq


async def run(
    exhibitors: list[ClassificationOutput],
    icp: ICPContext,
    prompt_override: str | None = None,
) -> list[ItineraryStop]:
    if prompt_override:
        try:
            return await generate_itinerary_groq(exhibitors, prompt_override)
        except PlannerGroqError as exc:
            print(f"[PLANNER] Groq fallback tri-par-score — raison : {exc}")
            return _fallback_sort(exhibitors)

    # Fallback : Gemini si pas de prompt GROK
    from orbit.tools.generate_itinerary import PlannerError, generate_itinerary
    try:
        return await generate_itinerary(exhibitors, icp)
    except PlannerError as exc:
        print(f"[PLANNER] Fallback tri-par-score — raison : {exc}")
        return _fallback_sort(exhibitors)


def _fallback_sort(exhibitors: list[ClassificationOutput]) -> list[ItineraryStop]:
    relevant = [e for e in exhibitors if e.category != "irrelevant"]
    ranked = sorted(relevant, key=lambda e: e.potential_score, reverse=True)
    return [
        ItineraryStop(
            order=i + 1,
            exhibitor_id=e.exhibitor_id,
            exhibitor_name=e.name,
            booth=e.booth,
            time_slot=None,
            objective=_objective(e.category),
            justification="[Fallback] Planner LLM indisponible — ordre par potential_score.",
        )
        for i, e in enumerate(ranked)
    ]


def _objective(category: str) -> str:
    return {
        "client": "Prise de contact + démonstration",
        "partner": "Explorer une opportunité de partenariat",
        "supplier": "Évaluer l'offre fournisseur",
        "competitor": "Veille concurrentielle",
    }.get(category, "À définir")