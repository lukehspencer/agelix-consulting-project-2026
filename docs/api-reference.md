# API Reference

This document describes every HTTP endpoint exposed by the Asset Management Dashboard backend, across all four routers (`/ahp`, `/rul`, `/upload`, `/rag`). It is written for a developer integrating against the API directly, without reading the source. Interactive Swagger docs are also available at `http://localhost:8000/docs` when the backend is running.

---

## Introduction

### Two dashboard modes

The system actually has two overlapping "mode" distinctions worth separating:

**1. Default Fleet Mode vs. Uploaded Asset Mode (which router you use).** Default Fleet Mode serves a fixed set of 5 KSB Calio 30-40 pumps with hardcoded scoring rules, via the **AHP Router** (`/ahp`) and **RUL Router** (`/rul`). It is fully functional but **not rendered in the dashboard UI** — nothing in the frontend calls these two routers anymore; they exist for direct API use only. Uploaded Asset Mode is the dashboard's only rendered view: a user uploads an Excel file of any asset type, Claude infers 3-7 AHP criteria dynamically (a `CriteriaConfig`), and all scoring, training, and RUL prediction for that asset type flow through the **Upload Router** (`/upload`) instead. A fourth router, the **RAG Router** (`/rag`), manages the knowledge base (manuals, failure cases, stored criteria configs) that enriches both `/upload` and, for `/upload`, the default-fleet-style explanation path.

**2. Training mode vs. prediction mode (within Uploaded Asset Mode only).** Every file `POST /upload/analyze` receives does exactly one of two things, decided automatically by whether a RUL/remaining-life column is detected in the telemetry sheet:
- **Training mode** — the file has a labeled RUL target column (historical run-to-failure data). A fresh XGBoost model is trained and saved for that asset type.
- **Prediction mode** — the file has no such column (current telemetry, unknown outcome). No training happens; the file is scored against an already-trained model for that asset type.

A single upload is never both — training on and predicting from the same file would be self-validating (the model would have seen the exact rows it was later "predicting" on) rather than genuinely predictive. See "Data Format" below for how the column is detected, and `POST /upload/analyze` for the full behavior of each branch.

### The two-model RUL system

For uploaded assets, every remaining-useful-life estimate actually comes from **two independent models**, computed alongside each other, never one instead of the other:

1. **ML (XGBoost)** — a per-asset-type model trained on the uploaded historical data (`rul/dynamic_train.py`), predicting RUL from a feature vector of AHP scores/weights, rolling sensor statistics, multi-sensor trend/correlation features, and threshold-breach counts. Its raw output is calibrated against the model's own observed training range (see `POST /upload/predict-all` below) to avoid wildly optimistic extrapolation.
2. **Physics-based projection** — pure sensor-trend extrapolation (`rul/physics_rul.py`), zero ML/training dependency. For each sensor with a defined risk threshold, fits a linear or exponential curve to its historical readings and projects how many days until it crosses into its worst scoring band. The soonest-crossing sensor becomes the physics estimate and is named as the "limiting sensor."

The default fleet (`/rul/predict`) only ever produces the ML estimate — physics projection is an uploaded-asset-only feature.

### Model selection logic

Rather than always averaging the two RUL estimates, `rul/consensus_rul.py`'s `select_rul()` picks a single "primary" source based on how closely they agree (`assess_consensus()`, comparing the two by ratio) and how much the physics projection can be trusted (`physics_confidence`, from sensor data volume and curve-fit quality):

| Consensus | Physics confidence | Primary source |
|---|---|---|
| Physics unavailable | — | ML |
| High (within ~30%) | any | Average of both |
| Medium (within ~60%) | high or medium | Physics |
| Medium | low | ML |
| Low (diverge significantly) | high or medium | Physics |
| Low | low | ML |

This selection (`primary_rul_days`, `primary_source`, `reason`) is what the dashboard treats as *the* RUL number everywhere — sorting, health status, the PM interval calculation, and the headline figure shown to the user — not the raw ML value. See `POST /upload/predict-all` for the exact response fields.

### Authentication

The Anthropic API key is read once at process startup from the `ANTHROPIC_API_KEY` environment variable (via `.env` and `python-dotenv`) — it is never passed as a request parameter or header on any endpoint in this API. It's required for: schema inference (`POST /upload/analyze` in training mode), RUL explanations (`POST /rul/explain`, `POST /upload/explain`), on-demand breach alerts (`POST /upload/explain-breach`), and building/rebuilding the RAG knowledge base. Endpoints that don't touch Claude (`/ahp/*`, `POST /upload/predict-all`, `POST /upload/approve-criteria`, `GET /upload/models`, `GET /upload/audit-log`, `GET /rag/documents`) work with no key configured.

### Base URL

- **Local development:** `http://localhost:8000`. The Vite dev server proxies `/ahp/*`, `/rul/*`, `/upload/*`, and `/rag/*` to this address, so the frontend can also be reached at `http://localhost:5173`.
- **Production (Railway):** the FastAPI app serves both the API and the built React frontend from a single origin — all requests use relative paths (e.g. `fetch('/upload/analyze')`), no base URL configuration needed.
- All four routers are mounted on one FastAPI app (`main.py`). There is no API versioning prefix.

---

## Data Format

`POST /upload/analyze` (and the offline `rul/dynamic_train_cli.py`) accepts a two-sheet **`.xlsx`** file only — CSV is not supported. Column names are flexible; roles are detected by keyword heuristics (`data/upload_schema.py`), not by fixed names.

### Sheet 1: `Operational Telemetry`

One row per asset per day. Sheet name must match `"Operational Telemetry"` case-insensitively (after stripping whitespace). Minimum 10 rows total.

| Role | Detection | Required | Training vs. prediction |
|---|---|---|---|
| Asset ID | first column whose name contains `"id"`; if a candidate also appears in the log sheet's columns, that one wins; falls back to the first non-numeric (`object`-dtype) column if nothing matches | Yes | Same in both modes |
| Date | first column containing `"date"`, `"time"`, `"timestamp"`, or `"datetime"` that parses as a date for ≥90% of its rows (`pd.to_datetime(..., format="mixed")`) | Yes | Same in both modes |
| RUL / remaining-life target | first **numeric** column containing `"rul"`, `"remaining"`, `"life"`, or `"ttf"` | **No — this is the training/prediction trigger** | **Present → training mode.** **Absent → prediction mode.** `rul/dynamic_train_cli.py` passes `require_rul_column=True` and hard-fails if none is found (it always trains); `POST /upload/analyze` leaves it optional |
| Operating hours | first numeric column containing `"hour"`, `"runtime"`, `"operating"`, `"cycles"`, or `"cumulative"` | Yes | Same in both modes |
| Sensor columns | every remaining numeric column not already claimed by the roles above | Minimum 2 | Same in both modes — sensor *columns* must be identical between a training file and a later prediction-mode file for the same asset type; `POST /upload/analyze`'s prediction-mode branch rejects a file whose sensor columns don't exactly match the pre-trained model's (HTTP 422) |

If any *required* role can't be detected, the upload is rejected (HTTP 422) with a message listing every column name found, so you know what to rename.

