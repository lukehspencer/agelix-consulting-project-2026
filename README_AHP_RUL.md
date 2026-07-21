# Assets Maestro -- Predictive Asset Management Dashboard

> An asset risk scoring and remaining useful life (RUL) prediction dashboard for industrial equipment, powered by AHP-based risk analysis, XGBoost ML, and RAG-augmented AI explanations via the Anthropic API.

---

## Overview

The dashboard scores industrial assets using the Analytic Hierarchy Process (AHP) -- a structured method for multi-criteria risk ranking -- and predicts remaining useful life using a trained XGBoost model. Risk scores and RUL predictions update dynamically as the user adjusts the AHP pairwise comparison matrix. A GenAI explanation layer (Claude, via the Anthropic API) generates plain-English maintenance recommendations for each asset on demand, enriched by a RAG (Retrieval-Augmented Generation) knowledge pipeline that retrieves relevant engineering standards, past failure cases, and prior asset configurations.

The backend supports two modes. A default fleet mode loads a pre-configured fleet of 5 KSB Calio 30-40 centrifugal pump assets from operational telemetry provided by the client, exposed via the `/ahp` and `/rul` API routes. **The dashboard UI currently renders only the second mode, uploaded asset mode** -- the default fleet endpoints remain fully functional for direct API use, but there is no toggle or view for them in the dashboard itself.

In uploaded asset mode, the user uploads an Excel file with operational telemetry and a failure/maintenance log, Claude analyzes the data and infers appropriate AHP criteria, scoring thresholds, and a recommended preventive-maintenance interval for that asset type, and the dashboard runs the full risk and RUL pipeline on the uploaded data. Claude's inferred criteria are always a draft: a human reviews and approves (or edits) them in the dashboard before they can drive any scoring or prediction, and every approval is recorded in an audit trail showing exactly what changed from Claude's suggestion. Approval isn't a one-time checkpoint -- once criteria have been approved at least once, the user can freely re-run the risk/RUL analysis with different AHP weights with no extra approval step, and can reopen the review screen at any time to edit thresholds or the PM interval, which requires re-approving before the next run.

The RUL model for uploaded assets also looks beyond single-sensor thresholds: it tracks trend direction and cross-sensor correlation over a rolling window, and separately runs deterministic threshold-breach detection on every scoring pass, with Claude only invoked on demand to explain a breach that has already been found. It also produces simplified MTBF (mean time between failures) and MTBM (recommended maintenance interval) estimates, plus a basic replace-vs-maintain economic comparison -- all deterministic approximations, not full statistical reliability models.

Built as an internship project for Agelix Consulting to extend their asset lifecycle management platform, Assets Maestro. The default asset class is the KSB Calio 30-40 glandless circulator pump.

---

## Tech Stack

| Layer | Technology |
|---|---|
| AHP Engine | Python, NumPy |
| Telemetry Processing | Python, pandas, openpyxl |
| ML Model | XGBoost, scikit-learn, joblib |
| GenAI Layer | Anthropic API (claude-sonnet-4-6) |
| Schema Inference | Anthropic API (claude-sonnet-4-6) |
| RAG Pipeline | ChromaDB (onnxruntime default embeddings), LangChain |
| API Layer | FastAPI, Uvicorn |
| Frontend | React, Recharts |
| Testing | pytest |

---

## Prerequisites

1. Python 3.11 or higher
2. Node.js (LTS) and npm
3. An Anthropic API key
4. On macOS: `brew install libomp` (required for XGBoost)

---

## Setup

### Step 1 -- Clone the repository

```bash
git clone <repository-url>
cd agelix-consulting-project-2026
```

### Step 2 -- Install Python dependencies

```bash
pip install -r requirements.txt
```

### Step 3 -- Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and set:
```
ANTHROPIC_API_KEY=your_key_here
API_BASE_URL=http://localhost:8000
```

### Step 4 -- Generate the default fleet data

```bash
python data/generate_maintenance_log.py
```

This generates the KSB telemetry file and maintenance log in `data/raw/`. Required before starting the backend.

### Step 5 -- Train the default fleet RUL model

```bash
python -m rul.train
```

Outputs `rul/model.pkl`. Required before starting the backend.

### Step 6 -- Build the RAG knowledge base (optional)

```bash
python -m rag.ingest
```

