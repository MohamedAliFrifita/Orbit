"""
Classifier — délègue à classify_exhibitor_groq (Llama 3.3 70B via Groq).

Reçoit le prompt_worker généré par GROK en sous-phase Planning.
Applique le plafond MAX_EXHIBITORS avant de passer au tool.
"""

import os

from orbit.schemas.exhibitor import ClassificationOutput, ExhibitorInput
from orbit.schemas.run import ICPContext
from orbit.tools.classify_exhibitor_groq import classify_exhibitor_batch_groq

MAX_EXHIBITORS = int(os.environ.get("ORBIT_MAX_EXHIBITORS", "25"))


async def run_batch(
    exhibitors: list[ExhibitorInput],
    icp: ICPContext,
    prompt_override: str | None = None,
) -> list[ClassificationOutput]:
    if len(exhibitors) > MAX_EXHIBITORS:
        print(
            f"[CLASSIFIER] {len(exhibitors)} exposants reçus — "
            f"tronqué à {MAX_EXHIBITORS} (ORBIT_MAX_EXHIBITORS)."
        )
        exhibitors = exhibitors[:MAX_EXHIBITORS]

    if prompt_override:
        return await classify_exhibitor_batch_groq(exhibitors, prompt_override)

    # Fallback : utiliser l'ancien tool Gemini si pas de prompt GROK
    from orbit.tools.classify_exhibitor import classify_exhibitor_batch
    return await classify_exhibitor_batch(exhibitors, icp)