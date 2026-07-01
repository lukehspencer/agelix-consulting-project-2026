# Assets Maestro -- Predictive Asset Management Dashboard

> An asset risk scoring and remaining useful life (RUL) prediction dashboard for industrial equipment, powered by AHP-based risk analysis, XGBoost ML, and RAG-augmented AI explanations via the Anthropic API.

---

## Overview

The dashboard scores industrial assets using the Analytic Hierarchy Process (AHP) -- a structured method for multi-criteria risk ranking -- and predicts remaining useful life using a trained XGBoost model. Risk scores and RUL predictions update dynamically as the user adjusts the AHP pairwise comparison matrix. A GenAI explanation layer (Claude, via the Anthropic API) generates plain-English maintenance recommendations for each asset on demand, enriched by a RAG (Retrieval-Augmented Generation) knowledge pipeline that retrieves relevant engineering standards, past failure cases, and prior asset configurations.

The dashboard operates in two modes. The default mode loads a pre-configured fleet of 5 KSB Calio 30-40 centrifugal pump assets from operational telemetry provided by the client. The upload mode accepts any asset type -- the user uploads an Excel file with operational telemetry and a failure/maintenance log, Claude analyzes the data and infers appropriate AHP criteria and scoring thresholds for that asset type, and the dashboard runs the full risk and RUL pipeline on the uploaded data.

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
| RAG Pipeline | ChromaDB, SentenceTransformers, LangChain |
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

Runs at `http://localhost:5173`. Vite proxies `/ahp/*`, `/rul/*`, and `/upload/*` to the backend automatically.

---

## How It Works

### AHP Risk Scoring

The user fills a pairwise comparison matrix in the dashboard, following Saaty's 1-9 scale. The engine derives a weight vector from the matrix and validates consistency using the Consistency Ratio (CR). A CR above 0.10 indicates an inconsistent matrix -- the dashboard surfaces a warning and blocks RUL predictions until the matrix is corrected.

In default fleet mode the matrix is always 5x5 (five fixed criteria). In upload mode the matrix is NxN where N is the number of criteria inferred by Claude for the uploaded asset type (3--7). Each asset is scored on a 1-10 internal scale, converted to the 1-9 Saaty scale. The overall risk factor is the dot product of the weight vector and score vector, producing a score from 1 to 9 per asset. Higher scores indicate higher risk.

In the default fleet mode, three criteria are derived automatically from sensor telemetry and two are manual inputs with defaults based on the KSB Calio operational context. In upload mode, no criteria are hardcoded -- the Anthropic API analyzes the uploaded data, infers appropriate criteria names and scoring thresholds for the detected asset type, and stores them in a CriteriaConfig that drives the entire scoring pipeline.

### RUL Prediction

The XGBoost model is trained on daily telemetry rows from the KSB dataset (1,095 days x 5 pumps). Each training sample is a 24-feature vector combining raw asset variables, the full AHP weight vector, the AHP weighted score vector, the overall risk factor, and 5 rolling telemetry features. The training target is `True_RUL_Days / 365` (years).

At inference time, the raw model prediction is adjusted by the AHP risk factor: `RUL_adjusted = RUL_raw x (1 - (risk_factor - 1) / 8)`. This means a higher risk score directly reduces predicted remaining life. RUL is displayed in **days** in the dashboard (`rul_years * 365`); the backend always returns years. Color thresholds: green &gt; 365 days, yellow 180--365 days, red &lt; 180 days.

### Dynamic Asset Upload

When a user uploads an Excel file (two sheets: Operational Telemetry and Failure & Maintenance Logs), the pipeline:

1. Validates the file and detects column roles by keyword heuristics -- no specific column names are required.
2. Queries the RAG knowledge base for relevant engineering standards, similar past CriteriaConfigs, and known failure cases.
3. Calls the Anthropic API to infer 3-7 AHP criteria appropriate for the detected asset type, with scoring thresholds calibrated to the actual data ranges, enriched by retrieved domain knowledge.
4. Stores the inferred CriteriaConfig in the knowledge base for future retrieval.
5. Trains a fresh XGBoost model on the uploaded dataset.
6. Auto-generates a failure case document recording the asset type, sensors, failure modes, criteria, and training metrics.
7. Scores each asset and predicts RUL using the user's AHP matrix.

All column name references flow through a central resolver module (`data/column_resolver.py`) -- no part of the pipeline hardcodes column names.

### GenAI Explanations

