"""
Follow-up — genere des messages de relance post-evenement (brouillons uniquement,
jamais d'envoi automatique - voir orbit-agent-design-guide.md §6/§9).

SEMAINE 5 : a implementer. Place-holder pour l'instant.
"""

from orbit.schemas.exhibitor import ClassificationOutput


async def draft_followup(lead: ClassificationOutput) -> str:
    raise NotImplementedError("Follow-up agent arrive en semaine 5 (voir orbit-coding-guide.md §8)")
