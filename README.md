# ORBIT

**Autonomous Multi-Agent System for B2B Trade Show Prospecting & Itinerary Optimization.**

ORBIT automates the discovery of high-impact industry trade shows, extracts and analyzes exhibitor directories, qualifies leads against an Ideal Customer Profile (ICP), and produces optimized visit schedules complete with custom sales pitch talking points and downloadable PDF dossiers.

---

## Architecture & Multi-Agent Pipeline

![ORBIT Architecture & Dataflow](docs/images/architecture_dataflow.jpg)

The pipeline is built on an **Orchestrator-Worker** pattern structured into 5 sequential stages. Every autonomous stage(1,3,4 and 5) is governed by a **3-Subphase Engine (Planning ➔ Working ➔ Judging)**:

```text
[B2B Mission] (Sector, Region, ICP Target Profile)
      │
      ▼
 1. SCOUT (Gemini 3.5 Flash Lite) ──► Web discovery of candidate trade shows
      │
      ▼
 2. HUMAN CHECKPOINT ───────────────► Target event selection on the Command Dashboard
      │
      ▼
 3. ANALYST (Playwright + Gemini) ──► Dynamic JavaScript rendering & exhibitor extraction
      │
      ▼
 4. CLASSIFIER (Groq LLaMA 3.3) ────► Batch qualification against ICP criteria
      │
      ▼
 5. PLANNER (Groq LLaMA 3.3) ───────► Schedule optimization, booth routing & sales talking points
      │
      ▼
   [DONE] ──────────────────────────► Comprehensive report & ReportLab PDF export
```

### Specialized LLM Providers & Roles

- **Groq (`openai/gpt-oss-120b`)**: **Planning Engine** dynamically generating the contextual worker prompt and strict evaluation criteria for each stage.
- **Google Gemini (`gemini-3.5-flash-lite`)**: **Search & Recognition Engine** powering the Scout (with web search grounding and resilient fallback) and Analyst fallback.
- **Groq (`llama-3.3-70b-versatile`)**: **High-Speed Inference Engine** for batch ICP qualification (Classifier) and schedule optimization (Planner).
- **Mistral (`codestral-2508`)**: **Independent Reference Judge** evaluating every worker output (`PASS`, `REFINE`, `REWORK`).

---

## Repository Structure

```text
orbit/
├── apps/
│   ├── api/             # FastAPI Backend (Orchestrator, Agents, JWT Auth, PDF Export)
│   └── web/             # Next.js 15 Frontend (Tactical Command Dashboard, Live SSE Stream)
├── docs/                # In-depth technical documentation
│   ├── architecture.md  # Deep dive into multi-agent architecture, feedback loops, Redis & memory
│   ├── testing_guide.md # Comprehensive test suite guide & terminal walk-throughs (pytest & curl)
│   └── images/          # Architecture diagrams & assets
├── docker-compose.yml   # Local infrastructure: PostgreSQL 16 & Redis 7
└── manual_test_e2e.py   # Standalone end-to-end integration test script
```

---

## Quickstart (3 Minutes)

### 1. Launch Infrastructure (PostgreSQL & Redis)

From the root of the `orbit/` repository:
```bash
docker compose up -d
```

---

### 2. Start the Backend (FastAPI)

In your first terminal:

```bash
cd apps/api

# Activate Python virtual environment
source .venv/Scripts/activate        # Windows (Git Bash)
# source .venv/bin/activate          # Linux / macOS

# Install dependencies & Playwright browser
pip install -e ".[dev]"
playwright install chromium

# Configure environment variables
cp .env.example .env

# Run database migrations
alembic upgrade head

# Start the server
uvicorn orbit.api.main:app --reload --port 8000
```

- **API Root**: http://localhost:8000
- **Interactive Swagger Docs**: http://localhost:8000/docs

> **API Keys (.env)**:
> Populate your credentials in `apps/api/.env`: `GEMINI_API_KEY`, `GROQ_API_KEY`, and `MISTRAL_API_KEY`.

---

### 3. Start the Frontend (Next.js)

In a second terminal:

```bash
cd apps/web
npm install
npm run dev
```

- **Mission Command Center**: http://localhost:3000

---

## Testing & Validation

The entire unit test suite runs deterministically offline without network dependencies:

```bash
cd apps/api
pytest -v
```

> **Test Suite**: 54/54 tests passing (Orchestrator, Mistral Judge, bcrypt Auth, PDF Export, Playwright Scraping).

---

## Detailed Documentation

- [**In-Depth Architecture & Feedback Loops**](file:///docs/architecture.md): 3-subphase details, memory model, Redis Pub/Sub, pause/resume mechanisms.
- [**Testing Guide & Terminal Walk-through**](file:///docs/testing_guide.md): Complete curl commands from user registration to PDF export.
