"""
Orchestrateur ORBIT — nouvelle architecture 3 sous-phases par stage.

Chaque stage exécute séquentiellement :
  1. Planning  (GROK) → génère prompt_worker + success_criteria
  2. Working   (Worker : Gemini / Groq) → exécute la tâche
  3. Judging   (Mistral) → évalue le résultat

Le verdict du Judge contrôle la progression :
  PASS   → stage suivant
  REFINE → GROK réécrit le prompt_worker, Working relancé (max 2 retries)
  REWORK → retour au stage précédent (max 1 REWORK par stage)
"""

from __future__ import annotations

import json
from collections.abc import Callable, Coroutine
from typing import Any

from orbit.agents import analyst, classifier, planner, scout
from orbit.judge import run as judge_module
from orbit.orchestrator import planning
from orbit.schemas.judge import JudgeInput, JudgeVerdict
from orbit.schemas.run import RunStage, RunState, SelectedEvent, SubPhase, StagePlan
from orbit.tools.fetch_exhibitor_list import ExhibitorFetchError
from orbit.tools.search_events import EventSearchError

MAX_RETRIES = 2   # tentatives REFINE max par stage avant force-PASS

# Stage précédent pour un REWORK
_REWORK_TARGET: dict[RunStage, RunStage] = {
    RunStage.ANALYST: RunStage.SCOUT,
    RunStage.CLASSIFIER: RunStage.ANALYST,
    RunStage.PLANNER: RunStage.CLASSIFIER,
}

# Publier = no-op par défaut (tests / sans SSE)
_NOOP: Callable[[dict], Coroutine] = lambda _: _noop_coro()

async def _noop_coro() -> None:
    pass


class InvalidTransition(Exception):
    pass


# ── Workers wrappers ──────────────────────────────────────────────────────────

async def _scout_worker(state: RunState, prompt_worker: str) -> list:
    """Appelle le Scout avec le prompt GROK-généré."""
    return await scout.run(state.input, prompt_override=prompt_worker)


async def _analyst_worker(state: RunState, prompt_worker: str) -> list:
    """Appelle l'Analyst avec le prompt GROK-généré."""
    if state.selected_event is None:
        raise InvalidTransition("Aucun événement sélectionné pour l'Analyst.")
    return await analyst.run(state.selected_event, prompt_override=prompt_worker)


async def _classifier_worker(state: RunState, prompt_worker: str) -> list:
    """Appelle le Classifier (Groq) avec le prompt GROK-généré."""
    return await classifier.run_batch(
        state.raw_exhibitors, state.input.icp, prompt_override=prompt_worker
    )


async def _planner_worker(state: RunState, prompt_worker: str) -> list:
    """Appelle le Planner (Groq) avec le prompt GROK-généré."""
    return await planner.run(
        state.exhibitors, state.input.icp, prompt_override=prompt_worker
    )


# ── Sous-phase engine ─────────────────────────────────────────────────────────

async def _run_stage_with_judge(
    state: RunState,
    stage: RunStage,
    worker_fn: Callable,
    publish: Callable[[dict], Coroutine] = _NOOP,
) -> tuple[RunState, Any]:
    """
    Exécute les 3 sous-phases d'un stage.
    Retourne (state, worker_output) — worker_output est None si le stage
    n'a pas abouti (pause, erreur, REWORK).
    """

    # ── Sous-phase 1 : PLANNING ──────────────────────────────────────
    if state.paused:
        state.paused_at_stage = stage
        state.paused_at_subphase = SubPhase.PLANNING
        return state, None

    await publish({"event": "subphase_started", "stage": stage.value, "subphase": "planning"})

    plan: StagePlan = await planning.plan_stage(state, stage)
    state.stage_plans[stage.value] = plan.model_dump()

    await publish({"event": "subphase_completed", "stage": stage.value, "subphase": "planning",
                   "success_criteria": plan.success_criteria})

    # ── Sous-phases 2+3 : WORKING + JUDGING (avec retries) ───────────
    attempt = 0
    current_plan = plan

    while True:
        attempt += 1
        state.retry_counts[stage.value] = attempt - 1

        # Sous-phase 2 : WORKING
        if state.paused:
            state.paused_at_stage = stage
            state.paused_at_subphase = SubPhase.WORKING
            return state, None

        await publish({
            "event": "subphase_started", "stage": stage.value,
            "subphase": "working", "attempt": attempt,
        })

        try:
            worker_output = await worker_fn(state, current_plan.prompt_worker)
        except (EventSearchError, ExhibitorFetchError) as exc:
            state.error = str(exc)
            await publish({"event": "stage_error", "stage": stage.value, "error": str(exc)})
            return state, None

        await publish({"event": "subphase_completed", "stage": stage.value, "subphase": "working"})

        # Sous-phase 3 : JUDGING
        if state.paused:
            state.paused_at_stage = stage
            state.paused_at_subphase = SubPhase.JUDGING
            return state, None

        await publish({"event": "subphase_started", "stage": stage.value, "subphase": "judging"})

        verdict: JudgeVerdict = await judge_module.judge(
            JudgeInput(
                stage=stage.value,
                icp_context=state.input.icp.model_dump_json(),
                success_criteria=current_plan.success_criteria,
                worker_output=json.dumps(
                    [w if isinstance(w, dict) else w.model_dump() for w in worker_output]
                    if isinstance(worker_output, list)
                    else worker_output,
                    ensure_ascii=False,
                    default=str,
                ),
            ),
            attempt_number=attempt,
        )

        await publish({
            "event": "judge_verdict",
            "stage": stage.value,
            "verdict": verdict.verdict,
            "score": verdict.score,
            "reasoning": verdict.reasoning,
            "suggestions": verdict.suggestions,
            "attempt": attempt,
        })

        # ── Décision ──────────────────────────────────────────────────
        if verdict.verdict == "PASS":
            state.error = None
            return state, worker_output

        elif verdict.verdict == "REFINE":
            if attempt >= MAX_RETRIES:
                # Force PASS avec flag low_confidence
                state.low_confidence = True
                if stage.value not in state.low_confidence_stages:
                    state.low_confidence_stages.append(stage.value)
                state.error = None
                await publish({
                    "event": "forced_pass",
                    "stage": stage.value,
                    "reason": "Max retries atteint — PASS forcé avec low_confidence",
                })
                return state, worker_output
            # Re-Planning partiel
            current_plan = await planning.refine_plan(state, current_plan, verdict)
            state.stage_plans[stage.value] = current_plan.model_dump()
            continue

        elif verdict.verdict == "REWORK":
            rework_target = _REWORK_TARGET.get(stage)
            if rework_target and state.retry_counts.get(f"rework_{stage.value}", 0) < 2:
                state.retry_counts[f"rework_{stage.value}"] += 1
                state.stage = rework_target
                await publish({
                    "event": "rework",
                    "stage": stage.value,
                    "target_stage": rework_target.value,
                })
            else:
                # REWORK impossible (déjà reworké ou stage Scout) → force PASS
                state.low_confidence = True
                if stage.value not in state.low_confidence_stages:
                    state.low_confidence_stages.append(stage.value)
                state.error = None
                return state, worker_output
            return state, None


