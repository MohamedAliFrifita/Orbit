"""
Tests de classify_exhibitor.py — TOUJOURS mockes, jamais de vrai appel a l'API Gemini.

Utilite (meme principe que Scout et Analyst, voir orbit-contexte-semaine2.md
§5 "strategie de test") : les appels reels sont reserves a
eval/run_classifier_eval.py, execute manuellement, pas dans la suite pytest.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from orbit.schemas.exhibitor import ExhibitorInput
from orbit.schemas.run import ICPContext, Objective
from orbit.tools.classify_exhibitor import ClassificationError, classify_exhibitor_batch

MOCK_ICP = ICPContext(
    target_client_profile="Fabricants de lignes de production",
    objectives=[Objective.FIND_CLIENTS],
)


def _exhibitor(id_, name, desc="Description test suffisamment longue pour eviter l'inference."):
    return ExhibitorInput(id=id_, name=name, raw_description=desc)


def _make_valid_item(ex_id, name, category="client", sources_used=None):
    return {
        "exhibitor_id": ex_id, "name": name,
        "category": category, "potential_score": 0.7,
        "rationale": "Test rationale suffisamment longue.", "confidence": "medium",
        "sources_used": sources_used if sources_used is not None else ["raw_description"],
    }


def _mock_response(payload) -> MagicMock:
    response = MagicMock()
    response.text = json.dumps(payload)
    return response


async def test_batch_all_valid_first_call():
    """Lot de 3 exposants, tout valide au premier appel -> 1 seul appel Gemini."""
    batch = [_exhibitor("ex_001", "A"), _exhibitor("ex_002", "B"), _exhibitor("ex_003", "C")]
    batch_response = _mock_response([
        _make_valid_item("ex_001", "A"),
        _make_valid_item("ex_002", "B"),
        _make_valid_item("ex_003", "C"),
    ])

    with patch("orbit.tools.classify_exhibitor._get_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.models.generate_content.return_value = batch_response

        results = await classify_exhibitor_batch(batch, MOCK_ICP)

    assert len(results) == 3
    assert mock_client.models.generate_content.call_count == 1


async def test_batch_partial_invalid_retries_individual():
    """Lot de 3, item 2 invalide (category manquante) -> items 1 et 3 conserves,
    item 2 relance individuellement -> resultat final correct."""
    batch = [
        _exhibitor("ex_001", "ABC Auto", "Convoyage agroalimentaire"),
        _exhibitor("ex_002", "???Corp", ""),
        _exhibitor("ex_003", "XYZ Tools", "Outillage industriel"),
    ]
    batch_response = _mock_response([
        _make_valid_item("ex_001", "ABC Auto"),
        {"exhibitor_id": "ex_002", "name": "???Corp"},  # invalide : category absente
        _make_valid_item("ex_003", "XYZ Tools"),
    ])
    individual_response = _mock_response(
        _make_valid_item("ex_002", "???Corp", category="irrelevant")
    )

    with patch("orbit.tools.classify_exhibitor._get_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.models.generate_content.side_effect = [batch_response, individual_response]

        results = await classify_exhibitor_batch(batch, MOCK_ICP)

    assert len(results) == 3
    assert results[0].exhibitor_id == "ex_001"
    assert results[1].exhibitor_id == "ex_002"
    assert results[1].category == "irrelevant"
    assert results[2].exhibitor_id == "ex_003"
    assert mock_client.models.generate_content.call_count == 2


async def test_batch_parse_failure_relaunches_all_individual():
    """Lot entier non parseable (JSON invalide) -> chaque exposant relance individuellement."""
    batch = [_exhibitor("ex_001", "A"), _exhibitor("ex_002", "B")]

    unparseable_response = MagicMock()
    unparseable_response.text = "ceci n'est pas du json valide {{{"

    individual_1 = _mock_response(_make_valid_item("ex_001", "A"))
    individual_2 = _mock_response(_make_valid_item("ex_002", "B"))

    with patch("orbit.tools.classify_exhibitor._get_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.models.generate_content.side_effect = [
            unparseable_response, individual_1, individual_2,
        ]

        results = await classify_exhibitor_batch(batch, MOCK_ICP)

    assert len(results) == 2
    assert mock_client.models.generate_content.call_count == 3  # 1 lot + 2 relances


async def test_individual_correction_on_invalid():
    """Relance individuelle : premier appel invalide -> re-prompt -> second appel valide."""
    batch = [_exhibitor("ex_001", "A")]

    batch_response = _mock_response([{"exhibitor_id": "ex_001", "name": "A"}])  # invalide
    first_individual = _mock_response({"exhibitor_id": "ex_001", "name": "A"})  # invalide aussi
    correction_response = _mock_response(_make_valid_item("ex_001", "A"))  # valide

    with patch("orbit.tools.classify_exhibitor._get_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.models.generate_content.side_effect = [
            batch_response, first_individual, correction_response,
        ]

        results = await classify_exhibitor_batch(batch, MOCK_ICP)

    assert len(results) == 1
    assert results[0].exhibitor_id == "ex_001"


async def test_individual_two_invalids_raises_error():
    """Deux appels invalides consecutifs (premier essai + correction) -> ClassificationError,
    l'exposant est mis en revue manuelle, pas de plantage global du batch."""
    batch = [_exhibitor("ex_001", "A")]
    review_queue: list[str] = []

    batch_response = _mock_response([{"exhibitor_id": "ex_001", "name": "A"}])  # invalide
    first_individual = _mock_response({"exhibitor_id": "ex_001", "name": "A"})  # invalide
    correction_response = _mock_response({"exhibitor_id": "ex_001", "name": "A"})  # toujours invalide

    with patch("orbit.tools.classify_exhibitor._get_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.models.generate_content.side_effect = [
            batch_response, first_individual, correction_response,
        ]

        results = await classify_exhibitor_batch(batch, MOCK_ICP, manual_review_queue=review_queue)

    assert len(results) == 0
    assert "A" in review_queue


