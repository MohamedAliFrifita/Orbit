"""
Scout - identifie les evenements pertinents pour un secteur/objectif donne.

SEMAINE 2 : branche sur le vrai tool search_events (Gemini 2.5 Flash + google_search).
Voir orbit/tools/search_events.py pour le detail des decisions d'AI engineering
(modele, contrainte JSON, anti-hallucination).

Les erreurs (reponse invalide apres re-prompt, aucun evenement trouve) remontent
sous forme de EventSearchError, geree par l'orchestrateur (meme pattern Option A
que ExhibitorFetchError - voir orchestrator/run.py).
"""

from orbit.schemas.run import EventCandidate, RunInput
from orbit.tools.search_events import search_events


async def run(run_input: RunInput) -> list[EventCandidate]:
    return await search_events(run_input)
