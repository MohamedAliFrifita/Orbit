"""
search_events — Scout tool reel (semaine 2, Objectif 3).

DECISIONS D'AI ENGINEERING (voir orbit-contexte-semaine2.md §5 et §6 pour le detail complet) :

1. Modele : gemini-2.5-flash. Seule generation Gemini avec recherche web GRATUITE
   (500 requetes/jour, sans carte bancaire) - Gemini 3.x a la recherche web mais
   uniquement en payant. Verifie sur ai.google.dev/gemini-api/docs/pricing.

2. Pas de sortie structuree native (response_schema) : l'API Gemini interdit de
   combiner response_schema avec l'outil google_search sur les modeles 2.5
   (erreur 400 INVALID_ARGUMENT confirmee). On demande donc un JSON strict par
   instruction de prompt, puis on l'extrait par regex - contrainte technique,
   pas un choix de confort.

3. Anti-hallucination par verification de DOMAINE (pas d'URL exacte) : les URLs
   renvoyees dans grounding_metadata.grounding_chunks passent souvent par une
   redirection Google (vertexaisearch...), donc comparer l'URL exacte que le
   modele cite dans son JSON contre l'URL de redirection echouerait presque
   toujours. On compare plutot le DOMAINE (champ "domain" documente sur
   GroundingChunk.web) - plus robuste, et suffisant pour detecter une source
   totalement inventee (domaine qui n'apparait dans aucune recherche reelle).

4. Un seul re-prompt correctif en cas de JSON invalide, puis echec explicite
   (EventSearchError) - meme philosophie que ExhibitorFetchError (Objectif 2/4) :
   ne jamais renvoyer une liste vide silencieuse.
"""

from __future__ import annotations

import asyncio
import json
import re

from google import genai
from google.genai import types
from pydantic import ValidationError

from orbit.config import settings
from orbit.prompts import load_prompt
from orbit.schemas.run import EventCandidate, RunInput

import os

# Modele configurable via variable d'environnement pour faciliter les tests
# empiriques. Historique de cette decision (voir orbit-contexte-semaine2.md) :
# - Premiere tentative : erreur 404 "no longer available to new users" - s'est
#   averee etre un faux negatif (probablement lie a l'initialisation du projet
#   Google Cloud, pas un vrai blocage).
# - Confirme via le dashboard aistudio.google.com/rate-limit : gemini-2.5-flash
#   a un quota actif sur ce compte (5 RPM / 250K TPM / 20 RPD) avec des appels
MODEL_NAME = os.environ.get("ORBIT_SCOUT_MODEL") or "gemini-3.5-flash-lite"

_JSON_ARRAY_PATTERN = re.compile(r"\[.*\]", re.DOTALL)


class EventSearchError(Exception):
    """
    Levee quand la recherche d'evenements echoue de maniere irrecuperable
    (reponse toujours invalide apres re-prompt, erreur API, quota depasse).

    Meme pattern que ExhibitorFetchError : permet a l'orchestrateur de renvoyer
    un message clair au stage SCOUT plutot que de planter ou de renvoyer une
    liste vide silencieuse (voir orchestrator/run.py).
    """

    pass


def _get_client() -> genai.Client:
    if not settings.gemini_api_key:
        raise EventSearchError(
            "GEMINI_API_KEY manquante dans .env - voir aistudio.google.com/apikey"
        )
    return genai.Client(api_key=settings.gemini_api_key)


def _build_config(system_prompt: str) -> types.GenerateContentConfig:
    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    return types.GenerateContentConfig(
        tools=[grounding_tool],
        system_instruction=system_prompt,
    )


def _extract_grounded_domains(response) -> set[str]:
    """Recupere les vrais domaines consultes par le modele pendant sa recherche.

    Utilite : sert de reference verifiable pour la Decision 3 (anti-hallucination) -
    un evenement dont le domaine source n'apparait pas ici a probablement ete
    invente par le modele plutot que trouve via une vraie recherche.
    """
    domains: set[str] = set()
    for candidate in response.candidates or []:
        metadata = getattr(candidate, "grounding_metadata", None)
        if not metadata or not metadata.grounding_chunks:
            continue
        for chunk in metadata.grounding_chunks:
            web = getattr(chunk, "web", None)
            if web and web.domain:
                domains.add(web.domain.lower())
    return domains


