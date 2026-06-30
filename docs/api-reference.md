# API Reference

This document describes every HTTP endpoint exposed by the Asset Management Dashboard backend. It is written for developers integrating against the API directly, without reading the source.

## How the Routers Relate

The dashboard operates in two modes, and the three routers map onto them as follows:

- **Default Fleet Mode** uses the **AHP Router** (`/ahp`) and **RUL Router** (`/rul`). It serves a fixed set of 5 KSB Calio 30-40 pumps with hardcoded scoring rules calibrated to that pump model. The AHP criteria are always C1-C5 (Criticality, Condition, Failure Probability, Downtime Impact, Maintenance Cost Trend).
- **Uploaded Asset Mode** uses the **Upload Router** (`/upload`) exclusively. A user uploads an Excel file of any asset type; Claude infers 3-7 AHP criteria dynamically from the data (a `CriteriaConfig`), and all scoring, training, and RUL prediction for that asset type flow through this router instead of the AHP/RUL routers.

Both modes share the same AHP math (pairwise matrix -> weights -> Consistency Ratio) and the same Claude-based explanation step, but default fleet calls go through `ahp/api.py` and `rul/api.py` while uploaded asset calls go through `upload/api.py`, which calls the dynamic equivalents of the same logic internally.

All three routers are mounted on a single FastAPI app (`main.py`). Interactive Swagger docs are available at `http://localhost:8000/docs` when the backend is running.

---

## AHP Router (`/ahp`)

Used only in default fleet mode. Computes AHP weights from a pairwise comparison matrix, derives per-criterion Saaty scores for a single pump, computes a risk factor, and returns the full ranked pump list.

### POST `/ahp/calculate-weights`

Accepts a 5x5 pairwise comparison matrix (caller fills the upper triangle and diagonal; the lower triangle reciprocals are auto-filled) and returns the derived weight vector plus consistency metrics.

**Request body**

| Field | Type | Default | Description |
|---|---|---|---|
| `matrix` | `float[5][5]` | required | Pairwise comparison matrix. Diagonal must be `1`. Must be exactly 5x5. |

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
| `weights` | `float[5]` | Derived weight vector [w1-w5], summing to 1.0 |
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
| 422 | `matrix` is not 5x5, or any row is not length 5 | Pydantic validation error: `"matrix must be 5×5"` |

---

### POST `/ahp/score-asset`

Derives the five C1-C5 Saaty scores for a single pump from its raw variables. C1 and C4 are passed through as manual inputs; C2, C3, and C5 are computed from the pump's condition and maintenance history fields.

**Request body**

| Field | Type | Default | Description |
|---|---|---|---|
| `asset_id` | `string` | `""` | Asset identifier (optional, for reference only) |
| `criticality_raw` | `float` | required | C1 manual input, 1-10 |
| `condition_score` | `float` | required | 1-10, from telemetry aggregator |
| `vibration_level` | `string` | required | One of `Normal`, `High`, `Critical` |
| `seal_condition` | `string` | required | One of `Good`, `Worn`, `Leaking` |
| `bearing_condition` | `string` | required | One of `Good`, `Worn`, `Failed` |
| `age_years` | `float` | required | Asset age in years |
| `expected_lifespan_years` | `float` | required | Expected total lifespan in years |
| `number_of_failures_last_3yr` | `int` | required | Failure count, last 3 years |
| `days_since_maintenance` | `float` | required | Days since last maintenance event |
| `maintenance_frequency_days` | `float` | required | Recommended maintenance interval (90 for KSB Calio) |
| `downtime_impact_raw` | `float` | required | C4 manual input, 1-10 |
| `maintenance_cost_trend` | `string` | required | One of `Decreasing`, `Stable`, `Increasing` |
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
| `score_criticality` | `float` | C1 on 1-9 Saaty scale |
| `score_condition` | `float` | C2 on 1-9 Saaty scale |
| `score_failure_probability` | `float` | C3 on 1-9 Saaty scale |
| `score_downtime_impact` | `float` | C4 on 1-9 Saaty scale |
| `score_maintenance_cost_trend` | `float` | C5 on 1-9 Saaty scale |

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

Computes the risk factor (dot product) for one pump given a weight vector and score vector. Used as a standalone utility separate from the full `/ahp/assets` ranking.

**Request body**

| Field | Type | Default | Description |
|---|---|---|---|
| `weights` | `float[5]` | required | AHP weight vector, must sum to ~1.0 |
| `scores` | `float[5]` | required | Per-criterion Saaty scores, 1-9 each |

```json
{
  "weights": [0.35, 0.25, 0.2, 0.12, 0.08],
  "scores": [6.33, 2.78, 4.56, 5.44, 3.67]
}
```