Creates the ChromaDB vector store at `rag/chroma_db/`. This step is optional -- the system works without it, but schema inference and RUL explanations improve when domain knowledge is available. To populate it, place PDF manuals in `docs/manuals/` and/or failure case markdown files in `docs/failure_cases/` before running. CriteriaConfigs from previous uploads are stored automatically in `rag/stored_configs/`. Use `--rebuild` to force a full rebuild.

### Step 7 -- Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

---

## Running the Application

### Backend

```bash
uvicorn main:app --reload
```

Runs at `http://localhost:8000`. API docs available at `http://localhost:8000/docs`.

### Frontend

```bash
cd frontend
npm run dev
```

To run node.js on Windows:
& "C:\Program Files\nodejs\npm.cmd"
To set npm in env: $env:PATH += ";C\Program Files\nodejs\"

Runs at `http://localhost:5173`. Vite proxies `/ahp/*`, `/rul/*`, `/upload/*`, and `/rag/*` to the backend automatically.

---

## How It Works

### AHP Risk Scoring

The user fills a pairwise comparison matrix in the dashboard, following Saaty's 1-9 scale. The engine derives a weight vector from the matrix and validates consistency using the Consistency Ratio (CR). A CR above 0.10 indicates an inconsistent matrix -- the dashboard surfaces a warning and blocks RUL predictions until the matrix is corrected.

In default fleet mode the matrix is always 5x5 (five fixed criteria); in upload mode -- the dashboard's only rendered view -- the matrix is NxN where N is the number of criteria inferred by Claude for the uploaded asset type (3--7). Each asset is scored on a 1-10 internal scale, converted to the 1-9 Saaty scale. The overall risk factor is the dot product of the weight vector and score vector, producing a score from 1 to 9 per asset. Higher scores indicate higher risk.

In the default fleet mode, three criteria are derived automatically from sensor telemetry and two are manual inputs with defaults based on the KSB Calio operational context. In upload mode, no criteria are hardcoded -- the Anthropic API analyzes the uploaded data, infers appropriate criteria names and scoring thresholds for the detected asset type, and stores them in a CriteriaConfig that drives the entire scoring pipeline.

### RUL Prediction

The XGBoost model is trained on daily telemetry rows from the KSB dataset (1,095 days x 5 pumps). Each training sample is a 24-feature vector combining raw asset variables, the full AHP weight vector, the AHP weighted score vector, the overall risk factor, and 5 rolling telemetry features. The training target is `True_RUL_Days / 365` (years).

At inference time, the raw model prediction is adjusted by the AHP risk factor: `RUL_adjusted = RUL_raw x (1 - (risk_factor - 1) / 8)`. This means a higher risk score directly reduces predicted remaining life. RUL is displayed in **days** in the dashboard (`rul_years * 365`); the backend always returns years. Color thresholds: green &gt; 365 days, yellow 180--365 days, red &lt; 180 days.

### Dynamic Asset Upload

When a user uploads an Excel file (two sheets: Operational Telemetry and Failure & Maintenance Logs), the pipeline:

1. Validates the file and detects column roles by keyword heuristics -- no specific column names are required.
2. Queries the RAG knowledge base for relevant engineering standards, similar past CriteriaConfigs, and known failure cases.
3. Calls the Anthropic API to infer 3-7 AHP criteria appropriate for the detected asset type, with scoring thresholds calibrated to the actual data ranges and a recommended PM (preventive maintenance) interval inferred from the gaps between logged maintenance events (or from domain knowledge if fewer than 2 exist), enriched by retrieved domain knowledge. This is a **draft** -- it is stored provisionally but not yet trusted.
4. Trains a fresh XGBoost model on the uploaded dataset (the model bundle is saved as unapproved).
5. **The user reviews and approves the criteria** in the dashboard: criterion names, manual-input default scores, threshold/penalty values, and the recommended PM interval are all editable (sensor column assignments are not, since changing them would invalidate the trained model). Approving locks the bundle and re-stores the SME-approved CriteriaConfig in the knowledge base as a new, versioned file for future retrieval -- Claude's original draft is never overwritten, and every approval (with a before/after diff of exactly what the SME changed) is appended to an audit log. Approval isn't one-and-done: the user can come back and click "Edit Criteria" at any time to change thresholds or the PM interval and re-approve, or just re-run the analysis with new AHP weights without touching criteria at all.
6. Auto-generates a failure case document recording the asset type, sensors, failure modes, criteria, and training metrics.
7. Scores each asset, runs deterministic threshold-breach detection, computes MTBF/MTBM/replace-vs-maintain estimates using the approved PM interval, and predicts RUL using the user's AHP matrix. The first prediction run requires the criteria to have been approved; subsequent weight-only re-runs don't require re-approving.

