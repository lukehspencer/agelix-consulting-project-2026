# CLAUDE.md — Asset Risk Dashboard (Dynamic AHP Module)

## Project Overview

This is a solo internship project for **Agelix Consulting**, built to extend their asset lifecycle management platform **Assets Maestro**. The goal is to build an asset management dashboard for centrifugal pump assets with three calculation modules:

1. **Dynamic AHP** (Phase 1 — current focus)
2. **Overall Risk Factor** (dot product of AHP weights × asset scores)
3. **ML-Based RUL — Remaining Useful Life** (Phase 2)

The AHP module is the foundation. AHP criteria weights and per-asset weighted score vectors will later serve as engineered feature inputs into the ML RUL model — making RUL predictions adaptive to expert judgment encoded in the AHP matrix.

---

## Current Phase

**Phase 1 — Dynamic AHP + Risk Factor Calculation**

Do not build or modify anything in `rul/` unless explicitly instructed. All current work is scoped to:
- `data/pumps.json`
- `ahp/ahp_constants.py`
- `ahp/criteria_scoring.py`
- `ahp/ahp_engine.py`
- `ahp/risk_calculator.py`
- `ahp/api.py`
- `frontend/src/` React components

---

## Folder Structure

```
asset-risk-dashboard/
│
├── CLAUDE.md                          # This file
├── README.md                          # Project overview and setup instructions
├── .env                               # Environment variables (never commit)
├── .env.example                       # Safe template (no secrets)
├── .gitignore
├── requirements.txt                   # Python dependencies
│
├── ahp/                               # AHP MODULE (Python)
│   ├── __init__.py
│   ├── ahp_constants.py               # Saaty RI values, CR threshold, criteria names
│   ├── criteria_scoring.py            # Scoring rules for C1–C5, convert_to_saaty()
│   ├── ahp_engine.py                  # Normalize matrix, derive weights, compute CR
│   ├── risk_calculator.py             # Dot product → overall risk factor per pump
│   └── api.py                         # FastAPI endpoints
│
├── rul/                               # RUL MODULE (Phase 2 — do not modify yet)
│   ├── __init__.py
│   ├── rul_engine.py                  # Linear RUL placeholder
│   └── ml_rul_model.py                # ML model integration (Phase 2)
│
├── data/
│   ├── pumps.json                     # 10 mock centrifugal pump assets (29 variables each)
│   └── data_schema.py                 # Variable definitions and types
│
├── frontend/                          # React frontend
│   └── src/
│       ├── App.jsx
│       ├── components/
│       │   ├── Dashboard.jsx
│       │   ├── AssetRegistry.jsx
│       │   ├── AHPMatrix.jsx          # 5×5 pairwise matrix UI
│       │   ├── WeightDisplay.jsx      # AHP weights chart
│       │   ├── RiskRanking.jsx        # Asset risk scores ranked
│       │   └── RiskScatterPlot.jsx    # Risk vs RUL scatter (Phase 2 ready)
│       ├── hooks/
│       │   ├── useAHP.js
│       │   └── useRiskScores.js
│       └── utils/
│           └── dateUtils.js
│
├── tests/
│   ├── ahp/
│   │   ├── test_ahp_engine.py
│   │   └── test_criteria_scoring.py
│   └── rul/
│       └── test_rul_engine.py
│
└── docs/
    ├── ahp-methodology.md
    ├── criteria-scoring-rules.md
    └── data-schema.md
```

---

## Asset Type

**Centrifugal Pumps** — all mock data and scoring rules are calibrated for industrial centrifugal pump assets.

---

## Data Schema — 29 Variables Per Pump

### Identity (7)
| Variable | Type | Notes |
|---|---|---|
| `asset_id` | String | e.g. PUMP-001 |
| `asset_name` | String | Human-readable name |
| `manufacturer` | String | e.g. Grundfos |
| `model_number` | String | |
| `location` | String | Plant / Line |
| `install_date` | Date string (YYYY-MM-DD) | Used to calculate age_years |
| `expected_lifespan_years` | Number | Manufacturer/industry standard |

### Operational (4)
| Variable | Type | Notes |
|---|---|---|
| `rated_flow_rate_gpm` | Number | Manufacturer max |
| `actual_flow_rate_gpm` | Number | Current operating point |
| `operating_hours_per_day` | Number | |
| `total_runtime_hours` | Number | Cumulative |

### Condition / Health (5)
| Variable | Type | Notes |
|---|---|---|
| `condition_score` | Number (1–10) | From last inspection; 10 = perfect |
| `vibration_level` | Enum: Normal / High / Critical | |
| `temperature_celsius` | Number | |
| `seal_condition` | Enum: Good / Worn / Leaking | |
| `bearing_condition` | Enum: Good / Worn / Failed | |

