"""
Planner — genere l'itineraire de visite optimal via LLM (semaine 4).

SEMAINE 1-3 : tri simple par potential_score, aucun appel LLM.
SEMAINE 4   : agent LLM reel (generate_itinerary.py) avec ordonnancement
              metier, creneaux horaires et justification tracable.
              Fallback sur le tri par score si le LLM echoue (PlannerError).
"""

from orbit.schemas.exhibitor import ClassificationOutput
from orbit.schemas.itinerary import ItineraryStop
from orbit.schemas.run import ICPContext
from orbit.tools.generate_itinerary import PlannerError, generate_itinerary


async def run(
    exhibitors: list[ClassificationOutput],
    icp: ICPContext,
) -> list[ItineraryStop]:
    """
    Genere l'itineraire via le Planner LLM.
    En cas d'echec (PlannerError), bascule sur le fallback tri-par-score
    pour ne jamais bloquer le run — meme pattern Option A que l'Analyst.
    """
    try:
        return await generate_itinerary(exhibitors, icp)
    except PlannerError as exc:
        print(f"[PLANNER] Fallback tri-par-score active — raison : {exc}")
        return _fallback_sort(exhibitors)


def _fallback_sort(exhibitors: list[ClassificationOutput]) -> list[ItineraryStop]:
    """
    Fallback semaine 1 : tri par potential_score décroissant.
    Utilise uniquement si le Planner LLM est indisponible.
    """
    relevant = [e for e in exhibitors if e.category != "irrelevant"]
    ranked = sorted(relevant, key=lambda e: e.potential_score, reverse=True)

    return [
        ItineraryStop(
            order=i + 1,
            exhibitor_id=e.exhibitor_id,
            exhibitor_name=e.name,
            booth=e.booth,
            time_slot=None,
            objective=_objective_for_category(e.category),
            justification="[Fallback] Planner LLM indisponible — ordre par potential_score.",
        )
        for i, e in enumerate(ranked)
    ]


def _objective_for_category(category: str) -> str:
    return {
        "client": "Prise de contact + demonstration",
        "partner": "Explorer une opportunite de partenariat",
        "supplier": "Evaluer l'offre fournisseur",
        "competitor": "Veille concurrentielle",
    }.get(category, "A definir")
