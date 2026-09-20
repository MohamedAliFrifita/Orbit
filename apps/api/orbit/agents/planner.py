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


def _fallback_sort(exhibitors: list) -> list[ItineraryStop]:
    def _cat(e):
        return e.category if hasattr(e, "category") else e.get("category", "irrelevant")

    def _score(e):
        return e.potential_score if hasattr(e, "potential_score") else e.get("potential_score", 0.0)

    def _val(e, key, default=""):
        return getattr(e, key) if hasattr(e, key) else e.get(key, default)

    relevant = [e for e in exhibitors if _cat(e) != "irrelevant"]
    ranked = sorted(relevant, key=_score, reverse=True)

    return [
        ItineraryStop(
            order=i + 1,
            exhibitor_id=_val(e, "exhibitor_id", f"ex_{i+1}"),
            exhibitor_name=_val(e, "name", "Inconnu"),
            booth=_val(e, "booth", None),
            time_slot=None,
            objective=_objective(_cat(e)),
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