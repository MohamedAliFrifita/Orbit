"""
classify_exhibitor — Classifier tool reel (semaine 3).

DECISIONS D'AI ENGINEERING :

1. response_schema natif : pas de google_search -> pas d'incompatibilite
   (contrairement au Scout). Sortie JSON garantie conforme.

2. Batching par micro-lots (CLASSIFIER_BATCH_SIZE, defaut=3) :
   economise les appels API vs 1/exposant, qualite superieure vs tout-en-un.

3. Retry partiel sur lot : valider chaque item individuellement, relancer
   les echecs seuls plutot qu'en relancant tout le lot.

4. Temperature=0.35 : assez bas pour la coherence ICP, assez haut pour
   des inferences argumentees sur donnees manquantes.

5. Boucle de correction unique par exposant en echec (re-prompt avec
   message d'erreur Pydantic). ClassificationError si toujours invalide.

6. Retry/backoff sur 429 : 3 tentatives max, backoff 1s->2s->4s.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from google import genai
from google.genai import types
from pydantic import ValidationError

from orbit.config import settings
from orbit.prompts import load_prompt
from orbit.schemas.exhibitor import ClassificationOutput, ExhibitorInput
from orbit.schemas.run import ICPContext

MODEL_NAME = os.environ.get("ORBIT_CLASSIFIER_MODEL")
BATCH_SIZE = int(os.environ.get("CLASSIFIER_BATCH_SIZE", "3"))
_MAX_RETRIES = 3
_BACKOFF_BASE = 1.0  # secondes

_BATCH_RESPONSE_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "exhibitor_id":    {"type": "STRING"},
            "name":            {"type": "STRING"},
            "booth":           {"type": "STRING", "nullable": True},
            "category":        {
                "type": "STRING",
                "enum": ["client", "partner", "supplier", "competitor", "irrelevant"],
            },
            "potential_score": {"type": "NUMBER"},
            "rationale":       {"type": "STRING"},
            "confidence":      {"type": "STRING", "enum": ["low", "medium", "high"]},
            "sources_used":    {"type": "ARRAY", "items": {"type": "STRING"}},
        },
        "required": [
            "exhibitor_id", "name", "category",
            "potential_score", "rationale", "confidence",
        ],
    },
}


class ClassificationError(Exception):
    """
    Levee quand un exposant ne peut pas etre classifie apres correction.
    Ne stoppe pas le batch — l'appelant (classify_exhibitor_batch) log
    l'exposant en file de revue manuelle et continue avec les suivants.
    Meme pattern Option A que ExhibitorFetchError et EventSearchError.
    """
    pass


def _get_client() -> genai.Client:
    if not settings.gemini_api_key:
        raise ClassificationError(
            "GEMINI_API_KEY manquante dans .env — voir aistudio.google.com/apikey"
        )
    return genai.Client(api_key=settings.gemini_api_key)


def _build_config(system_prompt: str) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type="application/json",
        response_schema=_BATCH_RESPONSE_SCHEMA,
        temperature=0.35,
    )


def _build_batch_prompt(batch: list[ExhibitorInput], icp: ICPContext) -> str:
    exhibitors_json = json.dumps(
        [ex.model_dump() for ex in batch],
        ensure_ascii=False, indent=2
    )
    return (
        f"ICP:\n{icp.model_dump_json(indent=2)}\n\n"
        f"Exposants a classifier (liste de {len(batch)}) :\n{exhibitors_json}\n\n"
        "Retourne un tableau JSON avec exactement un objet de classification "
        "par exposant, dans le meme ordre que la liste fournie."
    )


def _build_single_correction_prompt(
    exhibitor: ExhibitorInput, icp: ICPContext, error_msg: str
) -> str:
    return (
        f"ICP:\n{icp.model_dump_json(indent=2)}\n\n"
        f"Exposant a classifier:\n{exhibitor.model_dump_json(indent=2)}\n\n"
        f"Ta reponse precedente etait invalide : {error_msg}\n"
        "Reponds UNIQUEMENT avec un objet JSON valide correspondant au schema demande "
        "(PAS un tableau, un seul objet)."
    )


async def _call_with_retry(
    client: genai.Client,
    config: types.GenerateContentConfig,
    prompt: str,
) -> str:
    """Appel Gemini avec retry/backoff sur 429 (RESOURCE_EXHAUSTED)."""
    for attempt in range(_MAX_RETRIES):
        try:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=MODEL_NAME,
                contents=prompt,
                config=config,
            )
            return response.text
        except Exception as exc:
            if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
                if attempt < _MAX_RETRIES - 1:
                    wait = _BACKOFF_BASE * (2 ** attempt)
                    await asyncio.sleep(wait)
                    continue
            raise ClassificationError(f"Erreur API Gemini: {exc}") from exc
    raise ClassificationError("Quota depasse — max tentatives atteint.")


def _validate_item(
    raw_item: dict[str, Any], fallback_id: str
) -> tuple[ClassificationOutput | None, str]:
    """
    Valide un item brut issu du lot. Retourne (output, '') ou (None, message_erreur).
    Reinjecte exhibitor_id si absent (le modele peut l'omettre meme avec response_schema).
    """
    try:
        if not raw_item.get("exhibitor_id"):
            raw_item["exhibitor_id"] = fallback_id
        output = ClassificationOutput.model_validate(raw_item)
        return output, ""
    except (ValidationError, ValueError) as exc:
        return None, str(exc)


async def _classify_single_with_correction(
    exhibitor: ExhibitorInput,
    icp: ICPContext,
    client: genai.Client,
    system_prompt: str,
) -> ClassificationOutput:
    """
    Relance un exposant individuel en echec avec un re-prompt correctif unique.
    Utilise uniquement pour les items qui ont echoue la validation dans leur lot.
    """
    single_schema = _BATCH_RESPONSE_SCHEMA["items"]
    config_single = types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type="application/json",
        response_schema=single_schema,
        temperature=0.35,
    )

    raw = await _call_with_retry(
        client, config_single,
        _build_batch_prompt([exhibitor], icp)
    )

    try:
        raw_item = json.loads(raw)
        if isinstance(raw_item, list) and len(raw_item) == 1:
            raw_item = raw_item[0]
        output, error_msg = _validate_item(raw_item, exhibitor.id)
    except (json.JSONDecodeError, TypeError) as exc:
        output, error_msg = None, str(exc)

    if output is not None:
        return output

    # Un seul re-prompt correctif
    correction_prompt = _build_single_correction_prompt(exhibitor, icp, error_msg)
    raw = await _call_with_retry(client, config_single, correction_prompt)

    try:
        raw_item = json.loads(raw)
        if isinstance(raw_item, list) and len(raw_item) == 1:
            raw_item = raw_item[0]
        output, error_msg = _validate_item(raw_item, exhibitor.id)
    except (json.JSONDecodeError, TypeError) as exc:
        output, error_msg = None, str(exc)

    if output is None:
        raise ClassificationError(
            f"Classification impossible pour '{exhibitor.name}' apres correction : {error_msg}"
        )
    return output


async def _process_batch(
    batch: list[ExhibitorInput],
    icp: ICPContext,
    client: genai.Client,
    config: types.GenerateContentConfig,
    system_prompt: str,
    manual_review_queue: list[str],
) -> list[ClassificationOutput]:
    """
    Traite un micro-lot d'exposants :
    1. Appel Gemini pour tout le lot
    2. Valide chaque item individuellement
    3. Relance en solo les items en echec (avec correction)
    4. Ajoute les echecs definitifs a manual_review_queue
    """
    results: list[ClassificationOutput] = []
    prompt = _build_batch_prompt(batch, icp)

    try:
        raw_text = await _call_with_retry(client, config, prompt)
        raw_list = json.loads(raw_text)
        if not isinstance(raw_list, list):
            raw_list = [raw_list]
    except (ClassificationError, json.JSONDecodeError, TypeError):
        raw_list = [None] * len(batch)

    for i, exhibitor in enumerate(batch):
        raw_item = raw_list[i] if i < len(raw_list) else None
        output = None

        if isinstance(raw_item, dict):
            output, _ = _validate_item(raw_item, exhibitor.id)

        if output is not None:
            results.append(output)
        else:
            try:
                output = await _classify_single_with_correction(
                    exhibitor, icp, client, system_prompt
                )
                results.append(output)
            except ClassificationError as exc:
                manual_review_queue.append(exhibitor.name)
                print(f"[REVUE MANUELLE] {exhibitor.name} — {exc}")

    return results


async def classify_exhibitor_batch(
    exhibitors: list[ExhibitorInput],
    icp: ICPContext,
    *,
    manual_review_queue: list[str] | None = None,
) -> list[ClassificationOutput]:
    """
    Classifie une liste d'exposants en micro-lots (BATCH_SIZE exposants par appel Gemini).

    Strategie de retry partielle : si des items d'un lot echouent la validation,
    ils sont relances individuellement — les items valides du lot ne sont pas
    perdus ni re-classifies.

    Les exposants en echec definitif sont ajoutes a manual_review_queue
    (si fournie) et exclus du resultat sans arreter le batch.
    """
    client = _get_client()
    system_prompt = load_prompt("classifier", version="v1")
    config = _build_config(system_prompt)
    review = manual_review_queue if manual_review_queue is not None else []

    results: list[ClassificationOutput] = []
    batches = [exhibitors[i:i + BATCH_SIZE] for i in range(0, len(exhibitors), BATCH_SIZE)]

    for batch in batches:
        batch_results = await _process_batch(
            batch, icp, client, config, system_prompt, review
        )
        results.extend(batch_results)

    return results