**Response body**

| Field | Type | Description |
|---|---|---|
| `risk_factor` | `float` | Scalar 1-9, dot product of weights and scores |
| `weighted_scores` | `float[5]` | Per-criterion products [w1*s1 ... w5*s5] |

```json
{
  "risk_factor": 4.4123,
  "weighted_scores": [2.2155, 0.695, 0.912, 0.6528, 0.2936]
}
```

**Errors**

| Status | Condition | Message |
|---|---|---|
| 422 | `weights` or `scores` not exactly length 5 | Pydantic validation error: `"weights and scores must each have exactly 5 elements"` |

---

### GET `/ahp/assets`

Returns all 5 default fleet pumps ranked highest to lowest by risk factor. Loads telemetry via `telemetry_aggregator.py`, scores each pump with the current weights and manual C1/C4 inputs, and ranks the result.

**Query parameters**

| Param | Type | Default | Description |
|---|---|---|---|
| `weights` | `float` (repeated) | `[0.2, 0.2, 0.2, 0.2, 0.2]` | AHP weight vector, repeated query param, exactly 5 values |
| `c1_score` | `int` | `7` | Criticality manual input, 1-10 |
| `c4_score` | `int` | `6` | Downtime Impact manual input, 1-10 |

```
GET /ahp/assets?weights=0.35&weights=0.25&weights=0.2&weights=0.12&weights=0.08&c1_score=7&c4_score=6
```

**Response body**

Array of pump result objects, sorted descending by `risk_factor`. Each object includes all aggregator output fields (see CLAUDE.md "Aggregator Output Format") plus:

| Field | Type | Description |
|---|---|---|
| `asset_id` | `string` | Pump identifier |
| `asset_name` | `string` | Human-readable name |
| `risk_factor` | `float` | Scalar 1-9 |
| `weights` | `float[5]` | Weight vector used for this ranking |
| `scores` | `float[5]` | Saaty score vector [s1-s5] |
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

Used only in default fleet mode. Predicts remaining useful life adjusted by AHP risk factor, and generates a Claude explanation for a prediction. Both endpoints are guarded by the AHP Consistency Ratio.

### POST `/rul/predict`

Builds the 24-feature vector for the default fleet model, predicts RUL in years, and applies the AHP risk adjustment.

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
| `asset_id` | `string` | Pump identifier, echoed from `pump.asset_id` (empty string if absent) |
| `rul_years` | `float` | Predicted remaining useful life, risk-adjusted |
| `ci_low` | `float` | Lower bound of confidence interval (years) |
| `ci_high` | `float` | Upper bound of confidence interval (years) |

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
| 422 | `weights` or `scores` not length 5 | Pydantic validation error: `"must have exactly 5 elements"` |
| 422 | `pump` missing a required field for feature vector construction | Message from `build_feature_vector` (`KeyError`/`ValueError` text) |
| 422 | Feature vector fails shape/range validation | Message from `validate_feature_vector` |
| 503 | Model file (`rul/model.pkl`) not found or fails to load | Message from `predict_adjusted` (`RuntimeError` text) |

---

### POST `/rul/explain`

Calls Claude to generate a plain-English explanation of a RUL prediction for the default fleet (uses hardcoded KSB Calio asset type and failure modes).

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
| `asset_id` | `string` | Pump identifier, echoed from `pump.asset_id` |
| `explanation` | `string` | 3-4 sentence plain-English explanation from Claude |

```json
{
  "asset_id": "KSB-CALIO-3040-1000",
  "explanation": "This pump's RUL estimate of 4.7 years reflects moderate risk driven primarily by Criticality (weight 0.35) and Condition (weight 0.25)..."
}
```

**Errors**

| Status | Condition | Message |
|---|---|---|
| 400 | `cr > 0.10` | `"AHP matrix is inconsistent (CR > 0.10). Revise pairwise comparisons before requesting RUL predictions."` |
| 422 | `weights` or `scores` not length 5 | Pydantic validation error: `"must have exactly 5 elements"` |
| 502 | Anthropic API call fails | Message from `explain` (`RuntimeError` text, e.g. `"Anthropic API call failed: ..."`) |

---

## Upload Router (`/upload`)

Used only in uploaded asset mode. Handles the full pipeline for an arbitrary asset type: file validation, Claude-driven criteria inference (enriched by RAG retrieval), dynamic model training, scoring, RUL prediction, and explanation.

### POST `/upload/analyze`

Accepts a two-sheet Excel file upload. Validates structure, infers a `CriteriaConfig` via Claude (with RAG context when available), stores the config for future retrieval, trains a fresh XGBoost model, auto-generates a failure case document, and scores every detected asset (without RUL — RUL requires a separate `/upload/predict-all` call with user-supplied weights).

