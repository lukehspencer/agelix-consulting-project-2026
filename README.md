# Assets Maestro -- Predictive Asset Management Dashboard

> An asset risk scoring and remaining useful life (RUL) prediction dashboard for industrial equipment, powered by AHP-based risk analysis and XGBoost ML, with AI-generated maintenance explanations via the Anthropic API.

---

## Overview

The dashboard scores industrial assets using the Analytic Hierarchy Process (AHP) -- a structured method for multi-criteria risk ranking -- and predicts remaining useful life using a trained XGBoost model. Risk scores and RUL predictions update dynamically as the user adjusts the AHP pairwise comparison matrix. A GenAI explanation layer (Claude, via the Anthropic API) generates plain-English maintenance recommendations for each asset on demand.

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

### Step 6 -- Install frontend dependencies

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

The user fills a 5x5 pairwise comparison matrix in the dashboard, following Saaty's 1-9 scale. The engine derives a weight vector from the matrix and validates consistency using the Consistency Ratio (CR). A CR above 0.10 indicates an inconsistent matrix -- the dashboard surfaces a warning and blocks RUL predictions until the matrix is corrected.

Each asset is scored against 5 criteria (C1-C5) on a 1-10 internal scale, converted to the 1-9 Saaty scale. The overall risk factor is the dot product of the weight vector and score vector, producing a score from 1 to 9 per asset. Higher scores indicate higher risk.

In the default fleet mode, three criteria (Condition, Failure Probability, Maintenance Cost Trend) are derived automatically from sensor telemetry. Two criteria (Criticality, Downtime Impact) are manual inputs with defaults based on the KSB Calio operational context.

### RUL Prediction

The XGBoost model is trained on daily telemetry rows from the KSB dataset (1,095 days x 5 pumps). Each training sample is a 24-feature vector combining raw asset variables, the full AHP weight vector, the AHP weighted score vector, the overall risk factor, and 5 rolling telemetry features. The training target is `True_RUL_Days / 365` (years).

At inference time, the raw model prediction is adjusted by the AHP risk factor: `RUL_adjusted = RUL_raw x (1 - (risk_factor - 1) / 8)`. This means a higher risk score directly reduces predicted remaining life. RUL is displayed in months in the dashboard; the backend always returns years.

### Dynamic Asset Upload

When a user uploads an Excel file (two sheets: Operational Telemetry and Failure & Maintenance Logs), the pipeline:

1. Validates the file and detects column roles by keyword heuristics -- no specific column names are required.
2. Calls the Anthropic API to infer 5 AHP criteria appropriate for the detected asset type, with scoring thresholds calibrated to the actual data ranges.
3. Trains a fresh XGBoost model on the uploaded dataset.
4. Scores each asset and predicts RUL using the user's AHP matrix.

All column name references flow through a central resolver module (`data/column_resolver.py`) -- no part of the pipeline hardcodes column names.

### GenAI Explanations

On demand, the dashboard calls the Anthropic API to generate a 3-4 sentence plain-English explanation for each asset's RUL prediction. The explanation names the biggest AHP risk drivers given the current weights, highlights the key telemetry signals, and recommends a specific maintenance action. For uploaded assets, the explanation adapts to the inferred asset type and failure modes.

---

## API Reference

The FastAPI backend exposes three routers.

### `/ahp` -- AHP Engine

| Method | Route | Description |
|---|---|---|
| POST | `/ahp/calculate-weights` | 5x5 matrix -> weights, CR, valid flag |
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
|   +-- schema_inferrer.py         # Claude API -> CriteriaConfig
|   +-- column_resolver.py         # Centralized column name lookups
|   +-- dynamic_aggregator.py      # Asset snapshots for uploaded data
|   +-- raw/                       # Telemetry, maintenance log, uploads
+-- upload/
|   +-- api.py                     # /upload/* endpoints
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
pytest tests/
```

The upload pipeline tests mock all Anthropic API calls -- no API key is required to run the test suite.
