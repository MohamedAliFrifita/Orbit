"""
Sous-phase Planning — GROK génère le prompt_worker et les success_criteria
pour chaque stage. Appelé au début de chaque stage par l'orchestrateur.
"""

from __future__ import annotations

import json

from orbit.orchestrator.grok_client import GROK_MODEL, get_grok_client
from orbit.prompts import load_prompt
from orbit.schemas.judge import JudgeVerdict
from orbit.schemas.run import RunStage, RunState, StagePlan

# Mapping stage → nom du prompt versionné
_STAGE_PROMPT_ROLE: dict[RunStage, str] = {
    RunStage.SCOUT: "grok_scout",
    RunStage.ANALYST: "grok_analyst",
    RunStage.CLASSIFIER: "grok_classifier",
    RunStage.PLANNER: "grok_planner",
}


def _build_context(state: RunState, stage: RunStage) -> str:
    """Construit le message utilisateur injecté dans le prompt GROK."""
    lines = [
        f"Secteur : {state.input.sector}",
        f"Région : {state.input.region}",
        f"Profil ICP : {state.input.icp.target_client_profile}",
        f"Objectifs : {', '.join(o.value for o in state.input.icp.objectives)}",
    ]
    if state.input.date_range_start:
        lines.append(f"Période : {state.input.date_range_start} → {state.input.date_range_end}")

    if stage == RunStage.ANALYST and state.selected_event:
        ev = state.selected_event
        lines += [
            f"Événement : {ev.name}",
            f"Dates : {ev.dates}",
            f"Lieu : {ev.location}",
            f"URL : {ev.source_url or 'non disponible'}",
        ]

    if stage in (RunStage.CLASSIFIER, RunStage.PLANNER):
        lines.append(f"Nombre d'exposants à traiter : {len(state.raw_exhibitors)}")

    if stage == RunStage.PLANNER and state.exhibitors:
        cats = {}
        for e in state.exhibitors:
            cat = e.category if hasattr(e, "category") else e.get("category", "?")
            cats[cat] = cats.get(cat, 0) + 1
        lines.append(f"Répartition catégories : {json.dumps(cats, ensure_ascii=False)}")

    return "\n".join(lines)


async def plan_stage(state: RunState, stage: RunStage) -> StagePlan:
    """
    Sous-phase Planning : GROK lit le prompt système du stage et génère
    { prompt_worker, success_criteria }.
    """
    role = _STAGE_PROMPT_ROLE[stage]
    system_prompt = load_prompt(role, "v1")
    user_message = _build_context(state, stage)

    client = get_grok_client()
    resp = await client.chat.completions.create(
        model=GROK_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )

    raw = resp.choices[0].message.content
    data = json.loads(raw)

    return StagePlan(
        prompt_worker=data["prompt_worker"],
        success_criteria=data["success_criteria"],
    )


async def refine_plan(
    state: RunState,
    current_plan: StagePlan,
    verdict: JudgeVerdict,
) -> StagePlan:
    """
    Re-Planning partiel après un verdict REFINE :
    GROK réécrit uniquement le prompt_worker en tenant compte des suggestions du Judge.
    Les success_criteria restent inchangés.
    """
    client = get_grok_client()
    resp = await client.chat.completions.create(
        model=GROK_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Tu es l'orchestrateur ORBIT. Le Judge a rejeté le résultat du worker. "
                    "Réécris uniquement le prompt_worker pour corriger les problèmes identifiés. "
                    "Retourne un JSON avec exactement deux clés : "
                    "{ \"prompt_worker\": \"...\", \"success_criteria\": {...} }. "
                    "Conserve les success_criteria inchangés."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Prompt worker actuel :\n{current_plan.prompt_worker}\n\n"
                    f"Verdict Judge : {verdict.verdict} (score {verdict.score}/10)\n"
                    f"Raison : {verdict.reasoning}\n"
                    f"Suggestions : {verdict.suggestions or 'aucune'}\n\n"
                    f"Critères de succès (à conserver) :\n"
                    f"{json.dumps(current_plan.success_criteria, ensure_ascii=False, indent=2)}"
                ),
            },
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
    )

    data = json.loads(resp.choices[0].message.content)
    return StagePlan(
        prompt_worker=data["prompt_worker"],
        success_criteria=current_plan.success_criteria,  # toujours inchangé
    )