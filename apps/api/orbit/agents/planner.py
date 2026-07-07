"""
Planner — sequence les visites par priorite (score de potentiel + logistique).

SEMAINE 1 : tri simple par potential_score, pas de contrainte horaire/logistique reelle.
SEMAINE 4 : ajouter la contrainte de localisation de stand (plan de salle) et les creneaux horaires.
"""

from orbit.schemas.exhibitor import ClassificationOutput
from orbit.schemas.itinerary import ItineraryStop


async def run(exhibitors: list[ClassificationOutput]) -> list[ItineraryStop]:
    relevant = [e for e in exhibitors if e.category != "irrelevant"]
    ranked = sorted(relevant, key=lambda e: e.potential_score, reverse=True)

    return [
        ItineraryStop(
            order=i + 1,
            exhibitor_id=e.exhibitor_id,
            exhibitor_name=e.name,
            booth=e.booth,
            time_slot=None,  # TODO(semaine 4): assigner un vrai creneau
            objective=_objective_for_category(e.category),
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
