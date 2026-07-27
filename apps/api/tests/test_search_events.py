"""
Tests de search_events.py — TOUJOURS mockes, jamais de vrai appel a l'API Gemini.

Utilite (Decision "strategie de test", voir orbit-contexte-semaine2.md §5) :
un appel reel serait lent, non deterministe (le modele peut repondre
differemment a chaque fois), et consommerait le quota gratuit journalier a
chaque `pytest -v`. Le test manuel avec une vraie cle API est fait separement,
hors pytest (voir Etape 6 de l'Objectif 3).
"""

from types import SimpleNamespace

import pytest

from orbit.schemas.run import ICPContext, Objective, RunInput
from orbit.tools.search_events import EventSearchError, search_events


def make_input() -> RunInput:
    return RunInput(
        sector="industrial automation",
        icp=ICPContext(
            target_client_profile="manufacturers >50 employees, EU",
            objectives=[Objective.FIND_CLIENTS],
        ),
        region="France",
    )


def _fake_response(text: str, grounded_domains: list[str] | None = None):
    """
    Construit un faux objet reponse Gemini, avec la meme forme que le vrai SDK :
    response.text + response.candidates[].grounding_metadata.grounding_chunks[].web.domain
    """
    chunks = [SimpleNamespace(web=SimpleNamespace(domain=d)) for d in (grounded_domains or [])]
    metadata = SimpleNamespace(grounding_chunks=chunks) if grounded_domains is not None else None
    candidate = SimpleNamespace(grounding_metadata=metadata)
    return SimpleNamespace(text=text, candidates=[candidate])


async def test_parses_valid_json_response(monkeypatch):
    import json as json_module

    from orbit.schemas.run import EventCandidate

    valid_json = """[
        {
            "name": "SEPEM Douai 2026",
            "dates": "2026-03-19",
            "location": "Douai, FR",
            "exhibitor_count": 300,
            "source_url": "https://douai.sepem-industries.com/content/liste-des-exposants",
            "relevance_note": "Salon industriel regional cible sur la maintenance et l'automatisation"
        }
    ]"""
    response = _fake_response(valid_json, grounded_domains=["douai.sepem-industries.com"])

    async def fake_call_and_parse(client, config, prompt):
        raw_items = json_module.loads(valid_json)
        events = [EventCandidate.model_validate(i) for i in raw_items]
        return events, response

    monkeypatch.setattr("orbit.tools.search_events._call_and_parse", fake_call_and_parse)
    monkeypatch.setattr("orbit.tools.search_events._get_client", lambda: object())

    events = await search_events(make_input())

    assert len(events) == 1
    assert events[0].name == "SEPEM Douai 2026"
    # Le domaine cite correspond a un domaine reellement "grounde" -> pas d'annotation d'alerte
    assert "ATTENTION" not in (events[0].relevance_note or "")


async def test_flags_ungrounded_source_as_suspicious(monkeypatch):
    """Verifie la Decision 3 (anti-hallucination) : une source_url dont le domaine
    n'apparait pas dans grounding_chunks doit etre signalee, pas acceptee telle quelle."""
    from orbit.schemas.run import EventCandidate

    fake_event = EventCandidate(
        name="Salon Invente 2026",
        dates="2026-01-01",
        location="Paris, FR",
        source_url="https://ce-domaine-n-a-jamais-ete-cherche.com/salon",
        relevance_note="Semble pertinent",
    )
    response = _fake_response("[]", grounded_domains=["un-autre-domaine-reel.com"])

    async def fake_call_and_parse(client, config, prompt):
        return [fake_event], response

    monkeypatch.setattr("orbit.tools.search_events._call_and_parse", fake_call_and_parse)
    monkeypatch.setattr("orbit.tools.search_events._get_client", lambda: object())

    events = await search_events(make_input())

    assert "ATTENTION" in events[0].relevance_note


async def test_retries_once_on_invalid_json_then_succeeds(monkeypatch):
    """Verifie la Decision 4 : un seul re-prompt correctif si le JSON est invalide."""
    from orbit.schemas.run import EventCandidate

    call_count = {"n": 0}

    async def fake_call_and_parse(client, config, prompt):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return None, _fake_response("ceci n'est pas du json")
        return (
            [EventCandidate(name="Salon Corrige", dates="2026-01-01", location="Lyon, FR")],
            _fake_response("[]", grounded_domains=[]),
        )

    monkeypatch.setattr("orbit.tools.search_events._call_and_parse", fake_call_and_parse)
    monkeypatch.setattr("orbit.tools.search_events._get_client", lambda: object())

    events = await search_events(make_input())

    assert call_count["n"] == 2  # 1 essai initial + 1 re-prompt correctif
    assert events[0].name == "Salon Corrige"


async def test_raises_after_second_invalid_json(monkeypatch):
    """Si meme le re-prompt correctif echoue, on leve EventSearchError - jamais
    de liste vide silencieuse (voir ExhibitorFetchError, meme philosophie)."""

    async def fake_call_and_parse(client, config, prompt):
        return None, _fake_response("toujours pas du json")

    monkeypatch.setattr("orbit.tools.search_events._call_and_parse", fake_call_and_parse)
    monkeypatch.setattr("orbit.tools.search_events._get_client", lambda: object())

    with pytest.raises(EventSearchError):
        await search_events(make_input())


async def test_raises_when_no_events_found(monkeypatch):
    async def fake_call_and_parse(client, config, prompt):
        return [], _fake_response("[]", grounded_domains=[])

    monkeypatch.setattr("orbit.tools.search_events._call_and_parse", fake_call_and_parse)
    monkeypatch.setattr("orbit.tools.search_events._get_client", lambda: object())

    with pytest.raises(EventSearchError):
        await search_events(make_input())


async def test_raises_when_api_key_missing(monkeypatch):
    from orbit.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "")

    with pytest.raises(EventSearchError):
        await search_events(make_input())
