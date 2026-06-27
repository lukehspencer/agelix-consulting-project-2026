# Asset Management Dashboard

An asset management dashboard for **KSB Calio 30-40** centrifugal pump assets, built as an internship project for **Agelix Consulting** to extend the *Assets Maestro* platform.

## What it does

Users define relative importance weights across five risk criteria using an AHP (Analytic Hierarchy Process) pairwise comparison matrix. The system validates the matrix for consistency (CR <= 0.10), derives the weight vector, and applies it to 5 KSB Calio 30-40 pumps to produce a live risk ranking.

An XGBoost ML model predicts Remaining Useful Life (RUL) per pump using a 24-feature input vector that combines raw telemetry, AHP weights, and weighted scores as engineered features. The RUL prediction is adjusted by the AHP risk factor. Claude (via the Anthropic API) generates plain language explanations of each prediction with recommended maintenance actions.

All pump data comes from CEO-provided telemetry (1095 days / 3 years of daily sensor readings per pump). Each pump is captured at a different lifecycle stage to show meaningful spread across the dashboard. C1 (Criticality) and C4 (Downtime Impact) are manual inputs with defaults of 7 and 6 respectively.

**Criteria:** Criticality . Condition . Failure Probability . Downtime Impact . Maintenance Cost Trend

---

## Prerequisites

| Tool | Version |
|---|---|
| Python | 3.11+ |
| Node.js | 18+ | 
| npm | 9+ |
| libomp | Required on macOS for XGBoost (`brew install libomp`) |

---

## Setup

### 1. Clone and create a virtual environment

```bash
git clone <repo-url>
cd agelix-consulting-project-2026

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Add your Anthropic API key for RUL explanations
```

### 4. Generate data and train the ML model

```bash
# Generate 3-year telemetry + maintenance log from CEO's script
python data/generate_maintenance_log.py

# Train XGBoost on 5440 telemetry samples, save rul/model.pkl
python -m rul.train
```

### 5. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

---

## Running

Open two terminals.

**Terminal 1. FastAPI backend**
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2. React frontend**
```bash
cd frontend
npm run dev
```

<!-- To run npm on windows: & "C:\Program Files\nodejs\npm.cmd" -->
<!-- To run node and npm keywords set $env:PATH += ";C:\Program Files\nodejs\" -->

