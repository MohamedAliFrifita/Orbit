"""
classify_exhibitor_groq — version Groq (Llama 3.3 70B) du Classifier.

Reçoit un prompt_worker généré par GROK (contient déjà les instructions ICP).
Traite les exposants en micro-lots de 3 avec JSON mode.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from pydantic import ValidationError

from orbit.schemas.exhibitor import ClassificationOutput, ExhibitorInput
from orbit.tools.groq_client import GROQ_MODEL, get_groq_client

BATCH_SIZE = 3
_MAX_RETRIES = 2


async def classify_exhibitor_batch_groq(
    exhibitors: list[ExhibitorInput],
    prompt_worker: str,
) -> list[ClassificationOutput]:
    """Classifie les exposants en micro-lots via Groq Llama 3.3."""
    results: list[ClassificationOutput] = []
    batches = [exhibitors[i: i + BATCH_SIZE] for i in range(0, len(exhibitors), BATCH_SIZE)]

    for batch in batches:
        batch_results = await _classify_batch(batch, prompt_worker)
        results.extend(batch_results)
        await asyncio.sleep(0.2)  # rate-limit léger

    return results


async def _classify_batch(
    batch: list[ExhibitorInput],
    prompt_worker: str,
    attempt: int = 0,
) -> list[ClassificationOutput]:
    if attempt >= _MAX_RETRIES:
        return []

    batch_items = [e.model_dump() if hasattr(e, "model_dump") else e for e in batch]
    batch_json = json.dumps(batch_items, ensure_ascii=False, indent=2)

    schema_instruction = (
        "Pour chaque exposant, produis un objet JSON respectant STRICTEMENT cette structure :\n"
        "{\n"
        '  "exhibitor_id": "<id de l\'exposant>",\n'
        '  "name": "<nom de l\'exposant>",\n'
        '  "booth": "<stand ou null>",\n'
        '  "category": "client" | "partner" | "supplier" | "competitor" | "irrelevant",\n'
        '  "potential_score": <nombre flottant entre 0.0 et 1.0>,\n'
        '  "rationale": "<justification en 1-2 phrases>",\n'
        '  "confidence": "low" | "medium" | "high"\n'
        "}\n"
        "Retourne un objet JSON contenant la clé \"exhibitors\" avec le tableau des résultats : "
        '{"exhibitors": [...]}.'
    )

    client = get_groq_client()
    resp = await client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": prompt_worker},
            {
                "role": "user",
                "content": (
                    f"Classifie ces {len(batch)} exposants.\n\n"
                    f"{schema_instruction}\n\n"
                    f"Exposants à classifier :\n{batch_json}"
                ),
            },
        ],
        response_format={"type": "json_object"},
        temperature=0.35,
    )

    raw = resp.choices[0].message.content
    try:
        data: Any = json.loads(raw)

        items_list: list = []
        if isinstance(data, list):
            items_list = data
        elif isinstance(data, dict):
            for val in data.values():
                if isinstance(val, list):
                    items_list = val
                    break
            if not items_list and all(isinstance(v, dict) for v in data.values()):
                items_list = list(data.values())

        outputs = []
        for i, item in enumerate(items_list):
            if not isinstance(item, dict):
                continue
            # Normalisation tolérante des clés courantes
            normalized = {
                "exhibitor_id": str(item.get("exhibitor_id") or item.get("id") or batch_items[min(i, len(batch_items)-1)].get("id", f"ex_{i}")),
                "name": str(item.get("name") or batch_items[min(i, len(batch_items)-1)].get("name", "Inconnu")),
                "booth": item.get("booth"),
                "category": str(item.get("category", "irrelevant")).lower().strip(),
                "potential_score": float(item.get("potential_score") if item.get("potential_score") is not None else item.get("score", 0.5)),
                "rationale": str(item.get("rationale") or item.get("justification") or "Classifié par IA"),
                "confidence": str(item.get("confidence", "medium")).lower().strip(),
                "sources_used": item.get("sources_used", []),
            }
            # Sécurité sur l'enum category
            valid_categories = {"client", "partner", "supplier", "competitor", "irrelevant"}
            if normalized["category"] not in valid_categories:
                normalized["category"] = "irrelevant"
            # Sécurité sur l'enum confidence
            if normalized["confidence"] not in {"low", "medium", "high"}:
                normalized["confidence"] = "medium"
            # Sécurité sur les bornes du score
            normalized["potential_score"] = max(0.0, min(1.0, normalized["potential_score"]))

            try:
                outputs.append(ClassificationOutput(**normalized))
            except ValidationError as ve:
                print(f"[CLASSIFIER WARN] ValidationError sur item: {ve}")
                continue

        if outputs:
            return outputs
        raise ValueError("Aucun exposant valide extrait du JSON")
    except Exception as exc:
        print(f"[CLASSIFIER RETRY] Erreur batch (tentative {attempt+1}): {exc}")
        await asyncio.sleep(1.0 * (attempt + 1))
        return await _classify_batch(batch, prompt_worker, attempt + 1)