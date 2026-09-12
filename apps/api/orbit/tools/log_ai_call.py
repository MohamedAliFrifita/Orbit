"""
Décorateur @log_ai_call — enregistre chaque appel LLM dans ai_call_logs.

Usage :
    @log_ai_call(stage="scout", subphase="working", model="gemini-2.5-flash",
                 role="worker", prompt_version="grok_scout/v1")
    async def my_llm_call(run_id: str, ...) -> ...:
        ...
"""

from __future__ import annotations

import asyncio
import functools
import time
from collections.abc import Callable
from typing import Any

from orbit.db.base import async_session
from orbit.db.models import AICallLog


def log_ai_call(
    *,
    stage: str,
    subphase: str,
    model: str,
    role: str,
    prompt_version: str | None = None,
) -> Callable:
    """
    Décorateur factory. La fonction décorée DOIT accepter `run_id: str` comme
    premier argument positionnel ou keyword argument.
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extraire run_id depuis args ou kwargs
            run_id: str | None = kwargs.get("run_id") or (args[0] if args else None)
            start = time.monotonic()
            error_msg: str | None = None
            result: Any = None

            try:
                result = await fn(*args, **kwargs)
                return result
            except Exception as exc:
                error_msg = str(exc)
                raise
            finally:
                latency_ms = int((time.monotonic() - start) * 1000)
                # Log en tâche de fond pour ne pas bloquer le pipeline
                asyncio.create_task(
                    _persist_log(
                        run_id=str(run_id) if run_id else None,
                        stage=stage,
                        subphase=subphase,
                        model=model,
                        role=role,
                        prompt_version=prompt_version,
                        latency_ms=latency_ms,
                        error=error_msg,
                    )
                )

        return wrapper

    return decorator


async def _persist_log(
    *,
    run_id: str | None,
    stage: str,
    subphase: str,
    model: str,
    role: str,
    prompt_version: str | None,
    latency_ms: int,
    error: str | None,
) -> None:
    try:
        async with async_session() as session:
            log = AICallLog(
                run_id=run_id,
                stage=stage,
                subphase=subphase,
                model=model,
                role=role,
                prompt_version=prompt_version,
                latency_ms=latency_ms,
                error=error,
            )
            session.add(log)
            await session.commit()
    except Exception:
        pass  # Les logs ne doivent jamais faire planter le pipeline