Open [http://localhost:5173](http://localhost:5173) in your browser.

The Vite dev server proxies `/ahp/*` and `/rul/*` requests to `http://localhost:8000`, so no CORS configuration is needed during development.

---

## Dashboard Features

| Feature | Description |
|---|---|
| AHP Matrix | 5x5 pairwise comparison input with Saaty scale dropdowns and auto-reciprocals |
| Manual Score Inputs | C1 (Criticality) and C4 (Downtime Impact) manual inputs with scoring guides |
| Data Upload | Upload custom pump data (CSV/JSON, 26 fields including rolling telemetry features) with validation + template download |
| KPI Cards | Average risk score, highest risk pump, high-risk count, CR status |
| Weight Distribution | Recharts bar chart of criterion weights after matrix submission |
| Asset Registry | Table of all pumps with expandable detail rows |
| Risk Ranking | Ranked table + color-coded bar chart (green 1-3, yellow 4-6, red 7-9) |
| Criteria Contribution | Stacked bar chart showing weighted criterion breakdown per pump |
| Risk vs Condition | Scatter plot with quadrant reference lines and colored regions |
| RUL Predictions | XGBoost predicted RUL per pump in months with confidence interval, color-coded (green >120mo, yellow 60-120mo, red <60mo), sorted by urgency |
| AI Explanations | Claude-generated maintenance recommendations per pump (on demand only) |
| Score History Log | Tracks matrix submissions, manual score overrides, and data uploads |

---

## Running tests

```bash
pytest tests/
```

---

## API Reference

Base URL: `http://localhost:8000`

### AHP Endpoints

| Method | Route | Description |
|---|---|---|
| `POST` | `/ahp/calculate-weights` | 5x5 pairwise matrix -> weights, lambda_max, CI, CR, valid flag |
| `POST` | `/ahp/score-asset` | Pump variables -> C1-C5 Saaty scores |
| `POST` | `/ahp/risk-factor` | weights + scores -> risk factor + weighted scores |
| `GET` | `/ahp/assets` | All pumps ranked by risk factor (`?weights=`, `?c1_score=`, `?c4_score=`) |

### RUL Endpoints

| Method | Route | Description |
|---|---|---|
| `POST` | `/rul/predict` | pump + AHP weights + scores + CR -> adjusted RUL + confidence interval |
| `POST` | `/rul/explain` | pump + AHP results + RUL -> Claude plain language explanation |

Both RUL endpoints reject requests with CR > 0.10 (HTTP 400).

Interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## Project Structure

```
agelix-consulting-project-2026/
+-- main.py                        # FastAPI entry point (mounts ahp + rul routers)
+-- ahp/                           # AHP module (Phase 1, do not modify)
|   +-- ahp_constants.py           # RI values, CR threshold, criteria names
|   +-- criteria_scoring.py        # C1-C5 scoring functions, convert_to_saaty()
|   +-- ahp_engine.py              # Matrix normalisation, weight derivation, CR
|   +-- risk_calculator.py         # Dot product risk factor, ranked asset list
|   +-- api.py                     # FastAPI AHP endpoints (loads from aggregator)
+-- rul/                           # RUL module (Phase 2)
|   +-- feature_engineering.py     # 24-feature vector builder
|   +-- train.py                   # Trains XGBoost on CEO telemetry (5440 samples)
|   +-- ml_rul_model.py            # predict() + predict_adjusted() with AHP risk adj
|   +-- rul_explainer.py           # Anthropic API (claude-sonnet-4-6) explanation
|   +-- api.py                     # FastAPI RUL endpoints (APIRouter via main.py)
|   +-- model.pkl                  # Trained XGBoost model (generated by train.py)
+-- data/
|   +-- raw/
|   |   +-- telemetry/
|   |   |   +-- KSB_Calio_Predictive_Maintenance_Complete.xlsx  # 1095 days x 5 pumps
|   |   +-- maintenance/
|   |       +-- maintenance_log.xlsx
|   +-- telemetry_aggregator.py    # Sole data source (replaces pumps.json)
|   +-- generate_maintenance_log.py # CEO's script: generates telemetry + maintenance log
+-- frontend/
|   +-- vite.config.js             # Vite + API proxy (/ahp, /rul)
|   +-- src/
|       +-- App.jsx
|       +-- components/
|       |   +-- Dashboard.jsx          # Orchestrates all components + state management
|       |   +-- AHPMatrix.jsx          # 5x5 pairwise matrix UI with CR validation
|       |   +-- ManualScoreInputs.jsx  # C1 + C4 manual inputs with scoring guides
|       |   +-- DataUpload.jsx         # CSV/JSON upload with validation + template
|       |   +-- WeightDisplay.jsx      # AHP weight distribution bar chart
|       |   +-- AssetRegistry.jsx      # Pump table with expandable detail rows
|       |   +-- RiskRanking.jsx        # Ranked risk table + color-coded bar chart
|       |   +-- CriteriaContribution.jsx # Stacked bar of weighted criterion contributions
|       |   +-- RiskScatterPlot.jsx    # Risk vs Condition scatter with quadrants
|       |   +-- RULDisplay.jsx         # RUL progress bars in months + confidence intervals
|       |   +-- RULExplanation.jsx     # Claude explanation cards per pump
|       +-- hooks/
|       |   +-- useAHP.js              # POST /ahp/calculate-weights
|       |   +-- useRiskScores.js       # GET /ahp/assets with current weights
|       |   +-- useRUL.js              # Auto-predict + on-demand explain
|       +-- utils/
|           +-- dateUtils.js
|           +-- dataParser.js          # CSV/JSON parsing + validation
+-- tests/
|   +-- rul/
|       +-- test_telemetry_aggregator.py
|       +-- test_feature_engineering.py
|       +-- test_ml_rul_model.py
|       +-- test_rul_explainer.py
+-- .env.example
+-- requirements.txt
+-- CLAUDE.md                      # Architecture spec and build guide
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, Uvicorn |
| Math | NumPy |
| Data | Pandas, openpyxl |
| ML Model | XGBoost, Scikit-learn, Joblib |
| GenAI | Anthropic API (claude-sonnet-4-6) |
| Frontend | React 18, Vite, Recharts |
| Testing | Pytest |