All column name references flow through a central resolver module (`data/column_resolver.py`) -- no part of the pipeline hardcodes column names.

### Approval Audit Trail

Every criteria approval is logged to `docs/audit_log.jsonl` (`rag/audit_log.py`) -- an append-only, one-line-per-approval record of the file uploaded, the asset type, the exact CriteriaConfig filename that was saved, a count of how many fields the SME changed, and a full field-by-field diff (criterion, field, Claude's original value, the approved value). This never blocks an approval -- if logging fails for any reason it's silently skipped. The dashboard's Knowledge Base panel has an "Approval Audit Log" section that lists every approval (timestamp, asset type, file, changes made) and lets you expand any row to see the full diff.

### Versioned CriteriaConfig Storage

Every successful schema inference and every approval saves a **new** CriteriaConfig file -- `{asset_type}_{timestamp}.json` -- rather than overwriting the previous one, so the full history of inferred and approved configs per asset type is preserved on disk and searchable in the RAG knowledge base. The Knowledge Base panel's document listing shows every version, sorted newest-first, and separately surfaces just the latest config for each distinct asset type.

### Multi-Sensor Correlation and Threshold Breach Detection

For uploaded assets, the RUL feature set goes beyond single-sensor rolling statistics:

- **Trend features** -- a 14-row rolling slope per sensor, showing whether a reading is degrading, stable, or improving.
- **Cross-sensor features** -- for every pair of sensors: their mean-value interaction, whether their trends are aligned (both degrading together), and their rolling correlation coefficient. A composite stress index summarizes how many sensors are degrading in tandem (0 = none, 1 = all of them).
- **Threshold breach detection** -- a pure deterministic check (`ahp/threshold_breach_detector.py`, no API call) that flags any sensor whose value has crossed from a "safe" scoring band into a risky one, with a severity of low/medium/high based on how far past the safe boundary it is.

Both feed the RUL model as additional features and surface in the dashboard: a Multi-Sensor Analysis panel in the asset explanation popup, and a per-asset breach status column with an on-demand "Breach Alerts" button. Claude is only called to generate breach alert text for medium/high severity breaches, and only when the user asks for it -- never automatically during scoring.

### Maintenance Planning (MTBF, MTBM, Replace vs. Maintain)

For uploaded assets, every scoring pass also computes three simplified, deterministic approximations (no API calls, and explicitly not full Weibull statistical reliability models):

- **Estimated MTBF** (mean time between failures) -- derived from the asset's observed failure count and total runtime, with a confidence label (low/medium/high) based on how many failures were actually observed. With zero recorded failures, MTBF is deliberately shown as unavailable (`N/A*`, with a footnote) rather than a fabricated estimate -- there's no data to estimate from.
- **Recommended maintenance interval (MTBM)** -- a risk-adjusted fraction of the estimated MTBF, compared against the asset's **approved PM interval** (the SME-approved value if one was set during criteria review, else Claude's recommendation from schema inference, else a 90-day fallback) to recommend shortening, extending, or maintaining it, plus a suggested next maintenance date. When MTBF is unavailable, this recommends maintaining the current interval rather than showing nothing -- the safer default when there's no failure history to optimize against.
- **Replace vs. maintain** -- a basic amortized-cost comparison between ongoing maintenance spend and an estimated (or uploaded) replacement cost.

These appear in the dashboard as a "Maintenance Planning" section of the asset explanation popup (three cards -- MTBF, PM interval with its source and confidence, economic decision -- plus a highlighted next-maintenance date) and as two extra columns, "Est. MTBF" and "PM Interval", in the risk ranking table.

### Health Status and Urgency