### Sheet 2: `Failure & Maintenance Logs`

One row per event. Sheet name must match `"Failure & Maintenance Logs"` case-insensitively. An empty log sheet is tolerated (reduces scoring quality) as long as the sheet itself exists with the right name.

| Role | Detection | Required |
|---|---|---|
| Asset ID | same detection as the telemetry sheet, cross-referenced against telemetry's asset ID column | Yes (if the log sheet has rows) |
| Event date | date-keyword column that parses as a date | Recommended |
| Event type | first column (in file order) containing `"event"`, `"type"`, `"status"`, or `"category"`, excluding any column whose name also contains `"date"`/`"timestamp"` | Recommended — Claude infers `failure_event_values` from this column's distinct values |
| Everything else | any remaining log columns, kept as `log_extra_columns` with up to 10 sample values each | No |

**Cross-sheet validation:** every asset ID appearing in the log sheet must also appear in the telemetry sheet — an "orphan" log asset ID fails validation (HTTP 422).

### `schema_summary` (what column detection produces)

Both `POST /upload/analyze` and the CLI compute this once and pass it to Claude for criteria inference. It's also returned directly in `/upload/analyze`'s response and echoed back to `/upload/predict-all` as `prediction_schema_summary`.

```json
{
  "asset_id_column": "Machine_ID",
  "date_column": "Timestamp",
  "rul_column": "RUL_Days",
  "has_rul_column": true,
  "operating_hours_column": "Runtime_Hours",
  "sensor_columns": ["Temp_C", "Vibration_Index"],
  "log_asset_id_column": "Machine_ID",
  "log_date_column": "Event_Timestamp",
  "log_event_type_column": "Event_Type",
  "log_extra_columns": ["Root_Cause"],
  "asset_ids": ["CONV-001", "CONV-002"],
  "row_count": 1825,
  "date_range": {"min": "2021-01-01", "max": "2025-12-31"},
  "sensor_stats": {
    "Temp_C": {"min": 45.2, "max": 98.1, "mean": 62.3, "std": 8.7, "p25": 55.0, "p75": 68.4}
  },
  "log_event_type_values": ["Failure", "Scheduled_PM"],
  "log_extra_column_samples": {"Root_Cause": ["Bearing_Wear", "Overheating"]}
}
```

When no RUL column is detected, `"rul_column": null` and `"has_rul_column": false` — this is what `POST /upload/analyze` branches on.

---

## Router Overview

| Router | Prefix | Used by dashboard UI? | Purpose |
|---|---|---|---|
| AHP | `/ahp` | No (default fleet, API-only) | Pairwise-matrix weights, C1-C5 scoring, risk ranking for the fixed 5-pump fleet |
| RUL | `/rul` | No (default fleet, API-only) | RUL prediction + Claude explanation for the fixed 5-pump fleet |
| Upload | `/upload` | Yes — the dashboard's only rendered flow | File validation, criteria inference/approval, dynamic training, scoring, RUL prediction, explanations |
| RAG | `/rag` | Yes (Knowledge Base panel) | Manage the manuals/failure-cases/criteria-configs knowledge base used by `/upload` |

---

## AHP Router (`/ahp`)

Default fleet only. All AHP math (5x5 matrix in, weights + Consistency Ratio out) is shared conceptually with the upload pipeline, but this router's endpoints operate on the hardcoded 5-criteria KSB Calio scoring rules, not an inferred `CriteriaConfig`.

### POST `/ahp/calculate-weights`

Accepts a pairwise comparison matrix (caller fills the upper triangle and diagonal; the lower-triangle reciprocals are auto-filled) and returns the derived weight vector plus consistency metrics.

**Request body**

| Field | Type | Default | Description |
|---|---|---|---|
| `matrix` | `float[n][n]` | required | Pairwise comparison matrix, diagonal `1`. `n` must be between 3 and 7, and every row must have exactly `n` elements (square) |

```json
{
  "matrix": [
    [1, 3, 5, 2, 4],
    [0.333, 1, 3, 1, 2],
    [0.2, 0.333, 1, 0.5, 1],
    [0.5, 1, 2, 1, 1.5],
    [0.25, 0.5, 1, 0.667, 1]
  ]
}
```

**Response body**

| Field | Type | Description |
|---|---|---|
| `weights` | `float[n]` | Derived weight vector, summing to 1.0 |
| `lambda_max` | `float` | Principal eigenvalue approximation |
| `ci` | `float` | Consistency Index |
| `cr` | `float` | Consistency Ratio |
| `valid` | `bool` | `true` when `cr <= 0.10` |

```json
{
  "weights": [0.418562, 0.243891, 0.097253, 0.171804, 0.06849],
  "lambda_max": 5.073021,
  "ci": 0.018255,
  "cr": 0.0163,
  "valid": true
}
```

**Errors**

