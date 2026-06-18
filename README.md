# Asset Risk Dashboard — Dynamic AHP Module

An asset risk prioritisation dashboard for industrial centrifugal pump assets, built as an internship project for **Agelix Consulting** to extend the *Assets Maestro* platform.

## What it does

Users define relative importance weights across five risk criteria using an AHP (Analytic Hierarchy Process) pairwise comparison matrix. The system validates the matrix for consistency (CR ≤ 0.10), derives the weight vector, and applies it to 10 centrifugal pump assets to produce a live risk ranking.

**Criteria:** Criticality · Condition · Failure Probability · Downtime Impact · Maintenance Cost Trend

---

## Prerequisites

| Tool | Version |
|---|---|
| Python | 3.11+ |
| Node.js | 18+ |
| npm | 9+ |

---

## Setup

### 1 — Clone and create a virtual environment

```bash
git clone <repo-url>
cd agelix-consulting-project-2026

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
```

### 2 — Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3 — Configure environment

```bash
cp .env.example .env
# Edit .env if you need non-default ports
```

### 4 — Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

---

## Running

Open two terminals.

**Terminal 1 — FastAPI backend**
```bash
uvicorn ahp.api:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 — React frontend**
```bash
cd frontend
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

The Vite dev server proxies all `/ahp/*` requests to `http://localhost:8000`, so no CORS configuration is needed during development.

---

## Running tests

```bash
pytest tests/
```

---

## API Reference

Base URL: `http://localhost:8000`

| Method | Route | Description |
|---|---|---|
| `POST` | `/ahp/calculate-weights` | 5×5 pairwise matrix → weights, λ_max, CI, CR, valid flag |
| `POST` | `/ahp/score-asset` | Pump variables → C1–C5 Saaty scores |
| `POST` | `/ahp/risk-factor` | weights + scores → risk factor + weighted scores |
| `GET` | `/ahp/assets` | All pumps ranked by risk factor (pass `?weights=` query params) |

Interactive docs: [http://localhost:8000/docs](http://localhost:8000/docs)

### Example — calculate weights

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

### Example — get ranked assets with custom weights

```bash
curl "http://localhost:8000/ahp/assets?weights=0.35&weights=0.25&weights=0.2&weights=0.12&weights=0.08"
```

---

## Project Structure

```
agelix-consulting-project-2026/
├── ahp/
│   ├── ahp_constants.py      # RI values, CR threshold, criteria names, Saaty scale
│   ├── criteria_scoring.py   # C1–C5 scoring functions, clamp(), convert_to_saaty()
│   ├── ahp_engine.py         # Matrix normalisation, weight derivation, CR computation
│   ├── risk_calculator.py    # Dot product risk factor, ranked asset list
│   └── api.py                # FastAPI application and endpoints
├── data/
│   └── pumps.json            # 10 mock centrifugal pump assets (29 variables each)
├── frontend/
│   ├── package.json
│   ├── vite.config.js        # Vite + API proxy config
│   └── src/
│       ├── App.jsx
│       ├── components/
│       │   └── AHPMatrix.jsx # 5×5 pairwise matrix UI with CR validation
│       └── hooks/
│           └── useAHP.js     # API hook for /ahp/calculate-weights
├── tests/
│   └── ahp/
├── .env.example
├── requirements.txt
└── CLAUDE.md                 # Architecture spec and build guide
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, Uvicorn |
| Math | NumPy |
| Data | Pandas |
| Frontend | React 18, Vite, Recharts |
| Testing | Pytest, HTTPX |
| Phase 2 ML | Scikit-learn (XGBoost / Random Forest) |

---

## Phase 2 (not yet built)

The AHP weight vector and per-criterion weighted scores are preserved in every API response as engineered feature inputs for a future ML-based Remaining Useful Life (RUL) prediction model.