async def test_429_triggers_backoff_and_retry(monkeypatch):
    """Premier appel 429 -> backoff -> second appel reussit -> resultat valide."""
    batch = [_exhibitor("ex_001", "A"), _exhibitor("ex_002", "B"), _exhibitor("ex_003", "C")]

    async def fake_sleep(seconds):
        pass  # ne pas vraiment attendre pendant les tests

    monkeypatch.setattr("orbit.tools.classify_exhibitor.asyncio.sleep", fake_sleep)

    ok_response = _mock_response([
        _make_valid_item("ex_001", "A"),
        _make_valid_item("ex_002", "B"),
        _make_valid_item("ex_003", "C"),
    ])

    with patch("orbit.tools.classify_exhibitor._get_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.models.generate_content.side_effect = [
            Exception("429 RESOURCE_EXHAUSTED"),
            ok_response,
        ]

        results = await classify_exhibitor_batch(batch, MOCK_ICP)

    assert len(results) == 3
    assert mock_client.models.generate_content.call_count == 2


async def test_429_exhausted_raises_error(monkeypatch):
    """3 x 429 consecutifs -> ClassificationError, exposants en revue manuelle."""
    batch = [_exhibitor("ex_001", "A")]
    review_queue: list[str] = []

    async def fake_sleep(seconds):
        pass

    monkeypatch.setattr("orbit.tools.classify_exhibitor.asyncio.sleep", fake_sleep)

    with patch("orbit.tools.classify_exhibitor._get_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED")

        results = await classify_exhibitor_batch(batch, MOCK_ICP, manual_review_queue=review_queue)

    assert len(results) == 0
    assert "A" in review_queue


