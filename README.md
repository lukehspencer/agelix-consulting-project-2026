# Asset Management Dashboard

An asset management dashboard for industrial centrifugal pump assets, built as an internship project for **Agelix Consulting** to extend the *Assets Maestro* platform.

## What it does

Users define relative importance weights across five risk criteria using an AHP (Analytic Hierarchy Process) pairwise comparison matrix. The system validates the matrix for consistency (CR <= 0.10), derives the weight vector, and applies it to centrifugal pump assets to produce a live risk ranking.

An XGBoost ML model predicts Remaining Useful Life (RUL) per pump using the AHP weights and asset condition data as engineered features. Claude (via the Anthropic API) generates plain language explanations of each prediction with recommended maintenance actions.

The dashboard ships with 5 default pump assets. Users can also upload their own pump data (CSV or JSON) to replace the default dataset. All scores, charts, RUL predictions, and rankings update in real time when weights or data change.

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
# Edit ports if needed
```

### 4. Train the ML model

```bash
python -m rul.train
```

This generates `rul/model.pkl` from 500 synthetic pump records. Required before RUL predictions work.

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

Open [http://localhost:5173](http://localhost:5173) in your browser.

The Vite dev server proxies `/ahp/*` and `/rul/*` requests to `http://localhost:8000`, so no CORS configuration is needed during development.

---

## Dashboard Features

| Feature | Description |
|---|---|
| AHP Matrix | 5x5 pairwise comparison input with Saaty scale dropdowns and auto-reciprocals |
| Data Upload | Upload custom pump data (CSV/JSON) with full validation, or use default dataset |
| KPI Cards | Average risk score, highest risk pump, high-risk count, CR status |
| Weight Distribution | Recharts bar chart of criterion weights after matrix submission |
| Asset Registry | Table of all pumps with expandable detail rows showing all 29 variables |
| Risk Ranking | Ranked table + color-coded bar chart (green 1-3, yellow 4-6, red 7-9) |
| Criteria Contribution | Stacked bar chart showing weighted criterion breakdown per pump |
| Risk vs Condition | Scatter plot with quadrant reference lines and colored regions |
| RUL Predictions | XGBoost predicted RUL per pump with confidence interval and color-coded bars |
| AI Explanations | Claude-generated maintenance recommendations per pump (on demand) |
| Score History Log | Tracks each matrix submission with weights, pump scores, and CR |

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
| `GET` | `/ahp/assets` | All pumps ranked by risk factor (pass `?weights=` query params) |

### RUL Endpoints

| Method | Route | Description |
|---|---|---|
| `POST` | `/rul/predict` | pump + AHP weights + scores + CR -> RUL + confidence interval |
| `POST` | `/rul/explain` | pump + AHP results + RUL -> Claude plain language explanation |

Both RUL endpoints reject requests with CR > 0.10 (HTTP 400).

Interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)

### Example. calculate weights

```bash
curl -X POST http://localhost:8000/ahp/calculate-weights \
  -H "Content-Type: application/json" \
  -d '{
    "matrix": [
      [1, 3, 5, 2, 4],
      [1, 1, 3, 1, 2],
      [1, 1, 1, 1, 1],
      [1, 1, 1, 1, 2],
      [1, 1, 1, 1, 1]
    ]
  }'
```

### Example. get ranked assets with custom weights

```bash
curl "http://localhost:8000/ahp/assets?weights=0.35&weights=0.25&weights=0.2&weights=0.12&weights=0.08"
```

---

## Project Structure

```
agelix-consulting-project-2026/
├── main.py                    # FastAPI entry point (mounts ahp + rul routers)
├── ahp/                       # AHP module (Phase 1)
│   ├── ahp_constants.py       # RI values, CR threshold, criteria names, Saaty scale
│   ├── criteria_scoring.py    # C1-C5 scoring functions, clamp(), convert_to_saaty()
│   ├── ahp_engine.py          # Matrix normalisation, weight derivation, CR computation
│   ├── risk_calculator.py     # Dot product risk factor, ranked asset list
│   └── api.py                 # FastAPI AHP endpoints
├── rul/                       # RUL module (Phase 2)
│   ├── feature_engineering.py # 19-feature vector builder
│   ├── train.py               # Synthetic data generation + XGBoost training
│   ├── ml_rul_model.py        # Loads model.pkl, exposes predict()
│   ├── rul_explainer.py       # Anthropic API call for plain language explanation
│   ├── api.py                 # FastAPI RUL endpoints (/rul/predict, /rul/explain)
│   └── model.pkl              # Trained XGBoost model (generated by train.py)
├── data/
│   └── pumps.json             # 5 mock centrifugal pump assets (29 variables each)
├── frontend/
│   ├── package.json
│   ├── vite.config.js         # Vite + API proxy config (/ahp, /rul)
│   └── src/
│       ├── App.jsx
│       ├── components/
│       │   ├── Dashboard.jsx          # Orchestrates all components + state management
│       │   ├── AHPMatrix.jsx          # 5x5 pairwise matrix UI with CR validation
│       │   ├── DataUpload.jsx         # CSV/JSON upload with validation + template download
│       │   ├── WeightDisplay.jsx      # AHP weight distribution bar chart
│       │   ├── AssetRegistry.jsx      # Pump table with expandable detail rows
│       │   ├── RiskRanking.jsx        # Ranked risk table + color-coded bar chart
│       │   ├── CriteriaContribution.jsx # Stacked bar of weighted criterion contributions
│       │   ├── RiskScatterPlot.jsx    # Risk vs Condition scatter with quadrants
│       │   ├── RULDisplay.jsx         # RUL progress bars + confidence intervals
│       │   └── RULExplanation.jsx     # Claude explanation cards per pump
│       ├── hooks/
│       │   ├── useAHP.js              # API hook for /ahp/calculate-weights
│       │   ├── useRiskScores.js       # Fetches /ahp/assets with current weights
│       │   └── useRUL.js              # RUL prediction + explanation state
│       └── utils/
│           ├── dateUtils.js
│           └── dataParser.js          # CSV/JSON parsing + validation (client-side)
├── tests/
│   └── rul/
│       ├── test_feature_engineering.py
│       ├── test_ml_rul_model.py
│       └── test_rul_explainer.py
├── .env.example
├── requirements.txt
└── CLAUDE.md                  # Architecture spec and build guide
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, Uvicorn |
| Math | NumPy |
| Data | Pandas |
| ML Model | XGBoost, Scikit-learn |
| GenAI | Anthropic API (claude-sonnet-4-6) |
| Frontend | React 18, Vite, Recharts |
| Testing | Pytest, HTTPX |