Each uploaded asset gets a Health Status -- Critical, At Risk, Monitor, or Healthy -- computed from RUL first and risk factor second (an asset with very little remaining life reads Critical regardless of its risk score; risk factor only decides the status once RUL itself looks healthy). This single function drives everything urgency-related in the dashboard so nothing can disagree with anything else: the Health Status column and colored badge, the risk-ranking sort order (most urgent first, then soonest RUL within a tier), the summary counts banner, and the "assets require attention" banner at the top of the table (red for any Critical assets, orange for At Risk when there's no Critical). Risk Factor and RUL color pills, the breach status badge, and the MTBM shorten/extend/maintain indicator all share the same red/orange/yellow/green/grey palette for visual consistency.

### GenAI Explanations

On demand, the dashboard calls the Anthropic API to generate a 3-4 sentence plain-English explanation for each asset's RUL prediction. The explanation names the biggest AHP risk drivers given the current weights, highlights the key telemetry signals, and recommends a specific maintenance action. For uploaded assets, the explanation adapts to the inferred asset type and failure modes, and is enriched with retrieved failure precedents and maintenance guidance from the RAG knowledge base when available.

### RAG Knowledge Pipeline

The RAG system enriches Claude's prompts with retrieved domain knowledge. It is entirely optional -- when the knowledge base is missing or empty, the system behaves identically to before.

Three document types are ingested into a ChromaDB vector store using ChromaDB's built-in `DefaultEmbeddingFunction` (onnxruntime-based, ~50 MB). An earlier version used SentenceTransformer (`all-MiniLM-L6-v2`, PyTorch, ~3 GB) -- that has been replaced to keep the Docker image size reasonable; don't reintroduce `sentence-transformers`.

- **PDF manuals** (`docs/manuals/`) -- engineering standards and operating limits, chunked at 500 characters.
- **Failure case markdown** (`docs/failure_cases/`) -- auto-generated after each successful upload training run (asset type, sensors, failure modes, criteria, training RMSE), chunked at 300 characters. Manual failure case files can also be added.
- **CriteriaConfigs** (`rag/stored_configs/`) -- saved as versioned JSON (one new file per schema inference and per approval -- never overwritten), indexed as whole documents.

The retriever makes targeted queries per use case:
- **Schema inference**: retrieves engineering standards, similar past configs, and failure cases, injected as a RETRIEVED DOMAIN KNOWLEDGE block in the inference prompt.
- **RUL explanation**: retrieves failure precedents and maintenance guidance, injected as a RETRIEVED MAINTENANCE KNOWLEDGE block in the explainer prompt with an instruction to cite the most relevant precedent.

The knowledge base grows automatically as assets are uploaded -- each upload stores its CriteriaConfig and generates a failure case document. To bootstrap with existing domain knowledge, place PDFs and markdown files in the appropriate directories and run `python -m rag.ingest`.

OEM PDF manuals can also be uploaded directly from the dashboard UI. In upload mode, a collapsible **RAG Knowledge Base** panel appears below the Upload panel. It shows all three document categories (manuals, failure cases, criteria configs), allows drag-and-drop or click-to-browse PDF upload, and provides per-manual delete buttons. Uploaded manuals are immediately ingested into the vector store.

---

## API Reference

The FastAPI backend exposes three routers.

### `/ahp` -- AHP Engine

| Method | Route | Description |
|---|---|---|
| POST | `/ahp/calculate-weights` | NxN matrix (3-7 criteria) -> weights, CR, valid flag |
| POST | `/ahp/score-asset` | Asset variables -> C1-C5 scores |
| POST | `/ahp/risk-factor` | Weights + scores -> risk factor |
| GET | `/ahp/assets` | All default fleet assets ranked by risk score |

GET `/ahp/assets` accepts query params: `weights` (repeated float), `c1_score` (int, default 7), `c4_score` (int, default 6).

### `/rul` -- RUL Prediction (Default Fleet)

| Method | Route | Description |
|---|---|---|
| POST | `/rul/predict` | Asset + AHP features -> adjusted RUL + CI |
| POST | `/rul/explain` | Asset + AHP + RUL -> Claude explanation |

### `/upload` -- Dynamic Asset Upload

| Method | Route | Description |
|---|---|---|
| POST | `/upload/analyze` | Upload Excel -> infer draft criteria, train model (unapproved), score assets |
| POST | `/upload/approve-criteria` | SME approves (optionally edited) criteria + PM interval -> locks the model bundle; can be called again after "Edit Criteria" to re-approve |
| POST | `/upload/predict-all` | AHP weights + manual scores -> RUL for all uploaded assets (400 if criteria have never been approved; weight-only re-runs after that don't need re-approval) |
| POST | `/upload/explain` | Asset + AHP + RUL + asset type -> Claude explanation (includes multi-sensor correlation summary) |
| POST | `/upload/explain-breach` | Asset + detected breaches -> on-demand Claude alerts for medium/high severity breaches |
| GET | `/upload/audit-log` | Full approval audit trail -- every draft-vs-approved diff across all uploads |

### `/rag` -- RAG Knowledge Base Management

| Method | Route | Description |
|---|---|---|
| POST | `/rag/upload-document` | Upload a PDF manual, save to `docs/manuals/`, ingest into vector store |
| GET | `/rag/documents` | List all ingested documents across manuals, failure cases, and criteria configs |
| DELETE | `/rag/document` | Delete a document by filename and type, rebuild the vector store |

`GET /rag/documents` sorts `criteria_configs` newest-first by the timestamp embedded in each versioned filename, and also returns `latest_per_asset_type`, mapping each distinct asset type to its most recently saved config file.

`DELETE /rag/document` accepts a JSON body: `{"filename": str, "doc_type": "manual"|"failure_case"|"criteria_config"}`.

Full request/response schemas are available at `http://localhost:8000/docs` when the backend is running.

---

## Upload File Format

The upload endpoint accepts a two-sheet Excel file (`.xlsx`). Column names are flexible -- the system detects roles by keyword matching and Claude infers scoring logic from the actual data. The only structural requirements are the two sheet names and the presence of detectable role columns.

**Accepted file format: .xlsx (Excel) only. CSV is not supported.**

### Sheet 1: `Operational Telemetry`

| Role | Detection keywords | Required |
|---|---|---|
| Asset identifier | column name contains `_id` or `id` | Yes |
| Timestamp | column name contains `date`, `time`, or `timestamp` | Yes |
| RUL target | column name contains `rul`, `remaining`, `life`, or `ttf` | Yes |
| Operating hours | column name contains `hour`, `runtime`, `operating`, `cycles`, or `cumulative` | Yes |
| Sensor readings | all other numeric columns | Min. 2 |

### Sheet 2: `Failure & Maintenance Logs`

| Role | Detection keywords | Required |
|---|---|---|
| Asset identifier | same as telemetry sheet | Yes |
| Event date | column name contains `date`, `time`, or `timestamp` | Yes |
| Event type | column name contains `event`, `type`, `status`, or `category` | Yes |
| Component, root cause, etc. | any remaining columns | No |

If a required role cannot be detected, the validation error message lists all column names found in the file so you know what to rename.

### Example Column Names

| Role | Example column names that work |
|---|---|
| Asset identifier | Pump_ID, Asset_ID, Equipment_ID, Unit_ID |
| Timestamp | Date, Timestamp, Event_Date, Reading_Date |
| RUL target | True_RUL_Days, Remaining_Life_Hours, TTF_Days, RUL |
| Operating hours | Operating_Hours, Runtime_Hours, Cumulative_Hours, Cycles |
| Sensor readings | Any numeric column not matching the above roles |
| Log event type | Event_Type, Status, Category, Failure_Type |

If validation fails, the error message lists all column names detected in your file so you know exactly what to rename.

### Tips for Preparing Your Data

- One row per asset per day in the Operational Telemetry sheet
- Minimum 30 rows per asset recommended for reliable RUL training
- The more historical data included, the better the model accuracy
- Failure & Maintenance Logs sheet can have as few as 1 row
- All numeric sensor columns are automatically used as AHP features
- Column names can be in any format -- detection is keyword-based

---

## Project Structure

```
agelix-consulting-project-2026/
+-- main.py                        # FastAPI entry point (also serves frontend/dist/ in production)
+-- requirements.txt
+-- railway.toml                   # Railway build/start commands
+-- nixpacks.toml                  # Railway build environment
+-- ahp/                           # AHP engine (do not modify)
|   +-- criteria_scoring.py        # Scoring rules, convert_to_saaty(), clamp()
|   +-- ahp_engine.py              # Matrix math, CR calculation
|   +-- risk_calculator.py         # Risk factor dot product
|   +-- dynamic_criteria_scorer.py # Runtime CriteriaConfig interpreter
|   +-- threshold_breach_detector.py # Deterministic threshold/penalty breach detection
|   +-- api.py                     # /ahp/* endpoints
+-- rul/                           # RUL prediction
|   +-- feature_engineering.py     # 24-feature vector (default fleet)
|   +-- ml_rul_model.py            # predict() + predict_adjusted()
|   +-- train.py                   # Trains default fleet model -> model.pkl
|   +-- rul_explainer.py           # Anthropic API explanation (+ correlation summary)
|   +-- breach_explainer.py        # On-demand Anthropic API breach alerts
|   +-- mtbf_mtbm.py               # Deterministic MTBF/MTBM/replace-vs-maintain estimates
|   +-- dynamic_*.py               # Dynamic equivalents for uploaded assets
|   +-- api.py                     # /rul/* endpoints
+-- data/
|   +-- telemetry_aggregator.py    # Default fleet data source
|   +-- upload_schema.py           # Upload validation + column detection
|   +-- schema_inferrer.py         # Claude API + RAG context -> CriteriaConfig
|   +-- column_resolver.py         # Centralized column name lookups
|   +-- dynamic_aggregator.py      # Asset snapshots + multi-sensor trend/correlation features
|   +-- raw/                       # Telemetry, maintenance log, uploads
+-- upload/
|   +-- api.py                     # /upload/* endpoints (analyze, approve-criteria, predict-all,
|   |                              # explain, explain-breach; wires RAG retrieval)
+-- rag/
|   +-- document_loader.py         # Loads + chunks PDFs, markdown, JSON configs
|   +-- knowledge_base.py          # ChromaDB vector store (onnxruntime default embeddings)
|   +-- retriever.py               # RAG retrieval entry point for all use cases
|   +-- audit_log.py               # Writes/reads docs/audit_log.jsonl (approval diffs)
|   +-- ingest.py                  # CLI: python -m rag.ingest [--rebuild]
|   +-- api.py                     # /rag/* endpoints (upload, list, delete documents)
|   +-- stored_configs/            # Saved CriteriaConfig JSON files, versioned per approval
|   +-- chroma_db/                 # ChromaDB persistent store (auto-generated)
+-- docs/
|   +-- manuals/                   # PDF manuals for RAG ingestion (uploadable via UI)
|   +-- failure_cases/             # Auto-generated + manual failure case markdown
|   +-- audit_log.jsonl            # Append-only approval audit trail (auto-created)
+-- frontend/src/
|   +-- components/                # React components; Dashboard.jsx renders only uploaded-asset mode
|   +-- hooks/                     # useAHP (via AHPMatrix), useUpload, useKnowledgeBase
+-- tests/
```

Note: `frontend/src/components/` and `hooks/` also still contain the default-fleet-only components (`WeightDisplay`, `AssetRegistry`, `RiskRanking`, `CriteriaContribution`, `RiskScatterPlot`, `RULDisplay`, `RULExplanation`, `ManualScoreInputs`, `DataUpload`) and hooks (`useRiskScores`, `useRUL`) -- these are kept on disk intentionally but are no longer imported by `Dashboard.jsx`.

---

## Environment Variables

| Variable | Description | Required |
|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key for schema inference and explanations | Yes |
| `API_BASE_URL` | Backend base URL for the frontend | Yes (default: `http://localhost:8000`) |

Never commit `.env`. The `.env.example` file contains safe empty placeholders.

---

## Running Tests

```bash
python -m pytest tests/
```

The upload pipeline tests mock all Anthropic API calls -- no API key is required to run the test suite.

---

## Deployment

The app deploys to Railway as a single service serving both the 
FastAPI backend and React frontend.

### Steps
1. Push code to GitHub — Railway auto-deploys on every push to main
2. Set environment variables in Railway dashboard:
   - ANTHROPIC_API_KEY — your Anthropic API key
   - VITE_API_BASE_URL — leave empty
3. Deploy takes a few minutes (installs Python deps, generates 
   telemetry data, trains the default RUL model)
4. Subsequent deploys are similarly fast

**The frontend is not built on Railway.** `frontend/dist/` is committed 
to the repo and served directly by FastAPI (see `main.py`). If you 
change anything under `frontend/src/`, run `npm run build` inside 
`frontend/` locally and commit the resulting `frontend/dist/` changes 
before pushing — otherwise Railway will keep serving the old build.

### Redeploying after changes
git push origin main

Railway detects the push and redeploys automatically. The public 
URL stays the same.

### Note on persistent data
The RAG knowledge base and dynamic model are rebuilt on each deploy. 
To persist uploaded assets and knowledge base documents across 
deploys, configure a Railway volume.
