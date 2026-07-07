"""
Orchestrateur — sequence les stages du run ORBIT.

SEMAINE 1 : chaque stage s'execute de maniere synchrone dans le meme process,
            les stages appellent des agents qui renvoient des donnees mockees.
SEMAINE 2+ : chaque stage devient une tache de queue asynchrone separee
            (voir orbit-coding-guide.md §7 - discussion RQ/Celery), ce qui permet
            de survivre a un redemarrage serveur et de ne pas bloquer la requete HTTP.

Pour l'instant, `advance()` fait avancer le run d'un seul stage a chaque appel -
c'est volontaire : ca permet de tester chaque transition independamment,
et ca correspond deja a la forme qu'aura chaque tache de queue plus tard.
"""

from orbit.agents import analyst, classifier, planner, scout
from orbit.schemas.run import RunStage, RunState, SelectedEvent


class InvalidTransition(Exception):
    pass


async def advance(state: RunState) -> RunState:
    """Fait avancer le run d'exactement un stage, puis retourne le nouvel etat.

    Le stage AWAITING_SELECTION necessite une action humaine (voir select_event())
    et n'avance donc jamais tout seul.
    """
    match state.stage:
        case RunStage.SCOUT:
            state.candidate_events = await scout.run(state.input)
            state.stage = RunStage.AWAITING_SELECTION

        case RunStage.AWAITING_SELECTION:
            raise InvalidTransition(
                "En attente de selection humaine - appeler select_event() d'abord."
            )

        case RunStage.ANALYST:
            if state.selected_event is None:
                raise InvalidTransition("Aucun evenement selectionne.")
            raw_exhibitors = await analyst.run(state.selected_event)
            state.raw_exhibitor_count = len(raw_exhibitors)
            state.raw_exhibitors = raw_exhibitors
            state.stage = RunStage.CLASSIFIER

        case RunStage.CLASSIFIER:
            classified = await classifier.run_batch(state.raw_exhibitors, state.input.icp)
            state.exhibitors = classified
            state.stage = RunStage.PLANNER

        case RunStage.PLANNER:
            state.itinerary = await planner.run(state.exhibitors)
            state.stage = RunStage.DONE

        case RunStage.DONE | RunStage.FAILED:
            raise InvalidTransition(f"Run deja termine (stage={state.stage}).")

    return state


def select_event(state: RunState, event: SelectedEvent) -> RunState:
    """Checkpoint humain : l'utilisateur choisit un evenement parmi candidate_events."""
    if state.stage != RunStage.AWAITING_SELECTION:
        raise InvalidTransition(
            f"select_event() attendu au stage AWAITING_SELECTION, actuel={state.stage}"
        )
    state.selected_event = event
    state.stage = RunStage.ANALYST
    return state


async def run_to_completion(state: RunState, event: SelectedEvent | None = None) -> RunState:
    """Utilitaire pour les tests / debug : fait avancer un run jusqu'a DONE.

    En prod, chaque stage sera declenche separement par un worker de queue,
    pas enchaine comme ici.
    """
    state = await advance(state)  # scout -> awaiting_selection

    if event is not None:
        state = select_event(state, event)

    while state.stage not in (RunStage.DONE, RunStage.FAILED, RunStage.AWAITING_SELECTION):
        state = await advance(state)

    return state
