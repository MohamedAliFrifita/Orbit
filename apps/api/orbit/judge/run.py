"""
Judge Mistral — évalue le résultat d'un worker en mode référence-based.

Le Judge reçoit :
  - Le prompt système versionné (prompts/judge/v1.md)
  - Les success_criteria générés par GROK en sous-phase Planning
  - Le résultat JSON du worker

Il rend un verdict : PASS | REFINE | REWORK
"""

from __future__ import annotations

import json

from mistralai.client import Mistral

from orbit.config import settings
from orbit.prompts import load_prompt
from orbit.schemas.judge import JudgeInput, JudgeVerdict

MISTRAL_MODEL = "codestral-2508"
_client: Mistral | None = None


def get_mistral_client() -> Mistral:
    global _client
    if _client is None:
        _client = Mistral(api_key=settings.mistral_api_key)
    return _client


async def judge(judge_input: JudgeInput, attempt_number: int = 1) -> JudgeVerdict:
    """
    Évalue le résultat d'un stage worker via Mistral.
    Retourne un JudgeVerdict avec verdict, score, reasoning et suggestions.
    """
    system_prompt = load_prompt("judge", "v1")

    user_message = (
        f"## Contexte ICP\n{judge_input.icp_context}\n\n"
        f"## Critères de succès de référence\n"
        f"{json.dumps(judge_input.success_criteria, ensure_ascii=False, indent=2)}\n\n"
        f"## Résultat à évaluer (stage : {judge_input.stage})\n"
        f"{judge_input.worker_output}"
    )

    client = get_mistral_client()
    resp = await client.chat.complete_async(
        model=MISTRAL_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,   # très bas : on veut un juge cohérent et reproductible
    )

    raw = resp.choices[0].message.content
    data = json.loads(raw)

    return JudgeVerdict(
        verdict=data["verdict"],
        score=float(data["score"]),
        reasoning=data["reasoning"],
        suggestions=data.get("suggestions"),
        attempt_number=attempt_number,
    )