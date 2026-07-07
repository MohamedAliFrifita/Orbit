"""
Scout — identifie les evenements pertinents pour un secteur/objectif donne.

SEMAINE 1 : donnees mockees, aucun appel externe.
SEMAINE 2 : brancher `tools.search_events` (recherche web / API d'annuaire d'evenements).
"""

from orbit.schemas.run import EventCandidate, RunInput


async def run(run_input: RunInput) -> list[EventCandidate]:
    # TODO(semaine 2): remplacer par un vrai appel a tools.search_events(run_input)
    return [
        EventCandidate(
            name="Global Industrie 2026",
            dates="2026-09-15/18",
            location="Lyon, FR",
            exhibitor_count=850,
            source_url="https://example.com/global-industrie",
            relevance_note=f"Correspond au secteur '{run_input.sector}' en {run_input.region}",
        ),
        EventCandidate(
            name="SIDO Lyon 2026",
            dates="2026-10-05/06",
            location="Lyon, FR",
            exhibitor_count=300,
            source_url="https://example.com/sido",
            relevance_note="Salon IoT/automatisation, plus petit mais cible",
        ),
    ]