async def test_batch_continues_after_one_failure():
    """Un exposant en ClassificationError definitive -> ajoute a manual_review_queue,
    le batch continue et retourne les autres resultats normalement."""
    batch = [
        _exhibitor("ex_001", "A"),
        _exhibitor("ex_002", "FailCorp"),
        _exhibitor("ex_003", "C"),
    ]
    review_queue: list[str] = []

    batch_response = _mock_response([
        _make_valid_item("ex_001", "A"),
        {"exhibitor_id": "ex_002", "name": "FailCorp"},  # invalide, va echouer definitivement
        _make_valid_item("ex_003", "C"),
    ])
    first_individual = _mock_response({"exhibitor_id": "ex_002", "name": "FailCorp"})  # invalide
    correction_response = _mock_response({"exhibitor_id": "ex_002", "name": "FailCorp"})  # invalide

    with patch("orbit.tools.classify_exhibitor._get_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.models.generate_content.side_effect = [
            batch_response, first_individual, correction_response,
        ]

        results = await classify_exhibitor_batch(batch, MOCK_ICP, manual_review_queue=review_queue)

    assert len(results) == 2  # ex_001 et ex_003 seulement
    assert "FailCorp" in review_queue


async def test_missing_api_key_raises_error(monkeypatch):
    """GEMINI_API_KEY absente -> ClassificationError avant tout appel reseau."""
    from orbit.config import settings

    monkeypatch.setattr(settings, "gemini_api_key", "")

    with pytest.raises(ClassificationError):
        await classify_exhibitor_batch([_exhibitor("ex_001", "A")], MOCK_ICP)


async def test_exhibitor_id_propagated():
    """exhibitor_id absent du JSON du modele -> reinjecte depuis ExhibitorInput.id."""
    batch = [_exhibitor("ex_001", "A")]
    item_without_id = _make_valid_item("ex_001", "A")
    del item_without_id["exhibitor_id"]
    batch_response = _mock_response([item_without_id])

    with patch("orbit.tools.classify_exhibitor._get_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.models.generate_content.return_value = batch_response

        results = await classify_exhibitor_batch(batch, MOCK_ICP)

    assert len(results) == 1
    assert results[0].exhibitor_id == "ex_001"


async def test_max_exhibitors_truncation(monkeypatch):
    """
    Le plafond MAX_EXHIBITORS est applique dans agents/classifier.py, pas dans
    classify_exhibitor_batch (voir orbit-semaine3-guide.md §6) - ce test verifie
    donc agents.classifier.run_batch, pas le tool directement.
    """
    from orbit.agents import classifier as classifier_agent

    monkeypatch.setattr(classifier_agent, "MAX_EXHIBITORS", 25)

    captured_batches: list[list[ExhibitorInput]] = []

    async def fake_classify_batch(exhibitors, icp, **kwargs):
        captured_batches.append(exhibitors)
        return []

    monkeypatch.setattr(classifier_agent, "classify_exhibitor_batch", fake_classify_batch)

    exhibitors_30 = [_exhibitor(f"ex_{i:03d}", f"Exhibitor {i}") for i in range(30)]
    await classifier_agent.run_batch(exhibitors_30, MOCK_ICP)

    assert len(captured_batches[0]) == 25


async def test_sources_used_model_inference():
    """Exposant avec raw_description vide -> sources_used peut contenir 'model_inference'
    (verifie que la valeur renvoyee par le modele est bien propagee sans alteration)."""
    batch = [_exhibitor("ex_001", "Siemens", desc="[extrait par LLM]")]
    batch_response = _mock_response([
        _make_valid_item("ex_001", "Siemens", category="competitor", sources_used=["model_inference"])
    ])

    with patch("orbit.tools.classify_exhibitor._get_client") as mock_client_fn:
        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        mock_client.models.generate_content.return_value = batch_response

        results = await classify_exhibitor_batch(batch, MOCK_ICP)

    assert len(results) == 1
    assert results[0].sources_used == ["model_inference"]