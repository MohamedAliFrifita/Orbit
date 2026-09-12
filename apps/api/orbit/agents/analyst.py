"""
Analyst - recupere/parse la liste d'exposants d'un evenement selectionne.

SEMAINE 2 : branche sur le vrai tool fetch_exhibitor_list (voir Objectif 1/2).
Cas de test choisi : SEPEM Douai 2026 (site en HTML statique - voir la note
dans tools/fetch_exhibitor_list.py pour le detail du choix).

Les erreurs (site injoignable, parsing qui ne trouve rien) remontent sous forme
de ExhibitorFetchError, geree par l'orchestrateur (Option A - retour au choix
d'evenement, voir orchestrator/run.py).
"""

from orbit.schemas.exhibitor import ExhibitorInput
from orbit.schemas.run import SelectedEvent
from orbit.tools.fetch_exhibitor_list import fetch_exhibitor_list


async def run(event: SelectedEvent, prompt_override: str | None = None) -> list[ExhibitorInput]:
    return await fetch_exhibitor_list(event, prompt_override=prompt_override)