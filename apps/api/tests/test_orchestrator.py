"""
Tests de l'orchestrateur.

IMPORTANT : depuis l'Objectif 3, scout.run() appelle le vrai Gemini
(search_events). Un test automatise ne doit jamais dependre du reseau/LLM
(voir orbit-contexte-semaine2.md paragraphe 5 "strategie de test") - donc
CHAQUE test qui ne teste pas specifiquement le comportement du Scout
lui-meme doit le mocker explicitement, meme les tests qui semblent ne pas
le concerner directement (ex: tests de select_event, de l'orchestrateur
general) puisque le pipeline complet passe forcement par le stage SCOUT
en premier.
"""

import pytest

from orbit.orchestrator.run import InvalidTransition, advance, run_to_completion, select_event
from orbit.schemas.run import EventCandidate, ICPContext, Objective, RunInput, RunStage, RunState, SelectedEvent


def make_input() -> RunInput:
    return RunInput(
        sector="industrial automation",
        icp=ICPContext(
            target_client_profile="manufacturers >50 employees, EU",
            objectives=[Objective.FIND_CLIENTS],
        ),
        region="France",
    )


def _mock_scout(monkeypatch, events=None):
    """Utilite : centralise le mock du Scout pour eviter de le repeter dans
    chaque test - toujours utiliser cette fonction plutot que d'appeler le
    vrai scout.run() dans un test automatise."""
    from orbit.agents import scout

    default_events = events or [
        EventCandidate(
            name="Salon Mocke 2026",
            dates="2026-09-15/18",
            location="Lyon, FR",
            exhibitor_count=100,
            source_url="https://exemple-mocke.fr/exposants",
        )
    ]

    async def _mocked_scout_run(run_input):
        return default_events

    monkeypatch.setattr(scout, "run", _mocked_scout_run)
    return default_events


async def test_scout_stage_produces_candidates(monkeypatch):
    _mock_scout(monkeypatch)

    state = RunState(client_id="test-client", input=make_input())
    state = await advance(state)

    assert state.stage == RunStage.AWAITING_SELECTION
    assert len(state.candidate_events) > 0


async def test_cannot_advance_while_awaiting_selection(monkeypatch):
    _mock_scout(monkeypatch)

    state = RunState(client_id="test-client", input=make_input())
    state = await advance(state)

    with pytest.raises(InvalidTransition):
        await advance(state)


async def test_full_run_reaches_done_with_mocked_stages(monkeypatch):
    """
    Utilise un Scout ET un Analyst mockes ici : depuis l'Objectif 2/3,
    analyst.run() et scout.run() appellent respectivement le vrai site
    SEPEM Douai et le vrai Gemini - un test automatise ne doit jamais
    dependre du reseau (lent, instable, cassant si le site/l'API change).
    Le vrai scraping est teste separement dans test_fetch_exhibitor_list.py,
    le vrai Scout dans test_search_events.py, tous deux contre des donnees
    locales/mockees.
    """
    from orbit.agents import analyst
    from orbit.schemas.exhibitor import ExhibitorInput

    _mock_scout(monkeypatch)

    async def _mocked_analyst_run(event):
        return [
            ExhibitorInput(id="ex_001", name="Example Corp", booth="A1", raw_description="test"),
            ExhibitorInput(id="ex_002", name="Concurrent SA", booth="A2", raw_description="editeur logiciel"),
        ]

    monkeypatch.setattr(analyst, "run", _mocked_analyst_run)

    state = RunState(client_id="test-client", input=make_input())
    event = SelectedEvent(name="Global Industrie 2026", dates="2026-09-15/18", location="Lyon, FR", exhibitor_count=850)

    state = await run_to_completion(state, event=event)

    assert state.stage == RunStage.DONE
    assert state.selected_event is not None
    assert len(state.exhibitors) > 0
    assert len(state.itinerary) > 0
    # l'itineraire doit etre trie par potential_score decroissant
    scores = [e.potential_score for e in state.exhibitors if e.category != "irrelevant"]
    assert scores == sorted(scores, reverse=True) or len(state.itinerary) <= 1


async def test_select_event_requires_awaiting_selection_stage():
    """Ne necessite PAS de mock Scout : le stage reste SCOUT volontairement,
    on ne fait jamais avancer le run - donc scout.run() n'est jamais appele ici."""
    state = RunState(client_id="test-client", input=make_input())
    event = SelectedEvent(name="X", dates="2026-01-01", location="Paris", exhibitor_count=10)

    with pytest.raises(InvalidTransition):
        select_event(state, event)  # stage encore = SCOUT, pas AWAITING_SELECTION


async def test_source_url_propagates_from_candidate_to_selected_event(monkeypatch):
    """Verifie le chainage dynamique (Objectif 5) : si l'appelant selectionne un
    evenement par son nom sans fournir source_url explicitement, celui-ci doit
    etre recupere automatiquement depuis candidate_events (ce que le Scout a trouve)."""
    _mock_scout(monkeypatch)

    state = RunState(client_id="test-client", input=make_input())
    state = await advance(state)  # scout -> awaiting_selection

    state.candidate_events = [
        EventCandidate(
            name="Salon Reel",
            dates="2026-05-01",
            location="Paris, FR",
            source_url="https://exemple-salon.fr/exposants",
        )
    ]

    # L'appelant ne fournit PAS source_url - juste le nom, comme le ferait un frontend
    event = SelectedEvent(name="Salon Reel", dates="2026-05-01", location="Paris, FR", exhibitor_count=100)
    state = select_event(state, event)

    assert state.selected_event.source_url == "https://exemple-salon.fr/exposants"


async def test_analyst_failure_returns_to_awaiting_selection(monkeypatch):
    """Verifie la decision Option A : un echec de l'Analyst ne fait pas planter
    le run et ne bascule pas silencieusement vers un autre evenement - il
    redonne la main a l'utilisateur avec un message d'erreur clair."""
    from orbit.agents import analyst
    from orbit.tools.fetch_exhibitor_list import ExhibitorFetchError

    _mock_scout(monkeypatch)

    async def _failing_run(event):
        raise ExhibitorFetchError("Site injoignable (simulation de test)")

    monkeypatch.setattr(analyst, "run", _failing_run)

    state = RunState(client_id="test-client", input=make_input())
    event = SelectedEvent(name="Salon Test", dates="2026-01-01", location="Paris", exhibitor_count=10)

    state = await advance(state)  # scout -> awaiting_selection
    state = select_event(state, event)  # awaiting_selection -> analyst
    state = await advance(state)  # analyst (echoue) -> awaiting_selection

    assert state.stage == RunStage.AWAITING_SELECTION
    assert state.error is not None
    assert "injoignable" in state.error
    assert state.selected_event is None