### Maintenance (5)
| Variable | Type | Notes |
|---|---|---|
| `last_maintenance_date` | Date string (YYYY-MM-DD) | |
| `maintenance_frequency_days` | Number | Scheduled PM interval |
| `maintenance_cost_last_year` | Number (USD) | |
| `maintenance_cost_trend` | Enum: Increasing / Stable / Decreasing | |
| `number_of_failures_last_3yr` | Number | |

### AHP Criteria Scores (5) — Derived
| Variable | Type | How Derived |
|---|---|---|
| `score_criticality` | Float (1–9) | Manual input → convert_to_saaty() |
| `score_condition` | Float (1–9) | condition_score + penalties → convert_to_saaty() |
| `score_failure_probability` | Float (1–9) | age + failures + overdue → convert_to_saaty() |
| `score_downtime_impact` | Float (1–9) | Manual input → convert_to_saaty() |
| `score_maintenance_cost_trend` | Float (1–9) | trend + cost level → convert_to_saaty() |

### Calculated Outputs (3)
| Variable | Formula |
|---|---|
| `age_years` | today − install_date |
| `usage_intensity_pct` | actual_flow / rated_flow × 100 |
| `days_since_maintenance` | today − last_maintenance_date |

---

## AHP Criteria — The 5 Factors (C1–C5)

| # | Criterion | Input Type |
|---|---|---|
| C1 | Criticality | Manual (1–10) |
| C2 | Condition | Derived |
| C3 | Failure Probability | Derived |
| C4 | Downtime Impact | Manual (1–10) |
| C5 | Maintenance Cost Trend | Derived |

---

## Scoring Rules — `criteria_scoring.py`

### Scale Convention
- Internal scoring logic uses **1–10**
- All outputs converted to **1–9 (Saaty scale)** via `convert_to_saaty()` before leaving the module
- Higher score = higher risk contribution across ALL criteria

### convert_to_saaty()
```python
def convert_to_saaty(score: float) -> float:
    return round(1 + (score - 1) * (8 / 9), 2)
```

### C2 — Condition
```
base score  = invert(condition_score):
              9–10 → 1, 7–8 → 3, 5–6 → 5, 3–4 → 7, 1–2 → 9

vibration:    Normal → 0, High → +1, Critical → +2
seal:         Good   → 0, Worn → +1, Leaking  → +2
bearing:      Good   → 0, Worn → +1, Failed   → +2

raw = clamp(base + penalties, 1, 10)
output = convert_to_saaty(raw)
```

### C3 — Failure Probability
```
age_ratio     = age_years / expected_lifespan_years

age_factor:   ratio < 0.2  → 0
              ratio < 0.4  → 1
              ratio < 0.6  → 2
              ratio < 0.8  → 3
              ratio < 1.0  → 4
              ratio ≥ 1.0  → 5   (at or past expected lifespan)

failure_factor = min(number_of_failures_last_3yr, 4)

overdue_ratio = days_since_maintenance / maintenance_frequency_days

overdue_factor: overdue_ratio < 0.5  → 0
                overdue_ratio < 1.0  → 1
                overdue_ratio ≥ 1.0  → 2   (past due)

raw = clamp(round((age_factor + failure_factor + overdue_factor) / 11 * 10), 1, 10)
output = convert_to_saaty(raw)
```

### C5 — Maintenance Cost Trend
```
trend base:   Decreasing → 2, Stable → 5, Increasing → 8
cost modifier: <$1k → -1, $1k–$3k → 0, $3k–$6k → +1, >$6k → +2

raw = clamp(base + modifier, 1, 10)
output = convert_to_saaty(raw)
```

---

## AHP Engine — `ahp_engine.py`

### Input
A 5×5 pairwise comparison matrix (upper triangle filled by user, lower triangle auto-filled with reciprocals).

### Steps
1. Fill reciprocals: `matrix[j][i] = 1 / matrix[i][j]`
2. Column-normalize: divide each cell by its column sum
3. Derive weights: average each row of normalized matrix → `weights [w1–w5]`, sum = 1.0
4. Compute consistency:
```
λ_max = mean(weighted_sum_vector / weights)
CI    = (λ_max - n) / (n - 1)     # n = 5
CR    = CI / RI[5]                 # RI[5] = 1.12
```
5. Validate: CR ≤ 0.10 → valid; CR > 0.10 → warn user

### Constants (`ahp_constants.py`)
```python
RI = {1: 0.00, 2: 0.00, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32}
CR_THRESHOLD = 0.10
CRITERIA = ["Criticality", "Condition", "Failure Probability",
            "Downtime Impact", "Maintenance Cost Trend"]
SAATY_SCALE = {1: "Equal", 3: "Moderate", 5: "Strong", 7: "Very Strong", 9: "Extreme"}
```