# ── API publique ──────────────────────────────────────────────────────────────

async def advance(
    state: RunState,
    publish: Callable[[dict], Coroutine] = _NOOP,
) -> RunState:
    """
    Fait avancer le run d'exactement un stage (3 sous-phases).
    Retourne le nouvel état.
    """
    match state.stage:

        case RunStage.SCOUT:
            await publish({"event": "stage_started", "stage": "scout"})
            state, output = await _run_stage_with_judge(
                state, RunStage.SCOUT, _scout_worker, publish
            )
            if output is not None:
                state.candidate_events = output
                state.stage = RunStage.AWAITING_SELECTION
                await publish({"event": "stage_completed", "stage": "scout",
                               "candidate_count": len(output)})

        case RunStage.AWAITING_SELECTION:
            raise InvalidTransition("En attente de sélection humaine — appeler select_event().")

        case RunStage.ANALYST:
            if state.selected_event is None:
                raise InvalidTransition("Aucun événement sélectionné.")
            await publish({"event": "stage_started", "stage": "analyst"})
            state, output = await _run_stage_with_judge(
                state, RunStage.ANALYST, _analyst_worker, publish
            )
            if output is not None and state.stage == RunStage.ANALYST:
                state.raw_exhibitor_count = len(output)
                state.raw_exhibitors = [
                    e.model_dump() if hasattr(e, "model_dump") else e for e in output
                ]
                state.stage = RunStage.CLASSIFIER
                await publish({"event": "stage_completed", "stage": "analyst",
                               "exhibitor_count": len(output)})
            elif output is None:
                # Échec extraction (aucun exposant trouvé) -> retour au choix d'événement
                state.stage = RunStage.AWAITING_SELECTION
                state.selected_event = None
                await publish({
                    "event": "returned_to_selection",
                    "stage": "awaiting_selection",
                    "reason": state.error or "Aucun exposant trouvé sur ce salon. Choisissez un autre événement."
                })

        case RunStage.CLASSIFIER:
            await publish({"event": "stage_started", "stage": "classifier"})
            state, output = await _run_stage_with_judge(
                state, RunStage.CLASSIFIER, _classifier_worker, publish
            )
            if output is not None and state.stage == RunStage.CLASSIFIER:
                state.exhibitors = [
                    e.model_dump() if hasattr(e, "model_dump") else e for e in output
                ]
                state.stage = RunStage.PLANNER
                await publish({"event": "stage_completed", "stage": "classifier",
                               "classified_count": len(output)})

        case RunStage.PLANNER:
            await publish({"event": "stage_started", "stage": "planner"})
            state, output = await _run_stage_with_judge(
                state, RunStage.PLANNER, _planner_worker, publish
            )
            if output is not None and state.stage == RunStage.PLANNER:
                state.itinerary = [
                    e.model_dump() if hasattr(e, "model_dump") else e for e in output
                ]
                state.stage = RunStage.DONE
                await publish({"event": "run_done",
                               "stop_count": len(output),
                               "low_confidence": state.low_confidence})

        case RunStage.DONE | RunStage.FAILED:
            raise InvalidTransition(f"Run déjà terminé (stage={state.stage}).")

    return state


def select_event(state: RunState, event: SelectedEvent) -> RunState:
    """Checkpoint humain : l'utilisateur choisit un événement."""
    if state.stage != RunStage.AWAITING_SELECTION:
        raise InvalidTransition(
            f"select_event() attendu au stage AWAITING_SELECTION, actuel={state.stage}"
        )

    if event.source_url is None:
        matching = next(
            (c for c in state.candidate_events if c.name == event.name), None
        )
        if matching:
            event.source_url = matching.source_url

    state.selected_event = event
    state.stage = RunStage.ANALYST
    return state