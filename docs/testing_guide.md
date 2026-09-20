# Testing & Verification Guide — ORBIT

This guide details all procedures for testing and verifying the ORBIT system, from automated unit test suites to full end-to-end mission walkthroughs via the terminal.

---

## 1. Automated Unit Test Suite (pytest)

The project includes a suite of **54 unit tests** covering the 3-subphase multi-agent architecture, authentication, judge evaluation, and external integrations.

### Run Full Test Suite

From the `apps/api` directory (with your virtual environment activated):

```bash
pytest -v
```

### Run Specific Test Modules

```bash
# Orchestrator tests (3 subphases, Judge verdicts, human checkpoints)
pytest tests/test_orchestrator.py -v

# Authentication tests (direct bcrypt, JWT token decoding, 72-byte truncation fix)
pytest tests/test_auth.py -v

# Mistral Judge tests (PASS, REFINE, REWORK parsing & scores)
pytest tests/test_judge.py -v

# PDF itinerary export tests (404, 409, binary %PDF response)
pytest tests/test_export_pdf.py -v

# Scraping & qualification tools tests
pytest tests/test_fetch_exhibitor_list.py -v
pytest tests/test_classify_exhibitor.py -v
```

---

## 2. Terminal-Based End-to-End Walkthrough (curl)

You can trigger, observe, and complete a full autonomous mission using standard command-line tools without opening a browser.

### Step 1: User Registration & Authentication

```bash
# Register account
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "agent@orbit.ai", "password": "SecurePassword123!"}'

# Login (retrieve JWT access token)
curl -X POST http://localhost:8000/auth/login \
  -F "username=agent@orbit.ai" \
  -F "password=SecurePassword123!"
```

Copy the returned `access_token` into an environment variable:
```bash
TOKEN="<your_jwt_access_token>"
```

---

### Step 2: Initialize a Mission (Scout Agent)

```bash
curl -X POST http://localhost:8000/runs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "sector": "Artificial Intelligence",
    "region": "Europe",
    "icp": {
      "target_client_profile": "CTOs & B2B Tech Decision Makers",
      "objectives": ["find_clients"]
    }
  }'
```

The response contains the generated `run_id` (e.g., `d3b12345-...`). Save it:
```bash
RUN_ID="<your_run_id>"
```

---

### Step 3: Stream Real-Time Pipeline Events (SSE)

In a separate terminal window, monitor live execution events as they are emitted:

```bash
curl -N http://localhost:8000/runs/$RUN_ID/stream
```

You will observe the live event stream:
- Subphase transitions (`planning`, `working`, `judging`)
- Dynamic success criteria and Mistral Judge verdicts
- Completion of the Scout stage and transition to `awaiting_selection`

---

### Step 4: Select Target Trade Show (Human Checkpoint)

Inspect the current run state to view the candidate events discovered by the Scout:

```bash
curl -X GET http://localhost:8000/runs/$RUN_ID \
  -H "Authorization: Bearer $TOKEN"
```

Select a candidate event to trigger the remaining autonomous stages (Analyst, Classifier, Planner):

```bash
curl -X POST http://localhost:8000/runs/$RUN_ID/select-event \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "AI & Big Data Expo Europe",
    "dates": "2026-09-23/24",
    "location": "Amsterdam, Netherlands",
    "exhibitor_count": 250,
    "source_url": "https://www.ai-expo.net/europe/"
  }'
```

The SSE stream will resume in real time:
1. Exhibitor extraction (Analyst)
2. Lead qualification against ICP criteria (Classifier)
3. Visit schedule & talking point generation (Planner)
4. Final `run_done` event

---

### Step 5: Download PDF Prospecting Dossier

Once the mission reaches the `DONE` stage:

```bash
curl -X GET http://localhost:8000/runs/$RUN_ID/export/pdf \
  -H "Authorization: Bearer $TOKEN" \
  --output mission_itinerary.pdf
```

The compiled `mission_itinerary.pdf` will contain the full visiting schedule, allocated time slots, booth locations, and tailor-made sales talking points.

---

## 3. Mission Lifecycle Control (Pause / Resume)

You can pause and resume the autonomous pipeline execution at any time:

```bash
# Pause active mission
curl -X POST http://localhost:8000/runs/$RUN_ID/pause \
  -H "Authorization: Bearer $TOKEN"

# Resume mission execution
curl -X POST http://localhost:8000/runs/$RUN_ID/resume \
  -H "Authorization: Bearer $TOKEN"
```
