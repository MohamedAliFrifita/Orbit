# ORBIT

Système multi-agents pour la préparation et l'optimisation de prospection lors de salons professionnels B2B.

Le projet automatise la détection des événements pertinents, l'extraction de la liste des exposants et leur qualification selon un profil client cible (ICP).

---

## Architecture & Fonctionnement

Le pipeline suit un pattern **Orchestrator-Worker** découpé en 5 étapes successives :

1. **Scout** : Recherche et sélectionne les salons candidats selon le secteur et la région demandés.
2. **Awaiting Selection** : Étape humaine de validation du salon cible.
3. **Analyst** : Extraction et scraping de la liste des exposants du salon sélectionné via Playwright.
4. **Classifier** : Analyse et notation de chaque exposant par LLM (Gemini) selon l'ICP client.
5. **Planner** : Génération d'un planning de visite optimisé et fiches de prospection.

### Structure du dépôt

```text
orbit/
├── apps/
│   ├── api/          # Backend Python (FastAPI, SQLAlchemy, Alembic, Playwright, Gemini)
│   └── web/          # Frontend Next.js (React 19, TypeScript, Tailwind CSS)
├── docker-compose.yml # PostgreSQL 16 & Redis 7
└── manual_test_e2e.py # Script de validation bout en bout
```

---

## Démarrage et exécution locale

Deux terminaux sont nécessaires pour exécuter simultanément l'API et l'interface web.

### Terminal 1 : Backend

Se placer à la racine du dépôt `orbit/` :

```bash
# 1. Démarrer PostgreSQL et Redis
docker compose up -d

# 2. Entrer dans l'API
cd apps/api

# 3. Activer l'environnement virtuel Python
source .venv/Scripts/activate       # Windows (Git Bash)
# source .venv/bin/activate         # Linux / macOS

# 4. Installer les dépendances et le navigateur Playwright
pip install -e ".[dev]"
playwright install chromium

# 5. Configurer l'environnement
cp .env.example .env

# 6. Appliquer les migrations de base de données
alembic upgrade head

# 7. Lancer le serveur FastAPI
uvicorn orbit.api.main:app --reload --port 8000
```

- **API** : http://localhost:8000
- **Documentation Swagger** : http://localhost:8000/docs

#### Configuration requise (.env)

Dans `apps/api/.env`, renseignez votre clé Gemini :
```env
GEMINI_API_KEY=AIzaSy...
```

*Note sur le modèle Gemini :*  
Le backend utilise `gemini-2.5-flash` par défaut. Si le modèle devient obsolète ou indisponible, vous pouvez le modifier sans toucher au code en ajoutant ces variables dans `.env` :
```env
ORBIT_SCOUT_MODEL=nom-du-modele
ORBIT_CLASSIFIER_MODEL=nom-du-modele
```

---

### Terminal 2 : Frontend

Dans un second terminal, depuis la racine `orbit/` :

```bash
cd apps/web
npm install
npm run dev
```

- **Application web** : http://localhost:3000

---

## Tests

### Tests unitaires et d'intégration
Depuis `apps/api` (environnement virtuel actif) :
```bash
pytest -v
```

### Test de bout en bout (E2E)
Depuis la racine `orbit/` :
```bash
python manual_test_e2e.py
```
