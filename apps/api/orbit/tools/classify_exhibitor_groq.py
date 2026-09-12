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

    batch_json = json.dumps(
        [e.model_dump() for e in batch], ensure_ascii=False, indent=2
    )

    client = get_groq_client()
    resp = await client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": prompt_worker},
            {
                "role": "user",
                "content": (
                    f"Classifie ces {len(batch)} exposants. "
                    f"Retourne un tableau JSON avec {len(batch)} objets.\n\n"
                    f"Exposants :\n{batch_json}"
                ),
            },
        ],
        response_format={"type": "json_object"},
        temperature=0.35,
    )

    raw = resp.choices[0].message.content
    try:
        data: Any = json.loads(raw)
        # Groq renvoie parfois {"items": [...]} ou {"results": [...]}
        if isinstance(data, dict):
            data = next(iter(data.values()))
        outputs = []
        for item in data:
            try:
                outputs.append(ClassificationOutput(**item))
            except ValidationError:
                continue
        return outputs
    except (json.JSONDecodeError, StopIteration):
        await asyncio.sleep(1.0 * (attempt + 1))
        return await _classify_batch(batch, prompt_worker, attempt + 1)