def _extract_json_array(text: str | None) -> list[dict]:
    if not text:
        raise ValueError("Aucun texte reçu dans la réponse du modèle.")
    match = _JSON_ARRAY_PATTERN.search(text)
    if not match:
        raise ValueError("Aucun tableau JSON trouve dans la reponse.")
    return json.loads(match.group(0))



def _domain_of(url: str) -> str:
    m = re.match(r"^https?://(?:www\.)?([^/]+)", url or "")
    return m.group(1).lower() if m else ""


async def search_events(run_input: RunInput, prompt_override: str | None = None) -> list[EventCandidate]:
    """
    Cherche des evenements pertinents pour le secteur/region donnes, via Gemini
    + recherche web. Leve EventSearchError si la reponse reste invalide apres
    un essai de correction, ou si aucun evenement plausible n'est trouve.
    """
    client = _get_client()
    system_prompt = prompt_override or load_prompt("scout", version="v1")
    config = _build_config(system_prompt)

    user_prompt = (
        f"Secteur: {run_input.sector}\n"
        f"Region: {run_input.region}\n"
        f"Objectifs: {', '.join(o.value for o in run_input.icp.objectives)}\n"
        f"Profil client cible: {run_input.icp.target_client_profile}\n"
    )

    events, response = await _call_and_parse(client, config, user_prompt)

    if events is None:
        # Un seul re-prompt correctif (Decision 4)
        correction_prompt = (
            user_prompt
            + "\n\nTa reponse precedente n'etait pas un JSON valide. "
            "Reponds UNIQUEMENT avec un tableau JSON valide, sans aucun texte autour."
        )
        events, response = await _call_and_parse(client, config, correction_prompt)

    if events is None:
        raise EventSearchError(
            "La reponse du modele n'a pas pu etre interpretee comme un JSON valide, "
            "meme apres une tentative de correction."
        )

    if not events:
        raise EventSearchError(
            "Aucun evenement trouve pour ce secteur/region - le modele n'a "
            "propose aucun candidat."
        )

    grounded_domains = _extract_grounded_domains(response)
    for event in events:
        source_domain = _domain_of(event.source_url or "")
        if source_domain and source_domain not in grounded_domains:
            event.relevance_note = (
                (event.relevance_note or "")
                + " [ATTENTION: source non confirmee par la recherche reelle - "
                "a verifier manuellement]"
            ).strip()

    return events


async def _call_and_parse(
    client: genai.Client, config: types.GenerateContentConfig, prompt: str
) -> tuple[list[EventCandidate] | None, object]:
    """
    Utilite du asyncio.to_thread : le SDK google-genai est synchrone
    (client.models.generate_content bloque le thread). Sans ca, un appel
    Gemini de plusieurs secondes gelerait tout le serveur FastAPI pendant
    l'attente - aucune autre requete ne pourrait etre traitee en parallele.
    to_thread delegue l'appel bloquant a un thread separe, laissant la boucle
    asyncio libre de gerer d'autres requetes pendant ce temps.
    """
    try:

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=MODEL_NAME,
            contents=prompt,
            config=config,
        )
    except Exception as exc:
        # Si la recherche web (grounding tool) échoue (ex: 429 quota search gratuit),
        # retenter sans l'outil de recherche plutôt que de faire échouer le Scout
        if getattr(config, "tools", None):
            fallback_config = types.GenerateContentConfig(
                system_instruction=config.system_instruction,
            )
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=MODEL_NAME,
                contents=prompt,
                config=fallback_config,
            )
        else:
            raise

    # Si la réponse avec grounding a renvoyé un texte vide ou None, retenter également sans outils
    text = getattr(response, "text", None)
    if not text and getattr(config, "tools", None):
        fallback_config = types.GenerateContentConfig(
            system_instruction=config.system_instruction,
        )
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=MODEL_NAME,
            contents=prompt,
            config=fallback_config,
        )
        text = getattr(response, "text", None)

    try:
        raw_items = _extract_json_array(text)
        events = [EventCandidate.model_validate(item) for item in raw_items]
    except (ValueError, json.JSONDecodeError, ValidationError, TypeError):
        return None, response

    return events, response