**Request**

`multipart/form-data` with a single field:

| Field | Type | Description |
|---|---|---|
| `file` | file (`.xlsx`) | Two-sheet Excel file: `Operational Telemetry` + `Failure & Maintenance Logs` |

**Response body**

| Field | Type | Description |
|---|---|---|
| `criteria_config` | `object` | Full `CriteriaConfig` inferred by Claude (see CriteriaConfig Schema in CLAUDE.md) |
| `schema_summary` | `object` | Detected column roles, sensor stats, asset IDs, date range, log event values |
| `training_result` | `object` | `{train_rmse, test_rmse, n_train_samples, n_test_samples}` |
| `assets` | `array` | One entry per detected asset (see below); `rul_years`/`rul_months` are `null` at this stage |
| `model_path` | `string` | Path to the trained model bundle, typically `rul/dynamic_model.pkl` |

Each entry in `assets`:

| Field | Type | Description |
|---|---|---|
| `asset_id` | `string` | Asset identifier |
| `snapshot_date` | `string` | Date of the snapshot row |
| `scores` | `object` | Saaty scores keyed by criterion ID, e.g. `{"C1": 6.33, "C2": 2.78, ...}` |
| `raw_scores` | `object` | Raw 1-10 scores keyed by criterion ID before Saaty conversion |
| `rul_years` | `null` | Always `null` from this endpoint |
| `rul_months` | `null` | Always `null` from this endpoint |
| ...sensor/rolling fields | varies | All remaining snapshot fields (sensor values, rolling means/stds, failure counts) keyed by their actual column names from the upload |

```json
{
  "criteria_config": {
    "asset_type": "Industrial Conveyor Motor",
    "failure_modes": ["Bearing wear", "Belt slippage", "Motor overheating"],
    "column_roles": {"asset_id": "Machine_ID", "date": "Timestamp", "rul_target": "RUL_Days", "operating_hours": "Runtime_Hours"},
    "criteria": [{"id": "C1", "name": "Criticality", "manual_input": true, "default_score": 7}]
  },
  "schema_summary": {
    "asset_id_column": "Machine_ID",
    "sensor_columns": ["Temp_C", "Vibration_Index"],
    "row_count": 1825
  },
  "training_result": {
    "train_rmse": 0.4123,
    "test_rmse": 0.5871,
    "n_train_samples": 1460,
    "n_test_samples": 365
  },
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
  "model_path": "rul/dynamic_model.pkl"
}
```

**Errors**

| Status | Condition | Message |
|---|---|---|
| 422 | File fails the two-sheet contract, column detection, or row-count minimum | Message from `validate_upload` (`UploadValidationError` text) |
| 422 | Claude returns invalid JSON, hallucinated column names, or fails validation rules | Message from `infer_criteria_config` (`RuntimeError` text) |
| 422 | Training fails (insufficient rows, invalid target column, etc.) | Message from `train_dynamic_model` (`ValueError`/`RuntimeError` text) |
| 422 | Snapshot aggregation fails | Exception text from `aggregate_uploaded_data` |
| 422 | Per-asset scoring fails | Exception text from `score_asset_dynamic` |

Note: RAG retrieval failures and CriteriaConfig storage failures never surface as errors here — both degrade silently (RAG returns `retrieval_available: false`; storage failures are caught and ignored).

---

### POST `/upload/predict-all`

Re-scores all assets from a previously uploaded file using user-supplied AHP weights and manual scores, and predicts RUL for each using the trained dynamic model.

**Request body**

| Field | Type | Default | Description |
|---|---|---|---|
| `file_path` | `string` | required | Path to the previously uploaded `.xlsx`, e.g. `data/raw/uploads/file.xlsx` |
| `weights` | `float[3-7]` | required | AHP weight vector, length must match the number of criteria (3-7) |
| `cr` | `float` | required | Current Consistency Ratio |
| `manual_scores` | `object` | required | Manual scores keyed by criterion ID, e.g. `{"C1": 7, "C4": 6}` |
| `model_path` | `string` | `"rul/dynamic_model.pkl"` | Path to the trained model bundle |

```json
{
  "file_path": "data/raw/uploads/conveyor_data.xlsx",
  "weights": [0.35, 0.25, 0.2, 0.12, 0.08],
  "cr": 0.07,
  "manual_scores": {"C1": 7, "C4": 6},
  "model_path": "rul/dynamic_model.pkl"
}
```

**Response body**

| Field | Type | Description |
|---|---|---|
| `assets` | `array` | One entry per asset, sorted descending by `risk_factor` |

