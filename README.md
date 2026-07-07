# ORBIT — Commando IA Événementiel

Squelette de repo — Semaine 1 (voir `orbit-coding-guide.md`).

## Contenu de cette étape

- Structure du monorepo (`apps/api` backend Python/FastAPI, `apps/web` réservé pour le frontend Next.js — semaine 4+)
- Schéma de base de données (SQLAlchemy + Alembic)
- `RunState` (Pydantic) — le contrat de données de l'orchestrateur
- Orchestrateur avec les 5 stages (`scout`, `analyst`, `classifier`, `planner`, `done`), **chaque stage retourne des données mockées** pour l'instant — aucun appel LLM réel encore
- Tests de base validant que la state machine avance correctement

## Démarrage rapide

```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

docker compose up -d          # lance Postgres local
alembic upgrade head          # applique le schéma DB

uvicorn orbit.api.main:app --reload
```

Puis dans un autre terminal :
```bash
curl -X POST http://localhost:8000/runs \
  -H "Content-Type: application/json" \
  -d '{"sector": "industrial automation", "objectives": ["find_clients"], "region": "France"}'
```

## Prochaine étape (semaine 2)

Remplacer les mocks dans `orbit/agents/scout.py` et `orbit/agents/analyst.py` par de vrais appels (recherche d'événements, scraping de la liste d'exposants).
