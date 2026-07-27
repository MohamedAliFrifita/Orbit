"""
Orchestrateur — sequence les stages du run ORBIT.

SEMAINE 1 : chaque stage s'execute de maniere synchrone dans le meme process,
            les stages appellent des agents qui renvoient des donnees mockees.
SEMAINE 2 : Scout et Analyst appellent maintenant de vrais tools (recherche web,
            scraping). L'echec de l'Analyst (Objectif 4, Option A) ne fait pas
            planter le run : il renvoie l'utilisateur au choix d'evenement avec
            un message d'erreur clair, plutot que de basculer silencieusement
            vers un autre evenement ou de laisser le run dans un etat casse.
SEMAINE 3+ : chaque stage devient une tache de queue asynchrone separee
            (voir orbit-coding-guide.md §7).
"""

from orbit.agents import analyst, classifier, planner, scout
from orbit.schemas.run import RunStage, RunState, SelectedEvent
from orbit.tools.fetch_exhibitor_list import ExhibitorFetchError
from orbit.tools.search_events import EventSearchError


class InvalidTransition(Exception):
    pass


async def advance(state: RunState) -> RunState:
    """Fait avancer le run d'exactement un stage, puis retourne le nouvel etat.

    Le stage AWAITING_SELECTION necessite une action humaine (voir select_event())
    et n'avance donc jamais tout seul.
    """
    match state.stage:
        case RunStage.SCOUT:
            try:
                state.candidate_events = await scout.run(state.input)
            except EventSearchError as exc:
                # Meme pattern Option A que l'Analyst (voir case ANALYST plus bas) :
                # le run reste au stage SCOUT, message d'erreur clair, aucune
                # liste vide silencieuse. L'utilisateur (ou le prochain appel a
                # /advance) peut alors reessayer.
                state.error = str(exc)
                return state

            state.error = None
            state.stage = RunStage.AWAITING_SELECTION

        case RunStage.AWAITING_SELECTION:
            raise InvalidTransition(
                "En attente de selection humaine - appeler select_event() d'abord."
            )

        case RunStage.ANALYST:
            if state.selected_event is None:
                raise InvalidTransition("Aucun evenement selectionne.")

            try:
                raw_exhibitors = await analyst.run(state.selected_event)
            except ExhibitorFetchError as exc:
                # Option A : on ne bloque pas le run et on ne bascule pas
                # silencieusement vers un autre evenement - on redonne la main
                # a l'utilisateur, qui reste seul decideur de l'evenement choisi.
                state.error = str(exc)
                state.candidate_events = [
                    e for e in state.candidate_events if e.name != state.selected_event.name
                ]
                state.selected_event = None
                state.stage = RunStage.AWAITING_SELECTION
                return state

            state.raw_exhibitor_count = len(raw_exhibitors)
            state.raw_exhibitors = raw_exhibitors
            state.error = None
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
    """Checkpoint humain : l'utilisateur choisit un evenement parmi candidate_events.

    Objectif 5 (chainage dynamique) : si event.source_url n'est pas deja fourni,
    on tente de le retrouver dans candidate_events (celui que le Scout a propose)
    en matchant sur le nom - evite que l'appelant de l'API ait a re-fournir une
    URL que le Scout connait deja.
    """
    if state.stage != RunStage.AWAITING_SELECTION:
        raise InvalidTransition(
            f"select_event() attendu au stage AWAITING_SELECTION, actuel={state.stage}"
        )

    if event.source_url is None:
        matching_candidate = next(
            (c for c in state.candidate_events if c.name == event.name), None
        )
        if matching_candidate is not None:
            event.source_url = matching_candidate.source_url

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