On demand, the dashboard calls the Anthropic API to generate a 3-4 sentence plain-English explanation for each asset's RUL prediction. The explanation names the biggest AHP risk drivers given the current weights, highlights the key telemetry signals, and recommends a specific maintenance action. For uploaded assets, the explanation adapts to the inferred asset type and failure modes, and is enriched with retrieved failure precedents and maintenance guidance from the RAG knowledge base when available.

### RAG Knowledge Pipeline

The RAG system enriches Claude's prompts with retrieved domain knowledge. It is entirely optional -- when the knowledge base is missing or empty, the system behaves identically to before.

Three document types are ingested into a ChromaDB vector store using SentenceTransformer (`all-MiniLM-L6-v2`) embeddings:

- **PDF manuals** (`docs/manuals/`) -- engineering standards and operating limits, chunked at 500 characters.
- **Failure case markdown** (`docs/failure_cases/`) -- auto-generated after each successful upload training run (asset type, sensors, failure modes, criteria, training RMSE), chunked at 300 characters. Manual failure case files can also be added.
- **CriteriaConfigs** (`rag/stored_configs/`) -- saved as JSON after each successful schema inference, indexed as whole documents.

The retriever makes targeted queries per use case:
- **Schema inference**: retrieves engineering standards, similar past configs, and failure cases, injected as a RETRIEVED DOMAIN KNOWLEDGE block in the inference prompt.
- **RUL explanation**: retrieves failure precedents and maintenance guidance, injected as a RETRIEVED MAINTENANCE KNOWLEDGE block in the explainer prompt with an instruction to cite the most relevant precedent.

The knowledge base grows automatically as assets are uploaded -- each upload stores its CriteriaConfig and generates a failure case document. To bootstrap with existing domain knowledge, place PDFs and markdown files in the appropriate directories and run `python -m rag.ingest`.

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
| POST | `/upload/analyze` | Upload Excel -> infer criteria, train model, score assets |
| POST | `/upload/predict-all` | AHP weights + manual scores -> RUL for all uploaded assets |
| POST | `/upload/explain` | Asset + AHP + RUL + asset type -> Claude explanation |

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
+-- main.py                        # FastAPI entry point
+-- requirements.txt
+-- ahp/                           # AHP engine (do not modify)
|   +-- criteria_scoring.py        # Scoring rules, convert_to_saaty(), clamp()
|   +-- ahp_engine.py              # Matrix math, CR calculation
|   +-- risk_calculator.py         # Risk factor dot product
|   +-- dynamic_criteria_scorer.py # Runtime CriteriaConfig interpreter
|   +-- api.py                     # /ahp/* endpoints
+-- rul/                           # RUL prediction
|   +-- feature_engineering.py     # 24-feature vector (default fleet)
|   +-- ml_rul_model.py            # predict() + predict_adjusted()
|   +-- train.py                   # Trains default fleet model -> model.pkl
|   +-- rul_explainer.py           # Anthropic API explanation
|   +-- dynamic_*.py               # Dynamic equivalents for uploaded assets
|   +-- api.py                     # /rul/* endpoints
+-- data/
|   +-- telemetry_aggregator.py    # Default fleet data source
|   +-- upload_schema.py           # Upload validation + column detection
|   +-- schema_inferrer.py         # Claude API + RAG context -> CriteriaConfig
|   +-- column_resolver.py         # Centralized column name lookups
|   +-- dynamic_aggregator.py      # Asset snapshots for uploaded data
|   +-- raw/                       # Telemetry, maintenance log, uploads
+-- upload/
|   +-- api.py                     # /upload/* endpoints (wires RAG retrieval)
+-- rag/
|   +-- document_loader.py         # Loads + chunks PDFs, markdown, JSON configs
|   +-- knowledge_base.py          # ChromaDB vector store (SentenceTransformer embeddings)
|   +-- retriever.py               # RAG retrieval entry point for all use cases
|   +-- ingest.py                  # CLI: python -m rag.ingest [--rebuild]
|   +-- stored_configs/            # Saved CriteriaConfig JSON files (auto-populated)
|   +-- chroma_db/                 # ChromaDB persistent store (auto-generated)
+-- docs/
|   +-- manuals/                   # PDF manuals for RAG ingestion
|   +-- failure_cases/             # Auto-generated + manual failure case markdown
+-- frontend/src/
|   +-- components/                # React components
|   +-- hooks/                     # useAHP, useRUL, useUpload
+-- tests/
```

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