| Status | Condition | Message |
|---|---|---|
| 422 | `matrix` has fewer than 3 or more than 7 rows | `"matrix must have 3–7 rows, got {n}"` |
| 422 | `matrix` is not square (a row's length ≠ row count) | `"matrix must be square ({n}×{n})"` |

---

### POST `/ahp/score-asset`

Derives the five C1-C5 Saaty scores for a single pump from its raw variables. C1 and C4 are passed straight through as manual inputs; C2, C3, and C5 are computed from condition and maintenance history fields.

**Request body**

| Field | Type | Default | Description |
|---|---|---|---|
| `asset_id` | `string` | `""` | Reference only, not used in scoring |
| `criticality_raw` | `float` | required | C1 manual input, 1-10 |
| `condition_score` | `float` | required | 1-10, from the telemetry aggregator |
| `vibration_level` | `string` | required | `"Normal"` \| `"High"` \| `"Critical"` |
| `seal_condition` | `string` | required | `"Good"` \| `"Worn"` \| `"Leaking"` |
| `bearing_condition` | `string` | required | `"Good"` \| `"Worn"` \| `"Failed"` |
| `age_years` | `float` | required | Asset age in years |
| `expected_lifespan_years` | `float` | required | Expected total lifespan in years |
| `number_of_failures_last_3yr` | `int` | required | Failure count, last 3 years |
| `days_since_maintenance` | `float` | required | Days since last maintenance event |
| `maintenance_frequency_days` | `float` | required | Recommended maintenance interval (90 for KSB Calio) |
| `downtime_impact_raw` | `float` | required | C4 manual input, 1-10 |
| `maintenance_cost_trend` | `string` | required | `"Decreasing"` \| `"Stable"` \| `"Increasing"` |
| `maintenance_cost_last_year` | `float` | required | Total repair cost, last 365 days ($) |

```json
{
  "asset_id": "KSB-CALIO-3040-1000",
  "criticality_raw": 7,
  "condition_score": 7,
  "vibration_level": "Normal",
  "seal_condition": "Good",
  "bearing_condition": "Good",
  "age_years": 1.81,
  "expected_lifespan_years": 20,
  "number_of_failures_last_3yr": 1,
  "days_since_maintenance": 45,
  "maintenance_frequency_days": 90,
  "downtime_impact_raw": 6,
  "maintenance_cost_trend": "Stable",
  "maintenance_cost_last_year": 2500
}
```

**Response body**

| Field | Type | Description |
|---|---|---|
| `score_criticality` | `float` | C1, 1-9 Saaty scale |
| `score_condition` | `float` | C2, 1-9 Saaty scale |
| `score_failure_probability` | `float` | C3, 1-9 Saaty scale |
| `score_downtime_impact` | `float` | C4, 1-9 Saaty scale |
| `score_maintenance_cost_trend` | `float` | C5, 1-9 Saaty scale |

```json
{
  "score_criticality": 6.33,
  "score_condition": 2.78,
  "score_failure_probability": 4.56,
  "score_downtime_impact": 5.44,
  "score_maintenance_cost_trend": 3.67
}
```

**Errors**

| Status | Condition | Message |
|---|---|---|
| 422 | Missing or invalid field | Pydantic validation error listing the offending field |

---

### POST `/ahp/risk-factor`

Computes the risk factor (dot product) for one pump given a weight vector and score vector — a standalone utility, separate from the full `/ahp/assets` ranking.

**Request body**

| Field | Type | Default | Description |
|---|---|---|---|
| `weights` | `float[5]` | required | AHP weight vector, must sum to ~1.0, exactly 5 elements |
| `scores` | `float[5]` | required | Per-criterion Saaty scores, exactly 5 elements |

```json
{
  "weights": [0.35, 0.25, 0.2, 0.12, 0.08],
  "scores": [6.33, 2.78, 4.56, 5.44, 3.67]
}
```

**Response body**

| Field | Type | Description |
|---|---|---|
| `risk_factor` | `float` | Scalar 1-9, dot product of weights and scores, rounded to 4 decimals |
| `weighted_scores` | `float[5]` | Per-criterion products `[w1*s1 ... w5*s5]`, each rounded to 6 decimals |

```json
{
  "risk_factor": 4.4123,
  "weighted_scores": [2.2155, 0.695, 0.912, 0.6528, 0.2936]
}
```

**Errors**

| Status | Condition | Message |
|---|---|---|
| 422 | `weights` or `scores` not exactly length 5 | `"weights and scores must each have exactly 5 elements"` |

---

### GET `/ahp/assets`

Returns all 5 default fleet pumps ranked highest to lowest by risk factor. Loads telemetry via `telemetry_aggregator.py`, scores each pump with the given weights and manual C1/C4 inputs, then ranks.

**Query parameters**

| Param | Type | Default | Description |
|---|---|---|---|
| `weights` | `float`, repeated | `[0.2, 0.2, 0.2, 0.2, 0.2]` | AHP weight vector; must be exactly 5 values if provided |
| `c1_score` | `int` | `7` | Criticality manual input, 1-10 |
| `c4_score` | `int` | `6` | Downtime Impact manual input, 1-10 |

```
GET /ahp/assets?weights=0.35&weights=0.25&weights=0.2&weights=0.12&weights=0.08&c1_score=7&c4_score=6
```

**Response body**

Array of pump result objects, sorted descending by `risk_factor`. Each includes every aggregator output field (see CLAUDE.md "Aggregator Output Format") plus:

| Field | Type | Description |
|---|---|---|
| `risk_factor` | `float` | Scalar 1-9 |
| `weights` | `float[5]` | Weight vector used for this ranking |
| `scores` | `float[5]` | Saaty score vector `[s1-s5]` |
| `weighted_scores` | `float[5]` | Per-criterion products |
| `criteria` | `string[5]` | `["Criticality", "Condition", "Failure Probability", "Downtime Impact", "Maintenance Cost Trend"]` |

```json
[
  {
    "asset_id": "KSB-CALIO-3040-1000",
    "asset_name": "KSB Calio 3040 - Unit 1000",
    "risk_factor": 4.41,
    "weights": [0.35, 0.25, 0.2, 0.12, 0.08],
    "scores": [6.33, 2.78, 4.56, 5.44, 3.67],
    "weighted_scores": [2.2155, 0.695, 0.912, 0.6528, 0.2936],
    "criteria": ["Criticality", "Condition", "Failure Probability", "Downtime Impact", "Maintenance Cost Trend"],
    "condition_score": 7,
    "vibration_level": "Normal"
  }
]
```

**Errors**

| Status | Condition | Message |
|---|---|---|
| 400 | `weights` does not contain exactly 5 values | `"Expected 5 weights, got {n}."` |

---

## RUL Router (`/rul`)

Default fleet only. Both endpoints are guarded by the AHP Consistency Ratio.

### POST `/rul/predict`

Builds the 24-feature vector for the default fleet model, predicts RUL in years, and applies the AHP risk adjustment (`rul_adjusted = rul_raw * (1 - (risk_factor - 1) / 8)`).

**Request body**

| Field | Type | Default | Description |
|---|---|---|---|
| `pump` | `object` | required | Full pump dict (aggregator output format) |
| `weights` | `float[5]` | required | AHP weight vector |
| `scores` | `float[5]` | required | Per-criterion Saaty scores |
| `cr` | `float` | required | Current Consistency Ratio |

```json
{
  "pump": {"asset_id": "KSB-CALIO-3040-1000", "total_runtime_hours": 14500.0},
  "weights": [0.35, 0.25, 0.2, 0.12, 0.08],
  "scores": [6.33, 4.56, 5.44, 5.44, 3.67],
  "cr": 0.07
}
```

**Response body**

| Field | Type | Description |
|---|---|---|
| `asset_id` | `string` | Echoed from `pump.asset_id` (`""` if absent) |
| `rul_years` | `float` | Predicted remaining useful life, risk-adjusted |
| `ci_low` | `float` | Confidence interval lower bound (years) |
| `ci_high` | `float` | Confidence interval upper bound (years) |

```json
{
  "asset_id": "KSB-CALIO-3040-1000",
  "rul_years": 3.82,
  "ci_low": 2.91,
  "ci_high": 4.73
}
```

**Errors**

| Status | Condition | Message |
|---|---|---|
| 400 | `cr > 0.10` | `"AHP matrix is inconsistent (CR > 0.10). Revise pairwise comparisons before requesting RUL predictions."` |
| 422 | `weights` or `scores` not length 5 | `"must have exactly 5 elements"` |
| 422 | `pump` missing a field required to build the feature vector | Text from `build_feature_vector` (`KeyError`/`ValueError`) |
| 422 | Feature vector fails shape/range validation | Text from `validate_feature_vector` |
| 503 | Model file (`rul/model.pkl`) not found or fails to load | Text from `predict_adjusted` (`RuntimeError`) |

---

### POST `/rul/explain`

Calls Claude to generate a maintenance assessment for a default-fleet RUL prediction. Internally this now calls the same `rul_explainer.explain()` used by `/upload/explain` (see that endpoint and CLAUDE.md's "GenAI Explainability" for the full prompt structure) — but since this endpoint only supplies `pump`/`weights`/`scores`/`risk_factor`/`predicted_rul`/`ci_low`/`ci_high` (no breach list, no physics projection, no per-sensor threshold data), the assessment's THRESHOLD BREACHES and physics-related sentences fall back to generic "no data" phrasing rather than the richer detail an uploaded asset gets.

**Request body**

| Field | Type | Default | Description |
|---|---|---|---|
| `pump` | `object` | required | Full pump dict |
| `weights` | `float[5]` | required | AHP weight vector |
| `scores` | `float[5]` | required | Per-criterion Saaty scores |
| `risk_factor` | `float` | required | Overall risk factor, 1-9 |
| `predicted_rul` | `float` | required | Predicted RUL in years |
| `ci_low` | `float` | required | Confidence interval lower bound (years) |
| `ci_high` | `float` | required | Confidence interval upper bound (years) |
| `cr` | `float` | required | Current Consistency Ratio |

```json
{
  "pump": {"asset_id": "KSB-CALIO-3040-1000"},
  "weights": [0.35, 0.25, 0.2, 0.12, 0.08],
  "scores": [6.33, 2.78, 4.56, 5.44, 3.67],
  "risk_factor": 5.2,
  "predicted_rul": 4.7,
  "ci_low": 3.2,
  "ci_high": 6.2,
  "cr": 0.07
}
```

**Response body**

| Field | Type | Description |
|---|---|---|
| `asset_id` | `string` | Echoed from `pump.asset_id` |
| `explanation` | `string` | An exact 5-sentence, data-driven assessment: current condition, root cause, breach details (or trending-sensor note if none), RUL interpretation, specific action |

```json
{
  "asset_id": "KSB-CALIO-3040-1000",
  "explanation": "This pump reads a risk factor of 5.20/9.0 with Condition as the primary concern... [5 sentences total]"
}
```

**Errors**

| Status | Condition | Message |
|---|---|---|
| 400 | `cr > 0.10` | `"AHP matrix is inconsistent (CR > 0.10). Revise pairwise comparisons before requesting RUL predictions."` |
| 422 | `weights` or `scores` not length 5 | `"must have exactly 5 elements"` |
| 502 | Anthropic API call fails | Text from `explain` (`RuntimeError`, e.g. `"Anthropic API call failed: ..."`) |

---

## Upload Router (`/upload`)

The dashboard's only rendered flow. Handles the full pipeline for an arbitrary uploaded asset type: file validation, Claude-driven criteria inference (RAG-enriched), training-or-prediction branching, SME approval, scoring, RUL prediction, and explanations.

### POST `/upload/analyze`

Accepts a two-sheet Excel file upload, validates it, infers a draft `CriteriaConfig` (or reuses a pre-trained model's approved one), and scores every detected asset — **without RUL**; RUL requires a separate `POST /upload/predict-all` call once the criteria have been approved.

Branches immediately on `schema_summary["has_rul_column"]` (see Data Format). This is the endpoint where training mode and prediction mode diverge.

**Request**

`multipart/form-data` with a single field:

| Field | Type | Description |
|---|---|---|
| `file` | file (`.xlsx`) | Two-sheet Excel file: `Operational Telemetry` + `Failure & Maintenance Logs` |

#### Training mode response (`has_rul_column: true` — file has a labeled RUL target column)

Calls Claude to infer a `CriteriaConfig` (RAG-enriched), stores the draft, trains a fresh XGBoost model on this file (`bundle["approved"] = False`), saves it to `rul/models/<sanitized_asset_type>.pkl`, and auto-generates a failure-case markdown document.

| Field | Type | Description |
|---|---|---|
| `mode` | `string` | Always `"training"` |
| `criteria_config` | `object` | Claude's draft `CriteriaConfig` (see CLAUDE.md "CriteriaConfig Schema") |
| `schema_summary` | `object` | See Data Format above |
| `training_result` | `object` | `{train_rmse, test_rmse, n_train_samples, n_test_samples}` (all RMSE in years) |
| `assets` | `array` | One entry per detected asset (see "Asset entry shape" below); `rul_years`/`rul_months` are `null` here |
| `model_path` | `string` | Where the newly trained model bundle was saved, e.g. `rul/models/industrial_conveyor_motor.pkl` |

No `criteria_source` field is present in the training-mode response — it is only set on the prediction-mode branch (see below).

```json
{
  "mode": "training",
  "criteria_config": {
    "asset_type": "Industrial Conveyor Motor",
    "failure_modes": ["Bearing wear", "Belt slippage", "Motor overheating"],
    "column_roles": {"asset_id": "Machine_ID", "date": "Timestamp", "rul_target": "RUL_Days", "operating_hours": "Runtime_Hours"},
    "recommended_pm_interval_days": 90,
    "pm_interval_source": "inferred_from_log",
    "pm_interval_confidence": "medium",
    "criteria": [{"id": "C1", "name": "Criticality", "manual_input": true, "default_score": 7}]
  },
  "schema_summary": {"asset_id_column": "Machine_ID", "sensor_columns": ["Temp_C", "Vibration_Index"], "row_count": 1825},
  "training_result": {"train_rmse": 0.4123, "test_rmse": 0.5871, "n_train_samples": 1460, "n_test_samples": 365},
  "assets": [
    {
      "asset_id": "CONV-001",
      "snapshot_date": "2026-06-20",
      "scores": {"C1": 6.33, "C2": 2.78},
      "raw_scores": {"C1": 7, "C2": 3},
      "rul_years": null,
      "rul_months": null,
      "Temp_C": 78.4
    }
  ],
  "model_path": "rul/models/industrial_conveyor_motor.pkl"
}
```

#### Prediction mode response (`has_rul_column: false` — current telemetry, no known outcome)

Never trains. Looks up an already-trained model for this asset type via `model_registry.find_model()` — exact case-insensitive match on inferred asset type first, then most-word-overlap match, then (only if there is exactly one model in the whole registry) that single model as a last resort. Uses that model's own **approved** `CriteriaConfig` directly (not a fresh Claude inference) so the feature vector always matches what the model was trained on, and requires this upload's sensor columns to exactly match the model's.

| Field | Type | Description |
|---|---|---|
| `mode` | `string` | Always `"prediction"` |
| `criteria_config` | `object` | The **pre-trained model's own** approved `CriteriaConfig` — not freshly inferred |
| `criteria_source` | `string` | Always `"pre_trained_model"` on this branch |
| `schema_summary` | `object` | This upload's own detected schema |
| `prediction_schema_summary` | `object` | Identical to `schema_summary` — returned under this explicit key so the client can round-trip it, unambiguously, into `POST /upload/predict-all` |
| `training_result` | `null` | Always `null` — no training happens |
| `assets` | `array` | One entry per detected asset, scored but not RUL-predicted (see "Asset entry shape" below) |
| `model_path` | `string` | Resolved path to the pre-trained model bundle |
| `model_used` | `string` | Same value as `model_path` |
| `model_asset_type` | `string` | The pre-trained model's own `asset_type` |
| `feature_count` | `int` | Length of the pre-trained model's feature vector |

```json
{
  "mode": "prediction",
  "criteria_config": {"asset_type": "Centrifugal Pump", "criteria": []},
  "criteria_source": "pre_trained_model",
  "schema_summary": {},
  "prediction_schema_summary": {},
  "training_result": null,
  "assets": [],
  "model_path": "rul/models/centrifugal_pump.pkl",
  "model_used": "rul/models/centrifugal_pump.pkl",
  "model_asset_type": "Centrifugal Pump",
  "feature_count": 47
}
```

#### Asset entry shape (both modes)

| Field | Type | Description |
|---|---|---|
| `asset_id` | `string` | Asset identifier |
| `snapshot_date` | `string` | ISO date of the snapshot row — **most recent row** in prediction mode, a 50-90% lifecycle-spread row in training mode (see CLAUDE.md `dynamic_aggregator.py`) |
| `scores` | `object` | Saaty scores keyed by criterion ID, e.g. `{"C1": 6.33, "C2": 2.78, ...}` |
| `raw_scores` | `object` | Raw 1-10 scores keyed by criterion ID, pre-Saaty-conversion |
| `rul_years` | `null` | Always `null` at this stage |
| `rul_months` | `null` | Always `null` at this stage |
| ...everything else | varies | Every remaining snapshot field: raw sensor values, `rolling_{col}_mean`/`rolling_{col}_std`, `trend_{col}`, `corr_*`/`interaction_*`/`alignment_*` pair features, `composite_stress_index`, `physics_projection`, `failures_last_90_days`, `days_since_last_event`, `total_failure_count`, `total_runtime_hours`, keyed by actual column names from the upload |

**Errors**

| Status | Condition | Message |
|---|---|---|
| 422 | File fails the two-sheet contract, column detection, or row-count minimum | Text from `validate_upload` (`UploadValidationError`) |
| 422 | Prediction mode: no pre-trained model exists for the inferred asset type | `"No pre-trained model found. Train a model first using:\npython -m rul.dynamic_train_cli --file <historical_data.xlsx>"` |
| 422 | Prediction mode: this file's sensor columns don't exactly match the pre-trained model's | `"Uploaded file sensor columns do not match pre-trained model.\nModel expects: [...]\nFile has: [...]"` |
| 422 | Training mode: Claude returns invalid JSON, hallucinated column names, or fails validation | Text from `infer_criteria_config` (`RuntimeError`) |
| 422 | Training mode: model training fails (insufficient rows, invalid target column, etc.) | Text from `train_dynamic_model` (`ValueError`/`RuntimeError`) |
| 422 | Snapshot aggregation fails (either mode) | Exception text from `aggregate_uploaded_data` |
| 422 | Per-asset scoring fails (either mode) | Exception text from `score_asset_dynamic` |

RAG retrieval failures and `CriteriaConfig` storage failures never surface as errors here — both degrade silently (RAG returns `retrieval_available: false`; storage failures are caught and ignored).

---

### POST `/upload/approve-criteria`

A human reviews and optionally edits Claude's draft `CriteriaConfig` (or re-edits an already-approved one), then locks it in. This is the gate: nothing downstream treats a `CriteriaConfig` as authoritative until it's been through this endpoint at least once for its model bundle.

**Request body**

| Field | Type | Default | Description |
|---|---|---|---|
| `criteria_config` | `object` | required | The (possibly SME-edited) `CriteriaConfig` to approve |
| `model_path` | `string` | `"rul/dynamic_model.pkl"` | Path to the model bundle this approval applies to |
| `file_path` | `string \| null` | `null` | Path to the uploaded file, recorded in the audit log entry |
| `previous_config` | `object \| null` | `null` | The client's last-approved config, if this is a re-approval — the diff/change-count is computed against this instead of the bundle's stored config, so it reflects only what changed *this round*. Omit or `null` on a first approval |
| `approved_pm_interval_days` | `int \| null` | `null` | SME-edited PM interval, 7-730. Outside that range (or omitted) leaves the bundle's existing PM interval state untouched — never overwritten with an invalid value |

```json
{
  "criteria_config": {"asset_type": "Industrial Conveyor Motor", "criteria": []},
  "model_path": "rul/models/industrial_conveyor_motor.pkl",
  "file_path": "data/raw/uploads/conveyor_data.xlsx",
  "previous_config": null,
  "approved_pm_interval_days": 60
}
```

**Validation applied to `criteria_config`:** 3-7 criteria; every criterion has non-empty `id`/`name`/`description`/`manual_input`; every non-manual criterion has a `primary_column` that exists in the bundle's `schema_summary["sensor_columns"]`, plus at least 2 `thresholds`; every threshold's `score` is a number between 1 and 10. `primary_column` and `secondary_columns` cannot be changed to anything not already in the original schema — sensor assignments are load-bearing for the already-trained model.

**Response body**

| Field | Type | Description |
|---|---|---|
| `status` | `string` | Always `"approved"` on success |
| `criteria_config` | `object` | Echoed back |
| `changes_from_original` | `int` | Count of changed fields (`name`/`thresholds`/`default_score`/`penalties` per criterion) vs. `previous_config` or the bundle's prior config |
| `approved_pm_interval_days` | `int \| null` | Whatever actually ended up stored on the bundle — `null` if never set or this call's value was invalid, not just an echo of the request |
| `approved_at` | `string` | UTC timestamp the approval was logged under (empty string if audit logging itself failed — logging never blocks the approval) |

```json
{
  "status": "approved",
  "criteria_config": {"asset_type": "Industrial Conveyor Motor", "criteria": []},
  "changes_from_original": 2,
  "approved_pm_interval_days": 60,
  "approved_at": "2026-07-16T21:47:38"
}
```

On success this also: overwrites `bundle["criteria_config"]` and sets `bundle["approved"] = True` in the model bundle on disk; re-stores the approved config as a new versioned file in `rag/stored_configs/` (never overwriting a prior version); and appends a draft-vs-approved diff entry to `docs/audit_log.jsonl` (see `GET /upload/audit-log`).

**Errors**

| Status | Condition | Message |
|---|---|---|
| 404 | `model_path` does not exist | `"Model not found at '{model_path}'."` |
| 422 | `criteria_config` fails validation | Specific message naming the criterion/field (wrong criteria count, missing field, unknown `primary_column`, too few thresholds, out-of-range score) |
| 422 | Any other unexpected failure during the approval | Generic exception text |

---

### POST `/upload/predict-all`

Re-scores every asset from a previously uploaded file using the caller's current AHP weights/manual scores, and predicts RUL for each. This is where the two-model RUL system, threshold breach detection, and maintenance planning all run — the richest endpoint in the API. Requires the model bundle's criteria to have been approved at least once (see `POST /upload/approve-criteria`); once approved, weight-only re-runs don't need a full re-approval cycle.

**Request body**

| Field | Type | Default | Description |
|---|---|---|---|
| `file_path` | `string` | required | Path to the file being scored, e.g. `data/raw/uploads/file.xlsx` — not necessarily the file the model was trained on |
| `weights` | `float[3-7]` | required | AHP weight vector; length must equal the number of criteria in the active `CriteriaConfig` |
| `cr` | `float` | required | Current Consistency Ratio |
| `manual_scores` | `object` | required | Manual scores keyed by criterion ID, e.g. `{"C1": 7, "C4": 6}` |
| `model_path` | `string` | `"rul/dynamic_model.pkl"` | Path to the trained model bundle |
| `approved_criteria_config` | `object \| null` | `null` | The client's current approved config. When present, used directly (re-validated server-side) — lets weight-only re-runs skip a full re-approval. When omitted, falls back to `bundle["criteria_config"]` and requires `bundle["approved"] == true` (HTTP 400 otherwise) |
| `prediction_schema_summary` | `object \| null` | `null` | This file's own detected schema (from `/upload/analyze`'s response). Used for every column-name lookup instead of the bundle's training-file schema, since a later prediction-mode file isn't guaranteed to share the training file's exact column names. Falls back to `bundle["schema_summary"]` when omitted |

```json
{
  "file_path": "data/raw/uploads/conveyor_data.xlsx",
  "weights": [0.35, 0.25, 0.2, 0.12, 0.08],
  "cr": 0.07,
  "manual_scores": {"C1": 7, "C4": 6},
  "model_path": "rul/models/industrial_conveyor_motor.pkl",
  "approved_criteria_config": null,
  "prediction_schema_summary": null
}
```

**Response body**

`{"assets": [...]}` — one entry per asset, sorted descending by `risk_factor`.

| Field | Type | Description |
|---|---|---|
| `asset_id` | `string` | Asset identifier |
| `snapshot_date` | `string` | Date of the snapshot row scored |
| `scores` | `object` | Saaty scores keyed by criterion ID |
| `raw_scores` | `object` | Raw 1-10 scores keyed by criterion ID |
| `risk_factor` | `float` | Scalar risk factor, rounded to 4 decimals |
| `weighted_scores` | `float[]` | Per-criterion weighted products |
| `rul_years` | `float` | Raw ML prediction, AHP-risk-adjusted, in years |
| `rul_months` | `float` | `rul_years * 12`, rounded to 1 decimal |
| `rul_raw_days` | `int` | The pre-calibration ML prediction, in days |
| `rul_calibrated` | `bool` | Whether the ML output was pulled back toward the model's observed training range |
| `ci_low` / `ci_high` | `float` | ML model's own confidence interval bounds, in years (fixed ±0.5 year half-width) |
| `ci_low_months` / `ci_high_months` | `float` | Same bounds in months |
| `correlation_summary` | `object` | `{composite_stress_index, top_correlated_pairs, sensors_degrading_together}` — see below |
| `breaches` | `array` | Threshold breaches detected on this snapshot (deterministic, no API call) — see below |
| `breach_summary` | `object` | `{total_breaches, high_severity, medium_severity, low_severity, most_severe_criterion, alert_required}` |
| `mtbf` | `object` | `{mtbf_days, mtbf_confidence, mtbf_note, basis}` — see below |
| `mtbm` | `object` | `{mtbm_recommended_days, current_interval_days, recommendation, recommendation_text, next_maintenance_date, basis, rul_days_used}` — see below |
| `replace_vs_maintain` | `object` | `{decision, rationale, annual_maintenance_cost, estimated_replacement_cost, replacement_cost_estimated, years_until_economic_end_of_life}` |
| `physics_projection` | `object` | `{physics_rul_days, limiting_sensor, limiting_sensor_projected_date, sensor_projections, consensus_with_ml, confidence}` — see below |
| `consensus` | `string` | `"high"` \| `"medium"` \| `"low"` \| `"unknown"` — how closely ML and physics agree |
| `physics_confidence` | `string` | `"high"` \| `"medium"` \| `"low"` — physics projection's own data-quality confidence |
| `rul_days` | `int` | **The primary/selected RUL in days — the headline number, not `rul_years * 365`** |
| `rul_primary_source` | `string` | `"ml"` \| `"physics"` \| `"average"` |
| `rul_ml_days` | `int` | The ML estimate alone, in days |
| `rul_physics_days` | `int \| null` | The physics estimate alone, in days |
| `rul_reason` | `string` | Human-readable reason `select_rul()` picked this source |
| ...everything else | varies | Every remaining snapshot field (raw sensor values, rolling stats, trend/correlation features, `total_runtime_hours`, etc.) |

**`breaches[]` entry:**

| Field | Type | Description |
|---|---|---|
| `criterion_id` | `string` | e.g. `"C2"` |
| `criterion_name` | `string` | e.g. `"Bearing Condition"` |
| `column` | `string` | The sensor column that breached |
| `current_value` | `float` | The value that triggered the breach |
| `threshold_max` | `float` | The safe/risk boundary that was crossed |
| `exceeded_by` | `float` | `current_value - threshold_max` |
| `exceeded_pct` | `float` | `exceeded_by / threshold_max` |
| `severity` | `string` | `"low"` (<10% over) \| `"medium"` (10-25%) \| `"high"` (>25%) |
| `breach_type` | `string` | `"primary"` (a criterion's own `thresholds`) or `"penalty"` (a `penalties[].bands` breach) |

**`mtbm.basis` values:** `"rul_based"` (primary — 75% of this asset's own predicted RUL, whenever `rul_days` is available), `"mtbf_based"` (fallback — 60% of observed MTBF, risk-adjusted), `"risk_adjusted"` (last-resort fallback — a risk-only adjustment of the current interval, used when neither RUL nor MTBF is available). `rul_days_used` echoes the RUL value used in the `rul_based` case, `null` otherwise.

**`physics_projection.sensor_projections["<sensor>"]` entry:** `{days_to_threshold, current_value, threshold, trend_direction, trend_rate, fit_method, fit_quality, already_breached, projected_date}`.

```json
{
  "assets": [
    {
      "asset_id": "CONV-001",
      "snapshot_date": "2026-06-20",
      "scores": {"C1": 6.33, "C2": 2.78},
      "raw_scores": {"C1": 7, "C2": 3},
      "risk_factor": 4.4123,
      "weighted_scores": [2.2155, 0.695],
      "rul_years": 0.34,
      "rul_months": 4.1,
      "rul_raw_days": 145,
      "rul_calibrated": false,
      "ci_low": 0.0,
      "ci_high": 0.84,
      "ci_low_months": 0.0,
      "ci_high_months": 10.1,
      "correlation_summary": {"composite_stress_index": 0.42, "top_correlated_pairs": [], "sensors_degrading_together": 1},
      "breaches": [
        {"criterion_id": "C2", "criterion_name": "Bearing Condition", "column": "Vibration_Index",
         "current_value": 3.1, "threshold_max": 2.5, "exceeded_by": 0.6, "exceeded_pct": 0.24, "severity": "medium", "breach_type": "primary"}
      ],
      "breach_summary": {"total_breaches": 1, "high_severity": 0, "medium_severity": 1, "low_severity": 0, "most_severe_criterion": "Bearing Condition", "alert_required": false},
      "mtbf": {"mtbf_days": null, "mtbf_confidence": "low", "mtbf_note": "Insufficient failure history -- MTBF unavailable", "basis": "insufficient_data"},
      "mtbm": {"mtbm_recommended_days": 109, "current_interval_days": 90, "recommendation": "extend",
        "recommendation_text": "PM interval can be extended to 109 days based on predicted RUL of 145 days.",
        "next_maintenance_date": "2026-10-13", "basis": "rul_based", "rul_days_used": 145},
      "replace_vs_maintain": {"decision": "insufficient_data", "rationale": "Insufficient failure history for cost analysis",
        "annual_maintenance_cost": 0, "estimated_replacement_cost": 50000.0, "replacement_cost_estimated": true, "years_until_economic_end_of_life": null},
      "physics_projection": {"physics_rul_days": 138.0, "limiting_sensor": "Vibration_Index",
        "limiting_sensor_projected_date": "2026-11-05", "sensor_projections": {}, "consensus_with_ml": "high", "confidence": "medium"},
      "consensus": "high",
      "physics_confidence": "medium",
      "rul_days": 142,
      "rul_primary_source": "average",
      "rul_ml_days": 145,
      "rul_physics_days": 138,
      "rul_reason": "Both models agree -- average of both used"
    }
  ]
}
```

**Errors**

| Status | Condition | Message |
|---|---|---|
| 400 | `cr > 0.10` | `"AHP matrix is inconsistent (CR > 0.10). Revise pairwise comparisons."` |
| 400 | `approved_criteria_config` omitted and the bundle has never been approved | `"Criteria have not been approved. Complete the review step before running predictions."` |
| 404 | `model_path` does not exist | `"Model not found at '{model_path}'."` |
| 422 | `weights` not 3-7 elements | `"weights must have 3-7 elements"` |
| 422 | `approved_criteria_config` fails validation | Same messages as `POST /upload/approve-criteria` |
| 422 | Snapshot aggregation fails | Exception text from `aggregate_uploaded_data` — often a raw `KeyError` if `prediction_schema_summary` doesn't match the file at `file_path` |
| 422 | Feature vector construction or prediction fails | Text from `predict_adjusted_dynamic` (`FileNotFoundError`/`ValueError`) |

---

### POST `/upload/explain`

Calls Claude to generate the same exact-5-sentence, data-driven maintenance assessment described in "The two-model RUL system" and the RUL Router's `/rul/explain` above — but for an uploaded asset, with the full breach list, physics projection, and per-sensor thresholds available.

**Request body**

| Field | Type | Default | Description |
|---|---|---|---|
| `pump` | `object` | required | The full asset result object from `POST /upload/predict-all` (not a bare snapshot) — must carry `rul_days`/`rul_ml_days`/`rul_physics_days`/`consensus`/`rul_primary_source`/`breaches`/`mtbm`/`scores`/the raw sensor and `rolling_{col}_mean` columns |
| `weights` | `float[3-7]` | required | Current AHP weight vector |
| `scores` | `float[3-7]` | required | Current per-criterion Saaty scores |
| `risk_factor` | `float` | required | Overall risk factor |
| `predicted_rul` | `float` | required | Predicted RUL in years (legacy field, not used by the current prompt builder) |
| `ci_low` | `float` | required | Legacy field, not used by the current prompt builder |
| `ci_high` | `float` | required | Legacy field, not used by the current prompt builder |
| `cr` | `float` | required | Current Consistency Ratio |
| `asset_type` | `string` | `"KSB Calio 30-40"` | Inferred asset type from `CriteriaConfig` |
| `failure_modes` | `string[] \| null` | `null` | Inferred failure modes from `CriteriaConfig` |
| `sensor_context` | `object \| null` | `null` | Unused by the current prompt builder — kept for backward compatibility |
| `criteria_config` | `object \| null` | `null` | The frontend's currently-approved `CriteriaConfig`, sent alongside `pump` — used to map `pump["scores"]`'s `"C1"`/`"C2"` ids to criterion names and to derive each sensor's warning/critical thresholds |

```json
{
  "pump": {"asset_id": "CONV-001", "rul_days": 142, "rul_ml_days": 145, "rul_physics_days": 138, "consensus": "high", "breaches": []},
  "weights": [0.35, 0.25, 0.2, 0.12, 0.08],
  "scores": [6.33, 2.78, 4.56, 5.44, 3.67],
  "risk_factor": 5.2,
  "predicted_rul": 4.7,
  "ci_low": 3.2,
  "ci_high": 6.2,
  "cr": 0.07,
  "asset_type": "Industrial Conveyor Motor",
  "failure_modes": ["Bearing wear", "Belt slippage"],
  "criteria_config": {"asset_type": "Industrial Conveyor Motor", "criteria": []}
}
```

**Response body**

| Field | Type | Description |
|---|---|---|
| `asset_id` | `string` | Echoed from `pump.asset_id` |
| `explanation` | `string` | Exact 5-sentence assessment: current condition, root cause, breach details, RUL interpretation, specific action (with an actual date) |

```json
{
  "asset_id": "CONV-001",
  "explanation": "This conveyor motor reads a risk factor of 5.20/9.0, with Vibration_Index at 3.10 (24% above the 2.50 threshold) as the most concerning reading... [5 sentences total]"
}
```

**Errors**

| Status | Condition | Message |
|---|---|---|
| 400 | `cr > 0.10` | `"AHP matrix is inconsistent (CR > 0.10). Revise pairwise comparisons."` |
| 422 | `weights` or `scores` not 3-7 elements | `"must have 3-7 elements"` |
| 502 | Anthropic API call fails | Text from `explain` (`RuntimeError`) |

RAG retrieval failures never surface as an error — `retrieve_for_explanation` catches them internally and the assessment proceeds without retrieved context.

---

### POST `/upload/explain-breach`

On-demand Claude alerts for an asset's high/medium-severity threshold breaches. Separate from `/upload/explain`; only called when the user clicks "Breach Alerts" in the dashboard.

**Request body**

| Field | Type | Default | Description |
|---|---|---|---|
| `asset_snapshot` | `object` | required | The asset result object (from `/upload/predict-all`) whose breaches are being explained |
| `breaches` | `array` | required | The breach list to explain (typically `asset_snapshot.breaches`) |
| `criteria_config` | `object \| null` | `null` | Used to look up criterion descriptions/failure modes; loaded from the model bundle if omitted |
| `model_path` | `string` | `"rul/dynamic_model.pkl"` | Only used to load `criteria_config` when it's omitted from the request |
| `cr` | `float` | `0.0` | Current Consistency Ratio |

```json
{
  "asset_snapshot": {"asset_id": "CONV-001", "risk_factor": 5.2},
  "breaches": [
    {"criterion_id": "C2", "criterion_name": "Bearing Condition", "column": "Vibration_Index",
     "current_value": 3.1, "threshold_max": 2.5, "exceeded_pct": 0.24, "severity": "medium"}
  ],
  "criteria_config": null,
  "model_path": "rul/models/industrial_conveyor_motor.pkl",
  "cr": 0.0
}
```

**Response body**

| Field | Type | Description |
|---|---|---|
| `asset_id` | `string` | Echoed from `asset_snapshot.asset_id` |
| `breach_alerts` | `array` | One entry per breach with `severity` in `("high", "medium")` — low-severity breaches produce no alert |

Each `breach_alerts[]` entry: `{criterion_id, criterion_name, column, severity, alert_text}` — `alert_text` is a 2-3 sentence Claude-generated explanation, or a deterministic fallback string (`"{column} has exceeded its threshold by {N}%. Immediate inspection recommended."`) if the Anthropic call fails.

```json
{
  "asset_id": "CONV-001",
  "breach_alerts": [
    {"criterion_id": "C2", "criterion_name": "Bearing Condition", "column": "Vibration_Index",
     "severity": "medium", "alert_text": "The Vibration_Index reading of 3.1 exceeds the 2.5 threshold by 24%, indicating early-stage bearing wear..."}
  ]
}
```

**Errors**

| Status | Condition | Message |
|---|---|---|
| 400 | `cr > 0.10` | `"AHP matrix is inconsistent (CR > 0.10). Revise pairwise comparisons."` |
| 404 | `criteria_config` omitted and `model_path` doesn't exist | `"Model not found at '{model_path}'."` |

This endpoint never raises on an individual Anthropic API failure — `explain_breach()` catches it per-breach and substitutes the deterministic fallback text.

---

### GET `/upload/audit-log`

Returns the full approval audit trail — every draft-vs-approved diff, across every upload, ever.

**Request:** none.

**Response body**

| Field | Type | Description |
|---|---|---|
| `entries` | `array` | Every logged approval, oldest to newest (append-only log) |
| `total_entries` | `int` | `len(entries)` |

Each `entries[]` item: `{timestamp, config_filename, file_path, asset_type, changes_from_claude, original_criteria, approved_criteria, diff}`. `original_criteria`/`approved_criteria` are each criterion reduced to `{id, name, thresholds, default_score}`. `diff` is a list of `{criterion_id, field, claude_value, approved_value}` — one entry per changed field (`name`/`thresholds`/`default_score`/`penalties`) per criterion.

```json
{
  "entries": [
    {
      "timestamp": "2026-07-16T21:47:38",
      "config_filename": "Industrial_Conveyor_Motor_20260716_214738.json",
      "file_path": "data/raw/uploads/conveyor_data.xlsx",
      "asset_type": "Industrial Conveyor Motor",
      "changes_from_claude": 2,
      "original_criteria": [{"id": "C2", "name": "Bearing Condition", "thresholds": [], "default_score": null}],
      "approved_criteria": [{"id": "C2", "name": "Bearing Health", "thresholds": [], "default_score": null}],
      "diff": [{"criterion_id": "C2", "field": "name", "claude_value": "Bearing Condition", "approved_value": "Bearing Health"}]
    }
  ],
  "total_entries": 1
}
```

**Errors:** none — returns `{"entries": [], "total_entries": 0}` if the log file doesn't exist yet.

---

### GET `/upload/models`

Lists every pre-trained dynamic model available in the registry (`rul/models/`).

**Request:** none.

**Response body**

| Field | Type | Description |
|---|---|---|
| `models` | `array` | One entry per `.pkl` file in `rul/models/` that loads successfully (corrupted/mid-write files are silently skipped) |

Each `models[]` entry: `{asset_type, filename, model_path, trained_at, feature_count}` — `trained_at` is the file's modification time as an ISO-8601 UTC timestamp; `feature_count` is the length of that model's stored feature vector.

```json
{
  "models": [
    {"asset_type": "KSB Calio Centrifugal Pump", "filename": "ksb_calio_centrifugal_pump.pkl",
     "model_path": "rul/models/ksb_calio_centrifugal_pump.pkl", "trained_at": "2026-07-21T14:23:11+00:00", "feature_count": 47}
  ]
}
```

**Errors:** none — returns `{"models": []}` if `rul/models/` doesn't exist yet.

---

## RAG Router (`/rag`)

Manages the knowledge base backing schema inference (`/upload/analyze` training mode) and explanations (`/upload/explain`, `/upload/explain-breach`, `/rul/explain`). Entirely optional — every RAG-dependent code path degrades gracefully when the knowledge base is missing or empty.

### POST `/rag/upload-document`

Uploads a PDF manual, saves it to `docs/manuals/`, and ingests it into the ChromaDB vector store.

**Request**

`multipart/form-data` with a single field:

| Field | Type | Description |
|---|---|---|
| `file` | file | Must have a `.pdf` extension (case-insensitive) |

**Response body**

| Field | Type | Description |
|---|---|---|
| `filename` | `string` | The uploaded file's name |
| `status` | `string` | Always `"ingested"` on success |
| `message` | `string` | Human-readable confirmation |

```json
{
  "filename": "ksb_manual.pdf",
  "status": "ingested",
  "message": "'ksb_manual.pdf' ingested and added to knowledge base."
}
```

**Errors**

| Status | Condition | Message |
|---|---|---|
| 422 | File doesn't have a `.pdf` extension | `"Only PDF files are accepted."` |
| 422 | Save or ingestion fails for any other reason | Exception text (the partially-written file is deleted before the error is raised) |

---

### GET `/rag/documents`

Lists every ingested document across all three categories.

**Request:** none.

**Response body**

| Field | Type | Description |
|---|---|---|
| `manuals` | `string[]` | Filenames in `docs/manuals/`, sorted alphabetically |
| `failure_cases` | `string[]` | Filenames in `docs/failure_cases/`, sorted alphabetically |
| `criteria_configs` | `string[]` | Filenames in `rag/stored_configs/`, sorted **newest-first** by the timestamp embedded in each filename (legacy files without a timestamp suffix sort to the bottom) |
| `latest_per_asset_type` | `object` | Maps each config's actual `asset_type` (read from the file's JSON content, not the filename) to its newest filename |

```json
{
  "manuals": ["ksb_manual.pdf"],
  "failure_cases": ["pump_20260630.md"],
  "criteria_configs": ["KSB_Calio_Pump_20260705_120000.json", "KSB_Calio_Pump_20260701_100000.json"],
  "latest_per_asset_type": {"KSB Calio Pump": "KSB_Calio_Pump_20260705_120000.json"}
}
```

**Errors:** none — missing directories are treated as empty lists.

---

### DELETE `/rag/document`

Deletes a single document and rebuilds the knowledge base to purge its stale embeddings.

**Request body**

| Field | Type | Default | Description |
|---|---|---|---|
| `filename` | `string` | required | Exact filename to delete |
| `doc_type` | `string` | required | `"manual"` \| `"failure_case"` \| `"criteria_config"` |

```json
{
  "filename": "ksb_manual.pdf",
  "doc_type": "manual"
}
```

**Response body**

| Field | Type | Description |
|---|---|---|
| `filename` | `string` | Echoed back |
| `status` | `string` | Always `"deleted"` on success |

```json
{
  "filename": "ksb_manual.pdf",
  "status": "deleted"
}
```

**Errors**

| Status | Condition | Message |
|---|---|---|
| 404 | File doesn't exist in the resolved directory | `"File not found: {filename}"` |
| 422 | `doc_type` is not one of the three allowed values | `"Unknown doc_type: {doc_type!r}"` |

This call triggers `build_knowledge_base(force_rebuild=True)` synchronously before returning — a full rebuild of the vector store, not an incremental delete.
