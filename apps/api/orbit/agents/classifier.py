"""
Classifier — classe chaque exposant (client/partenaire/fournisseur/concurrent)
et lui attribue un score de potentiel, avec justification tracable.

SEMAINE 3 : branche sur classify_exhibitor_batch (Gemini, response_schema,
micro-lots, retry partiel, boucle de correction, temperature=0.35).
Voir orbit/tools/classify_exhibitor.py pour le detail des decisions.

Les exposants non classifiables apres correction sont mis en file de revue
manuelle (ClassificationError — meme pattern Option A que ExhibitorFetchError
et EventSearchError). Le run ne s'arrete pas sur un exposant rate.
"""

from orbit.schemas.exhibitor import ClassificationOutput, ExhibitorInput
from orbit.schemas.run import ICPContext
from orbit.tools.classify_exhibitor import classify_exhibitor_batch


async def run_batch(
    exhibitors: list[ExhibitorInput], icp: ICPContext
) -> list[ClassificationOutput]:
    return await classify_exhibitor_batch(exhibitors, icp)