Each entry in `assets`:

| Field | Type | Description |
|---|---|---|
| `asset_id` | `string` | Asset identifier |
| `snapshot_date` | `string` | Date of the snapshot row |
| `scores` | `object` | Saaty scores keyed by criterion ID |
| `raw_scores` | `object` | Raw 1-10 scores keyed by criterion ID |
| `risk_factor` | `float` | Scalar risk factor, rounded to 4 decimals |
| `weighted_scores` | `float[]` | Per-criterion weighted products |
| `rul_years` | `float` | Predicted RUL in years |
| `rul_months` | `float` | `rul_years * 12`, rounded to 1 decimal |
| `ci_low` / `ci_high` | `float` | Confidence interval bounds in years |
| `ci_low_months` / `ci_high_months` | `float` | Confidence interval bounds in months |
| ...sensor/rolling fields | varies | All remaining snapshot fields |

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
      "rul_years": 3.1,
      "rul_months": 37.2,
      "ci_low": 2.4,
      "ci_high": 3.9,
      "ci_low_months": 28.8,
      "ci_high_months": 46.8
    }
  ]
}
```

**Errors**

| Status | Condition | Message |
|---|---|---|
| 400 | `cr > 0.10` | `"AHP matrix is inconsistent (CR > 0.10). Revise pairwise comparisons."` |
| 404 | `model_path` does not exist | `"Model not found at '{model_path}'."` |
| 422 | `weights` not 3-7 elements | Pydantic validation error: `"weights must have 3-7 elements"` |
| 422 | Snapshot aggregation fails | Exception text from `aggregate_uploaded_data` |
| 422 | Feature vector construction or prediction fails | Message from `predict_adjusted_dynamic` (`FileNotFoundError`/`ValueError` text) |

---

### POST `/upload/explain`

Calls Claude to generate a plain-English explanation for an uploaded asset's RUL prediction, using the asset type and failure modes from its `CriteriaConfig`, and enriched with RAG-retrieved failure precedents and maintenance guidance when the knowledge base has relevant content.

**Request body**

| Field | Type | Default | Description |
|---|---|---|---|
| `pump` | `object` | required | Asset snapshot dict (same shape as a `/upload/predict-all` result entry) |
| `weights` | `float[3-7]` | required | AHP weight vector |
| `scores` | `float[3-7]` | required | Per-criterion Saaty scores |
| `risk_factor` | `float` | required | Overall risk factor |
| `predicted_rul` | `float` | required | Predicted RUL in years |
| `ci_low` | `float` | required | Confidence interval lower bound (years) |
| `ci_high` | `float` | required | Confidence interval upper bound (years) |
| `cr` | `float` | required | Current Consistency Ratio |
| `asset_type` | `string` | `"KSB Calio 30-40"` | Inferred asset type from `CriteriaConfig` |
| `failure_modes` | `string[]` | `null` | Inferred failure modes from `CriteriaConfig` |
| `sensor_context` | `object` | `null` | Key telemetry values keyed by actual sensor column name |

```json
{
  "pump": {"asset_id": "CONV-001"},
  "weights": [0.35, 0.25, 0.2, 0.12, 0.08],
  "scores": [6.33, 2.78, 4.56, 5.44, 3.67],
  "risk_factor": 5.2,
  "predicted_rul": 4.7,
  "ci_low": 3.2,
  "ci_high": 6.2,
  "cr": 0.07,
  "asset_type": "Industrial Conveyor Motor",
  "failure_modes": ["Bearing wear", "Belt slippage"],
  "sensor_context": {"Temp_C": 78.4, "Vibration_Index": 2.3}
}
```

**Response body**

| Field | Type | Description |
|---|---|---|
| `asset_id` | `string` | Asset identifier, echoed from `pump.asset_id` |
| `explanation` | `string` | 3-4 sentence plain-English explanation from Claude, may cite a retrieved failure precedent |

```json
{
  "asset_id": "CONV-001",
  "explanation": "This conveyor motor's RUL estimate of 4.7 years is driven primarily by elevated vibration readings (2.3, above the typical healthy range)..."
}
```

**Errors**

| Status | Condition | Message |
|---|---|---|
| 400 | `cr > 0.10` | `"AHP matrix is inconsistent (CR > 0.10). Revise pairwise comparisons."` |
| 422 | `weights` or `scores` not 3-7 elements | Pydantic validation error: `"must have 3-7 elements"` |
| 502 | Anthropic API call fails | Message from `explain` (`RuntimeError` text) |

Note: RAG retrieval failures never surface as an error here — `retrieve_for_explanation` catches them internally and the explanation proceeds without retrieved context.
