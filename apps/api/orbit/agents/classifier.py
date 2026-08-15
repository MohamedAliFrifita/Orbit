"""
Classifier — classe chaque exposant (client/partenaire/fournisseur/concurrent)
et lui attribue un score de potentiel, avec justification tracable.

SEMAINE 3 : branche sur classify_exhibitor_batch (Gemini, response_schema,
micro-lots, retry partiel, boucle de correction, temperature=0.35).
Voir orbit/tools/classify_exhibitor.py pour le detail des decisions.

Les exposants non classifiables apres correction sont mis en file de revue
manuelle (ClassificationError — meme pattern Option A que ExhibitorFetchError
et EventSearchError). Le run ne s'arrete pas sur un exposant rate.

Objectif C7 : plafond MAX_EXHIBITORS applique ici, pas dans classify_exhibitor_batch
— l'outil reste generique, c'est l'agent qui impose la politique du run
(voir orbit-semaine3-guide.md §6 pour la justification complete du plafond).
"""

import os

from orbit.schemas.exhibitor import ClassificationOutput, ExhibitorInput
from orbit.schemas.run import ICPContext
from orbit.tools.classify_exhibitor import classify_exhibitor_batch

MAX_EXHIBITORS = int(os.environ.get("ORBIT_MAX_EXHIBITORS", "25"))


async def run_batch(
    exhibitors: list[ExhibitorInput], icp: ICPContext
) -> list[ClassificationOutput]:
    if len(exhibitors) > MAX_EXHIBITORS:
        print(
            f"[CLASSIFIER] {len(exhibitors)} exposants recus — "
            f"tronque a {MAX_EXHIBITORS} (ORBIT_MAX_EXHIBITORS). "
            "Les exposants restants ne sont pas classifies dans ce run."
        )
        exhibitors = exhibitors[:MAX_EXHIBITORS]
    return await classify_exhibitor_batch(exhibitors, icp)