---

## Risk Calculator — `risk_calculator.py`

```python
risk_factor = sum(w * s for w, s in zip(weights, scores))
```

- Weights from AHP engine (sum to 1.0)
- Scores from criteria_scoring.py (1–9 Saaty scale)
- Result: risk factor per pump between 1–9
- All pumps ranked highest → lowest by risk factor

---

## FastAPI Endpoints — `api.py`

| Method | Route | Description |
|---|---|---|
| POST | `/ahp/calculate-weights` | Takes 5×5 matrix → returns weights + CR + valid flag |
| POST | `/ahp/score-asset` | Takes pump variables → returns C1–C5 scores |
| POST | `/ahp/risk-factor` | Takes weights + scores → returns risk factor |
| GET | `/ahp/assets` | Returns all pumps with current risk scores ranked |

### GET /ahp/assets — weight query params
Weights are passed as repeated query parameters:
```
GET /ahp/assets?weights=0.35&weights=0.25&weights=0.2&weights=0.12&weights=0.08
```
Defaults to equal weights `[0.2, 0.2, 0.2, 0.2, 0.2]` when no params are supplied,
so the endpoint works on first load before the user has submitted a matrix.

### POST /ahp/score-asset — C1 and C4 field names
C1 and C4 are manual inputs. The request body must use:
- `criticality_raw` (float, 1–10) for C1
- `downtime_impact_raw` (float, 1–10) for C4

These differ from `score_criticality` / `score_downtime_impact` in `pumps.json`, which
store the already-converted Saaty values (1–9). The raw fields are what the API
receives; `criteria_scoring.py` converts them internally via `convert_to_saaty()`.

---

## Data Flow

```
pumps.json
    ↓
criteria_scoring.py   →   score vector per pump [s1–s5] on 1–9 scale
    ↓
ahp_engine.py         →   weight vector [w1–w5] from pairwise matrix + CR
    ↓
risk_calculator.py    →   risk factor per pump (dot product)
    ↓
api.py                →   FastAPI serves to React
    ↓
React Dashboard       →   AHP matrix UI, weight chart, risk ranking (live updates)
```

---

## Dynamic Behavior

When any pairwise comparison value changes in the UI:
1. Matrix updates → reciprocals recalculate
2. Weights recalculate
3. CR revalidates
4. All 10 pump risk scores update
5. Risk ranking re-renders

No page refresh required. Everything updates in real time.

---

## File Build Order

Build in this exact sequence to avoid dependency issues:

```
1. data/pumps.json              ✓ complete
2. ahp/ahp_constants.py         ✓ complete
3. ahp/criteria_scoring.py      ✓ complete
4. ahp/ahp_engine.py            ✓ complete
5. ahp/risk_calculator.py       ✓ complete
6. ahp/api.py                   ✓ complete
7. frontend/ (React UI last)    ✓ AHPMatrix.jsx complete — WeightDisplay,
                                  RiskRanking, Dashboard in progress
```

### Dev servers
- Backend: `uvicorn ahp.api:app --reload` → `http://localhost:8000`
- Frontend: `cd frontend && npm run dev` → `http://localhost:5173`
- Vite proxies `/ahp/*` → `http://localhost:8000` (no CORS config needed in dev)

---

## Tech Stack

| Layer | Tool |
|---|---|
| AHP Backend | Python 3.11+ |
| Matrix Math | NumPy |
| Data Handling | Pandas |
| API Layer | FastAPI + Uvicorn |
| Frontend | React + Recharts |
| Testing | Pytest |
| Phase 2 ML | Scikit-learn (XGBoost / Random Forest) |

---

## Phase 2 Notes (Do Not Build Yet)

The AHP module is architecturally designed to feed into a Phase 2 ML RUL model:

- Store **full weight vector** `[w1–w5]`, not just the final risk score
- Store **each weighted score individually** `[w1×s1, w2×s2, ...]`
- These become engineered feature inputs to the ML model alongside raw variables
- The ML model learns: given this AHP-weighted risk profile → predict RUL
- This makes RUL predictions adaptive to expert judgment encoded in the AHP matrix

Do not collapse weights into a single scalar or discard the per-criterion weighted scores.

---

## Key Conventions

- All Python files use snake_case
- All React files use PascalCase for components, camelCase for hooks/utils
- Internal scoring always 1–10; output always 1–9 (Saaty)
- Higher score = higher risk across all criteria (consistent direction)
- CR > 0.10 must surface a warning to the user — never silently proceed
- `clamp()` and `convert_to_saaty()` live in `criteria_scoring.py` and are imported where needed