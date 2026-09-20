"""
Tests unitaires du module Judge Mistral.
"""

import json
from unittest.mock import AsyncMock, MagicMock
import pytest

from orbit.judge import run as judge_mod
from orbit.schemas.judge import JudgeInput, JudgeVerdict


@pytest.fixture
def sample_judge_input():
    return JudgeInput(
        stage="scout",
        icp_context=json.dumps({"target_client_profile": "CTO B2B"}),
        success_criteria={"min_candidates": 2},
        worker_output=json.dumps([{"name": "Salon IA", "dates": "2026-05"}]),
    )


async def test_judge_parses_pass_verdict(sample_judge_input, monkeypatch):
    fake_content = json.dumps({
        "verdict": "PASS",
        "score": 9.5,
        "reasoning": "Tous les critères sont amplement satisfaits.",
        "suggestions": None,
    })

    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content=fake_content))]

    mock_client = MagicMock()
    mock_client.chat.complete_async = AsyncMock(return_value=mock_resp)

    monkeypatch.setattr(judge_mod, "get_mistral_client", lambda: mock_client)

    verdict = await judge_mod.judge(sample_judge_input, attempt_number=1)

    assert isinstance(verdict, JudgeVerdict)
    assert verdict.verdict == "PASS"
    assert verdict.score == 9.5
    assert "satisfaits" in verdict.reasoning
    assert verdict.attempt_number == 1


async def test_judge_parses_refine_verdict_with_suggestions(sample_judge_input, monkeypatch):
    fake_content = json.dumps({
        "verdict": "REFINE",
        "score": 5.0,
        "reasoning": "Qualité moyenne, manque de pertinence ICP.",
        "suggestions": "Préciser les sous-secteurs pour filtrer les exposants.",
    })

    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content=fake_content))]

    mock_client = MagicMock()
    mock_client.chat.complete_async = AsyncMock(return_value=mock_resp)

    monkeypatch.setattr(judge_mod, "get_mistral_client", lambda: mock_client)

    verdict = await judge_mod.judge(sample_judge_input, attempt_number=2)

    assert verdict.verdict == "REFINE"
    assert verdict.score == 5.0
    assert verdict.suggestions is not None
    assert "filtrer" in verdict.suggestions
    assert verdict.attempt_number == 2


async def test_judge_parses_rework_verdict(sample_judge_input, monkeypatch):
    fake_content = json.dumps({
        "verdict": "REWORK",
        "score": 1.5,
        "reasoning": "Échec total d'extraction ou salon hors sujet.",
        "suggestions": "Revenir au stage précédent.",
    })

    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content=fake_content))]

    mock_client = MagicMock()
    mock_client.chat.complete_async = AsyncMock(return_value=mock_resp)

    monkeypatch.setattr(judge_mod, "get_mistral_client", lambda: mock_client)

    verdict = await judge_mod.judge(sample_judge_input, attempt_number=1)

    assert verdict.verdict == "REWORK"
    assert verdict.score == 1.5
