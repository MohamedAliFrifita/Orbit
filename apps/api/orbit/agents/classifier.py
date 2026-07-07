"""
Classifier — classe chaque exposant (client/partenaire/fournisseur/concurrent)
et lui attribue un score de potentiel, avec justification tracable.

SEMAINE 1 : logique mockee (regles simples), aucun appel LLM.
SEMAINE 3 : brancher le vrai prompt (orbit/prompts/classifier/v1.md) + appel Anthropic
            + validation stricte contre ClassificationOutput (voir orbit-coding-guide.md §5/§6).
"""

from orbit.schemas.exhibitor import ClassificationOutput, ExhibitorInput
from orbit.schemas.run import ICPContext


async def run_batch(
    exhibitors: list[ExhibitorInput], icp: ICPContext
) -> list[ClassificationOutput]:
    # TODO(semaine 3): remplacer par des appels batches au modele + validation Pydantic stricte
    results: list[ClassificationOutput] = []
    for ex in exhibitors:
        category, score = _mock_classify(ex)
        results.append(
            ClassificationOutput(
                exhibitor_id=ex.id,
                name=ex.name,
                booth=ex.booth,
                category=category,
                potential_score=score,
                rationale=f"Classification mockee (semaine 1) basee sur '{ex.raw_description[:40]}...'",
                confidence="low",
                sources_used=["raw_description"],
            )
        )
    return results


def _mock_classify(exhibitor: ExhibitorInput) -> tuple[str, float]:
    desc = exhibitor.raw_description.lower()
    if "editeur" in desc or "logiciel" in desc:
        return "competitor", 0.3
    if "distributeur" in desc:
        return "supplier", 0.5
    return "client", 0.8
