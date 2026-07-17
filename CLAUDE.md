# CLAUDE.md -- Asset Management Dashboard

## Project Overview

An asset management dashboard for **Agelix Consulting** extending the *Assets Maestro* platform. The system combines AHP (Analytic Hierarchy Process) risk scoring with XGBoost ML-based Remaining Useful Life prediction, Claude-powered GenAI explainability, and a RAG (Retrieval-Augmented Generation) knowledge pipeline that enriches both schema inference and RUL explanations with domain knowledge from manuals, past failure cases, and stored CriteriaConfigs. The system has two backend pipelines: a default fleet mode for 5 KSB Calio 30-40 pumps with fixed scoring rules, and an uploaded asset mode that accepts any asset type's telemetry and uses Claude to infer AHP criteria dynamically. **The dashboard UI currently renders only the uploaded asset mode** -- the default fleet mode's backend endpoints (`ahp/api.py`, `rul/api.py`) remain fully functional and are used directly by the AI team, but nothing in `Dashboard.jsx` renders them anymore (see Frontend Architecture).

---

## Architecture and Data Flow

The system has two parallel data pipelines sharing the same AHP engine and frontend. The default fleet pipeline uses hardcoded scoring rules calibrated to KSB pumps. The upload pipeline uses a CriteriaConfig dict -- inferred by Claude from the uploaded data -- as the single source of truth for all column names, scoring thresholds, and failure detection. No file downstream of schema_inferrer.py may hardcode a column name.

```
Default Fleet Mode (backend only -- not rendered in the dashboard UI):
  CEO telemetry + maintenance log
  -> telemetry_aggregator.py (per-pump snapshots)
  -> criteria_scoring.py (AHP scores C1-C5)
  -> ahp_engine.py (weights + CR validation)
  -> risk_calculator.py (risk factor dot product)
  -> feature_engineering.py + ml_rul_model.py (24-feature RUL)
  -> rul_explainer.py (Claude explanation)
  -> FastAPI (ahp/api.py + rul/api.py)
  -> (endpoints remain live for direct API use; Dashboard.jsx no longer renders this mode)

Upload Mode:
  User Excel file (.xlsx)
  -> upload_schema.py (validation + schema_summary)
  -> retriever.py (RAG: standards, similar configs, failure cases)
  -> schema_inferrer.py (Anthropic API + retrieved_context -> CriteriaConfig draft)
  -> knowledge_base.py (store draft CriteriaConfig for future retrieval)
  -> dynamic_train.py (trains XGBoost model on the draft config, bundle["approved"] = False)
  -> SME Review & Approve gate (React: UploadPanel.jsx review screen)
     -> POST /upload/approve-criteria (validates edits, locks bundle["criteria_config"],
        sets bundle["approved"] = True, re-stores the approved config via knowledge_base.py
        as a new versioned file, logs the draft-vs-approved diff via rag/audit_log.py)
  -> column_resolver.py (all column lookups, always against the approved config)
  -> dynamic_aggregator.py (asset snapshots + rolling + multi-sensor trend/correlation features)
  -> dynamic_criteria_scorer.py (AHP scores from the approved CriteriaConfig)
  -> threshold_breach_detector.py (deterministic threshold/penalty breach detection, no API call)
  -> mtbf_mtbm.py (deterministic MTBF / MTBM / replace-vs-maintain estimates, no API call)
  -> dynamic_feature_engineering.py (feature vector: rolling + correlation + breach features)
  -> dynamic_ml_rul_model.py (RUL -- POST /upload/predict-all requires bundle["approved"] == True)
  -> auto-generate failure case markdown (docs/failure_cases/)
  -> retriever.py (RAG: failure precedents, maintenance guidance)
  -> rul_explainer.py (Claude explanation with retrieved_context + correlation_summary)
  -> breach_explainer.py (on-demand Claude alert for high/medium severity breaches only)
  -> FastAPI (upload/api.py)
  -> React dashboard (Dashboard.jsx's only rendered view)

RAG Knowledge Pipeline:
  docs/manuals/ (PDF manuals)
  + docs/failure_cases/ (auto-generated + manual markdown)
  + rag/stored_configs/ (saved CriteriaConfigs as versioned JSON, one file per approval)
  -> document_loader.py (load + chunk all three types)
  -> knowledge_base.py (SentenceTransformer embeddings -> ChromaDB)
  -> retriever.py (targeted queries per use case)
  -> injected into schema_inferrer.py and rul_explainer.py prompts

Audit Trail (parallel to the above, not part of retrieval):
  Every POST /upload/approve-criteria call
  -> rag/audit_log.py log_approval() (draft vs. approved diff, appended to docs/audit_log.jsonl)
  -> GET /upload/audit-log (read back for the KnowledgeBasePanel's Approval Audit Log viewer)
```

---

## Folder Structure

```
agelix-consulting-project-2026/
|
+-- main.py                                # FastAPI entry point (mounts ahp + rul + upload + rag routers)
+-- CLAUDE.md
+-- README.md
+-- .env                                   # never commit
+-- .env.example
+-- .gitignore
+-- requirements.txt
|
+-- ahp/
|   +-- __init__.py
|   +-- ahp_constants.py                   # FROZEN
|   +-- criteria_scoring.py                # FROZEN
|   +-- ahp_engine.py                      # FROZEN
|   +-- risk_calculator.py                 # FROZEN
|   +-- api.py
|   +-- dynamic_criteria_scorer.py         # interprets CriteriaConfig at runtime
|   +-- threshold_breach_detector.py       # deterministic threshold/penalty breach detection
|
+-- rul/
|   +-- __init__.py
|   +-- feature_engineering.py             # FROZEN -- 24-feature vector (default fleet)
|   +-- ml_rul_model.py                    # FROZEN -- predict/predict_adjusted (default model)
|   +-- train.py                           # FROZEN -- trains default KSB XGBoost model
|   +-- rul_explainer.py                   # optional params added with backward-compatible defaults
|   +-- breach_explainer.py                # on-demand Claude alert for a single threshold breach
|   +-- mtbf_mtbm.py                       # deterministic MTBF/MTBM/replace-vs-maintain estimates
|   +-- api.py                             # FROZEN
|   +-- model.pkl                          # trained default model (generated by train.py)
|   +-- dynamic_feature_engineering.py     # variable-length feature vector (uploaded assets)
|   +-- dynamic_ml_rul_model.py            # predict for dynamically trained models
|   +-- dynamic_train.py                   # trains XGBoost on any uploaded dataset, bundle["approved"]=False
|   +-- dynamic_model.pkl                  # trained uploaded model (generated per upload)
|
+-- data/
|   +-- raw/
|   |   +-- telemetry/
|   |   |   +-- KSB_Calio_Predictive_Maintenance_Complete.xlsx   # 1095 days x 5 pumps
|   |   +-- maintenance/
|   |   |   +-- maintenance_log.xlsx
|   |   +-- uploads/
|   |       +-- (user-uploaded files land here)
|   +-- telemetry_aggregator.py            # FROZEN -- sole data source for default fleet
|   +-- dynamic_aggregator.py              # reads uploaded Excel, produces snapshots + correlation/trend features
|   +-- upload_schema.py                   # validates uploaded Excel (two-sheet contract)
|   +-- schema_inferrer.py                 # Anthropic API -> CriteriaConfig dict
|   +-- column_resolver.py                 # centralized column lookup utility
|   +-- generate_maintenance_log.py        # CEO script: generates telemetry + maintenance log
|   +-- data_schema.py
|
+-- upload/
|   +-- __init__.py
|   +-- api.py                             # /upload/analyze, /upload/approve-criteria, /upload/predict-all,
|   |                                      # /upload/explain, /upload/explain-breach
|
+-- rag/
|   +-- __init__.py
|   +-- __main__.py                        # entry point for python -m rag
|   +-- document_loader.py                 # loads + chunks PDFs, markdown, JSON configs
|   +-- knowledge_base.py                  # ChromaDB vector store management
|   +-- retriever.py                       # RAG retrieval entry point for all use cases
|   +-- ingest.py                          # CLI: python -m rag.ingest [--rebuild]
|   +-- api.py                             # /rag/* endpoints (upload, list, delete documents)
|   +-- audit_log.py                       # writes/reads docs/audit_log.jsonl (draft vs approved diffs)
|   +-- chroma_db/                         # ChromaDB persistent store (gitignored)
|   +-- stored_configs/                    # saved CriteriaConfig JSON files, versioned per approval
|
+-- frontend/
|   +-- src/
|       +-- App.jsx
|       +-- components/
|       |   +-- Dashboard.jsx              # renders only the uploaded-mode view -- no mode toggle
|       |   +-- AHPMatrix.jsx              # rendered once a criteria config exists
|       |   +-- DataUpload.jsx             # orphaned -- not imported by Dashboard.jsx
|       |   +-- WeightDisplay.jsx          # orphaned -- default-fleet-only, not imported by Dashboard.jsx
|       |   +-- AssetRegistry.jsx          # orphaned -- default-fleet-only, not imported by Dashboard.jsx
|       |   +-- RiskRanking.jsx            # orphaned -- default-fleet-only, not imported by Dashboard.jsx
|       |   +-- CriteriaContribution.jsx   # orphaned -- default-fleet-only, not imported by Dashboard.jsx
|       |   +-- RiskScatterPlot.jsx        # orphaned -- default-fleet-only, not imported by Dashboard.jsx
|       |   +-- ManualScoreInputs.jsx      # orphaned -- not imported by Dashboard.jsx (uploaded mode edits
|       |   |                             # manual default_score inline inside UploadPanel's review cards instead)
|       |   +-- RULDisplay.jsx             # orphaned -- default-fleet-only, not imported by Dashboard.jsx
|       |   +-- RULExplanation.jsx         # orphaned -- default-fleet-only, not imported by Dashboard.jsx
|       |   +-- UploadPanel.jsx            # file drop + AI criteria review/approve screen + predict button
|       |   +-- KnowledgeBasePanel.jsx     # collapsible RAG document manager + Approval Audit Log viewer
|       |   +-- DynamicAssetTable.jsx      # risk ranking + RUL + breach status/alerts + MTBF/MTBM columns
|       +-- hooks/
|       |   +-- useAHP.js                  # used internally by AHPMatrix.jsx
|       |   +-- useRiskScores.js           # orphaned -- default-fleet-only, not imported by Dashboard.jsx
|       |   +-- useRUL.js                  # orphaned -- default-fleet-only, not imported by Dashboard.jsx
|       |   +-- useUpload.js              # upload flow state management
|       |   +-- useKnowledgeBase.js       # RAG document list + upload/delete state + audit log fetch
|       +-- utils/
|           +-- dateUtils.js
|           +-- dataParser.js
|
+-- tests/
|   +-- ahp/
|   |   +-- test_ahp_engine.py
|   |   +-- test_criteria_scoring.py
|   +-- rul/
|   |   +-- test_telemetry_aggregator.py
|   |   +-- test_feature_engineering.py
|   |   +-- test_ml_rul_model.py
|   |   +-- test_rul_explainer.py
|   +-- upload/
|       +-- test_upload_pipeline.py        # 19 integration tests
|
+-- docs/
    +-- ahp-methodology.md
    +-- criteria-scoring-rules.md
    +-- data-schema.md
    +-- rul-methodology.md
    +-- manuals/                            # PDF manuals for RAG ingestion
    +-- failure_cases/                      # auto-generated + manual failure case markdown
    +-- audit_log.jsonl                      # append-only approval audit trail (auto-created)
```

---

## Frozen Files

These files must never be modified. They are stable, tested, and depended upon by the rest of the system. Any new functionality must be implemented in new files that import from these, not by editing them.

- `ahp/criteria_scoring.py` -- AHP scoring rules, convert_to_saaty(), clamp()
- `ahp/ahp_engine.py` -- pairwise matrix math, CR calculation
- `ahp/risk_calculator.py` -- risk factor dot product
- `rul/feature_engineering.py` -- 24-feature vector for default KSB fleet
- `rul/ml_rul_model.py` -- predict() and predict_adjusted() for default model
- `rul/train.py` -- trains default KSB XGBoost model
- `data/telemetry_aggregator.py` -- sole data source for default fleet

One permitted exception: `rul/rul_explainer.py` accepts optional parameters (`asset_type`, `failure_modes`, `sensor_context`, `retrieved_context`) added with defaults that preserve all existing call signatures.

---

## Asset Type and Engineering Specs

**KSB Calio 30-40 Glandless Circulator Pump** (Material No. 29134915)
All default fleet scoring rules, thresholds, and RUL calculations are calibrated to this pump.

### Engineering Specs (used in scoring rules)
| Parameter | Value |
|---|---|
| Speed range | 1,000 - 2,900 RPM |
| Max current | 0.91A |
| Max winding temp | 110C (Class F insulation) |
| Max SPM temp | 105C |
| Normal voltage | 230V AC +/- 10% (207 - 253V) |
| Fluid temp range | -10 to 110C |
| Expected max lifetime | 30,000 operating hours |
| Recommended PM interval | 90 days |

### Known Failure Modes
| Component | Cause | Key Signal |
|---|---|---|
| Bearings (ceramic/carbon) | Dry running, cavitation, abrasive wear | Vibration_Score spike |
| Power electronics (SPM) | Thermal stress, voltage surges | SPM_Temp_C high, Mains_Voltage anomaly |
| Motor windings (ECM) | Insulation breakdown from overtemp | Winding_Temp_C above 110C |

---

## Data Sources

### Default Fleet -- Telemetry File

Path: `data/raw/telemetry/KSB_Calio_Predictive_Maintenance_Complete.xlsx`

| Column | Type | Notes |
|---|---|---|
| `Pump_ID` | String | KSB-CALIO-3040-1000 through 1004 |
| `Date` | DateTime | Daily timestamp |
| `Operating_Hours` | Float | Cumulative runtime hours |
| `Speed_RPM` | Float | 1,000 - 2,900 RPM |
| `Current_A` | Float | 0.15 - 0.91A |
| `Winding_Temp_C` | Float | Max 110C |
| `SPM_Temp_C` | Float | Max 105C |
| `Mains_Voltage` | Float | 207 - 253V normal |
| `Fluid_Temp_C` | Float | -10 to 110C |
| `Vibration_Score` | Float | Near 0 = healthy, spikes near failure |
| `True_RUL_Days` | Float | Days until failure -- ML training target |

### Default Fleet -- Maintenance Log

Path: `data/raw/maintenance/maintenance_log.xlsx`

| Column | Type | Notes |
|---|---|---|
| `Log_ID` | String | Unique event ID |
| `Pump_ID` | String | Links to telemetry |
| `Event_Timestamp` | DateTime | When event occurred |
| `Event_Type` | String | Maintenance or Failure |
| `Failed_Component` | String | Bearings / Electronics / Motor_Winding / None |
| `Root_Cause` | String | Mechanical_Wear / Thermal_Overload / Insulation_Breakdown / Scheduled_PM |

### Uploaded Asset Files

Path: `data/raw/uploads/<filename>`

**Accepted format: .xlsx only. CSV is not supported.**
Two sheets required with exact names (case-sensitive):
- Sheet 1: **`Operational Telemetry`** -- one row per asset per day
- Sheet 2: **`Failure & Maintenance Logs`** -- one row per event

Column detection is heuristic -- no specific column names are required. `upload_schema.py` detects roles by keyword matching:
- Asset ID: column name contains "id" (case-insensitive)
- Date: column name contains "date", "time", or "timestamp"
- RUL target: numeric column containing "rul", "remaining", "life", or "ttf"
- Operating hours: numeric column containing "hour", "runtime", "operating", "cycles", or "cumulative"
- Event type: column containing "type" (preferred) then "event" (excluding date columns)
- Sensor columns: all remaining numeric columns (minimum 2 required)

If a role cannot be detected, validation fails with an error message listing all column names found so the user knows what to rename.

**Minimum Data Requirements:**
- Minimum 10 rows total in the telemetry sheet (enforced by validation)
- Minimum 2 numeric sensor columns beyond the 4 role columns
- At least 1 row in the log sheet (empty log sheet is tolerated but reduces scoring quality)
- Asset IDs in the log must match asset IDs in telemetry (orphan IDs cause validation failure)
- Recommended: 30+ rows per asset for reliable XGBoost RUL training

---

## Two Backend Modes, One Rendered Dashboard

### Default Fleet Mode (backend only)

Loads 5 KSB Calio 30-40 pumps from CEO telemetry via `telemetry_aggregator.py`. AHP criteria are fixed (C1-C5 as defined below). C1 (Criticality) and C4 (Downtime Impact) are manual inputs; C2, C3, C5 are auto-derived from telemetry. All of `ahp/api.py` and `rul/api.py` remain fully functional and are used directly by the AI team, but **`Dashboard.jsx` no longer imports or renders any component for this mode** -- no mode toggle, no KPI cards, no `WeightDisplay`/`AssetRegistry`/`RiskRanking`/`CriteriaContribution`/`RiskScatterPlot`/`RULDisplay`/`RULExplanation`, no score history log. Those component files and the `useRiskScores`/`useRUL` hooks still exist on disk (kept intentionally, never deleted) but are orphaned -- nothing in the frontend imports them anymore.

### Uploaded Asset Mode (the dashboard's only rendered view)

Accepts any asset type with operational telemetry and a failure/maintenance log. Claude infers AHP criteria dynamically from the uploaded data. `Dashboard.jsx` renders directly into this view on load -- there is nothing to toggle to.

Dashboard layout (top to bottom):
1.  AHPMatrix (rendered once a criteria config -- draft or approved -- exists; labels from CriteriaConfig, not hardcoded)
2.  UploadPanel (file drop + Review & Approve Criteria screen + predict button, gated on approval)
3.  KnowledgeBasePanel (collapsible; manuals/failure cases/criteria configs + Approval Audit Log)
4.  DynamicAssetTable (risk ranking + RUL + MTBF/MTBM columns + breach status + inline explanations)

---

## AHP Engine

### The 5 Criteria (Default Fleet)

| # | Criterion | Source | Default |
|---|---|---|---|
| C1 | Criticality | Manual input | 7 |
| C2 | Condition | Derived from Vibration_Score, Winding_Temp_C, SPM_Temp_C, Current_A | auto |
| C3 | Failure Probability | Derived from Operating_Hours, failure log, maintenance log | auto |
| C4 | Downtime Impact | Manual input | 6 |
| C5 | Maintenance Cost Trend | Derived from failure log event counts + Mains_Voltage anomalies | auto |

### Scale Convention

- All inputs: 1-10 internal scale
- All outputs: 1-9 Saaty scale via convert_to_saaty()
- Higher score = higher risk across ALL criteria

```python
def convert_to_saaty(score: float) -> float:
    return round(1 + (score - 1) * (8 / 9), 2)
```

### Scoring Rules

**C1 -- Criticality**
```
input:  criticality_raw (1-10)
output: convert_to_saaty(clamp(criticality_raw, 1, 10))
```

**C2 -- Condition**
```
input:  condition_score (1-10, from aggregator)
output: convert_to_saaty(clamp(condition_score, 1, 10))
```

**C3 -- Failure Probability**
```
inputs: age_years, number_of_failures_last_3yr,
        days_since_maintenance, maintenance_frequency_days

age_ratio = age_years / (30000 / 22 / 365)   # normalize to lifespan
age_factor: ratio brackets 0-5 pts (see Telemetry Aggregator section)

failure_factor = min(number_of_failures_last_3yr, 4)

overdue_ratio = days_since_maintenance / maintenance_frequency_days
overdue_factor: ratio brackets 0-2 pts

raw = clamp(round((age_factor + failure_factor + overdue_factor) / 11 * 10), 1, 10)
output = convert_to_saaty(raw)
```

**C4 -- Downtime Impact**
```
input:  downtime_impact_raw (1-10)
output: convert_to_saaty(clamp(downtime_impact_raw, 1, 10))
```

**C5 -- Maintenance Cost Trend**
```
inputs: maintenance_cost_trend (enum), maintenance_cost_last_year ($)

trend_base: Decreasing -> 2, Stable -> 5, Increasing -> 8

cost_modifier:
  < $1,000    -> -1
  $1k - $3k   -> 0
  $3k - $6k   -> +1
  > $6,000    -> +2

raw = clamp(trend_base + cost_modifier, 1, 10)
output = convert_to_saaty(raw)
```

### AHP Matrix Math

1. Fill reciprocals: `matrix[j][i] = 1 / matrix[i][j]`
2. Column-normalize: divide each cell by its column sum
3. Derive weights: average each row -> `weights [w1-w5]`, sum = 1.0
4. Compute CR:
```
lambda_max = mean(weighted_sum_vector / weights)
CI = (lambda_max - n) / (n - 1)    # n = 5
CR = CI / RI[5]                     # RI[5] = 1.12
```
5. CR <= 0.10 -> valid. CR > 0.10 -> warn user, block RUL prediction.

```python
RI = {1: 0.00, 2: 0.00, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32}
CR_THRESHOLD = 0.10
CRITERIA = ["Criticality", "Condition", "Failure Probability",
            "Downtime Impact", "Maintenance Cost Trend"]
```

### Risk Factor

```python
risk_factor = sum(w * s for w, s in zip(weights, scores))
```
Result: 1-9 per asset. All assets ranked highest to lowest.

---

## Telemetry Aggregator (Default Fleet)

### Purpose

Sole data source for the default KSB fleet. Reads the CEO's Excel files and produces one AHP-compatible pump dict per pump using the exact variable names that `criteria_scoring.py` expects.

### Date Column Detection

The telemetry date column may be "Date" or "Timestamp" depending on which version of the CEO's file is present. The aggregator detects which exists at load time and uses it throughout. Never hardcode either name.

### Per-Pump Snapshot Offsets

Each pump is captured at a different point in its lifecycle to create meaningful spread across the dashboard:
```python
_PUMP_OFFSETS = {
    "KSB-CALIO-3040-1000": -100,   # ~100 days of life remaining
    "KSB-CALIO-3040-1001": -200,   # ~200 days remaining
    "KSB-CALIO-3040-1002": -300,   # ~300 days remaining
    "KSB-CALIO-3040-1003": -500,   # ~500 days remaining
    "KSB-CALIO-3040-1004": -700,   # ~700 days remaining (healthiest)
}
```
The snapshot row determines all aggregated values: Operating_Hours, Winding_Temp_C, True_RUL_Days, and the reference date for maintenance log lookups. The 7-row rolling window ends at the snapshot row.

### Public Interface

```python
def get_pump_data(c1_score: int = 7, c4_score: int = 6) -> list[dict]:
    """Returns list of 5 pump dicts ready for criteria_scoring.py."""
```

### How Each Criterion Is Derived

**C2 -- Condition (from telemetry)**

Step 1: Rolling 7-day mean of Vibration_Score -> vibration base score.
Vibration_Score is an unbounded degradation index (0 = healthy, 6+ near failure).
```
vibration_mean < 0.5    -> base = 9  (healthy)
vibration_mean 0.5-1.0  -> base = 7  (slight wear)
vibration_mean 1.0-2.0  -> base = 5  (moderate wear)
vibration_mean 2.0-3.5  -> base = 3  (significant wear)
vibration_mean > 3.5    -> base = 1  (critical)
```

Step 2: Apply penalties
```
Winding temp penalty (% of 110C limit):
  Winding_Temp_C < 55C   -> 0
  55C - 77C              -> -1
  77C - 99C              -> -2
  > 99C                  -> -3

SPM temp penalty (% of 105C limit):
  SPM_Temp_C < 52C       -> 0
  52C - 73C              -> -1
  73C - 94C              -> -2
  > 94C                  -> -3

Current load penalty (% of 0.91A max):
  Current_A < 60% max    -> 0
  60% - 75%              -> -1
  75% - 90%              -> -2
  > 90%                  -> -3
```

Step 3: `condition_score = clamp(base + winding_penalty + spm_penalty + current_penalty, 1, 10)`

Enum fields for the UI:
```
vibration_level:
  vibration_mean < 1.0    -> Normal
  vibration_mean 1.0-2.5  -> High
  vibration_mean > 2.5    -> Critical

bearing_condition (from 7-day std dev of Vibration_Score):
  std < 0.3   -> Good
  std 0.3-0.8 -> Worn
  std > 0.8   -> Failed

seal_condition (from 7-day slope of Current_A):
  slope near 0 (stable)      -> Good
  slope rising < 10% of mean -> Worn
  slope rising > 10% of mean -> Leaking
```

**C3 -- Failure Probability (from telemetry + maintenance log)**
```python
total_runtime_hours = latest Operating_Hours value
age_ratio = total_runtime_hours / 30000

age_factor:
  age_ratio < 0.20  -> 0
  age_ratio < 0.40  -> 1
  age_ratio < 0.60  -> 2
  age_ratio < 0.80  -> 3
  age_ratio < 1.00  -> 4
  age_ratio >= 1.00 -> 5

number_of_failures_last_3yr = count of Event_Type == "Failure" in last 365 days
failure_factor = min(number_of_failures_last_3yr, 4)

last_maintenance = most recent Event_Timestamp where Event_Type == "Maintenance"
days_since_maintenance = (latest_date - last_maintenance).days
maintenance_frequency_days = 90

overdue_ratio = days_since_maintenance / 90
overdue_factor:
  overdue_ratio < 0.50  -> 0
  overdue_ratio < 1.00  -> 1
  overdue_ratio >= 1.00 -> 2

age_years = total_runtime_hours / 22 / 365
```

**C1 -- Criticality (manual input):** Default 7. User overridable 1-10 via ManualScoreInputs.jsx.

**C4 -- Downtime Impact (manual input):** Default 6. User overridable 1-10 via ManualScoreInputs.jsx.

**C5 -- Maintenance Cost Trend (from maintenance log + telemetry)**
```python
current_period_failures  = count Failure events in last 90 days
previous_period_failures = count Failure events in prior 90 days

maintenance_cost_trend:
  current > previous + 1    -> Increasing
  abs(current - previous) <= 1 -> Stable
  current < previous - 1    -> Decreasing

voltage_anomaly_count = count of days where Mains_Voltage < 207 or > 253 in last 30 days

maintenance_cost_last_year = sum of repair costs for failures in last 365 days:
  Bearings failure       -> $2,500
  Electronics failure    -> $4,000
  Motor_Winding failure  -> $3,500
  Unknown failure        -> $3,000
```

### Aggregator Output Format

```python
{
    "asset_id": "KSB-CALIO-3040-1000",
    "asset_name": "KSB Calio 3040 - Unit 1000",
    "manufacturer": "KSB",
    "model_number": "Calio 30-40",
    "location": "Plant 1",
    "expected_lifespan_years": 20,
    "total_runtime_hours": 14500.0,
    "age_years": 1.81,
    "operating_hours_per_day": 22,
    "condition_score": 7,
    "vibration_level": "Normal",
    "temperature_celsius": 54.2,
    "seal_condition": "Good",
    "bearing_condition": "Good",
    "number_of_failures_last_3yr": 1,
    "days_since_maintenance": 45,
    "maintenance_frequency_days": 90,
    "maintenance_cost_last_year": 2500,
    "maintenance_cost_trend": "Stable",
    "criticality_raw": 7,
    "downtime_impact_raw": 6,
    "rolling_vibration_mean": 0.42,
    "rolling_vibration_std": 0.08,
    "rolling_winding_temp_mean": 54.2,
    "rolling_spm_temp_mean": 58.1,
    "rolling_current_mean": 0.55,
    "voltage_anomaly_count": 1,
    "true_rul_days": 87
}
```

---

## Upload Pipeline

### upload_schema.py

Validates uploaded Excel files against the two-sheet contract. Detects column roles by heuristic keyword matching. Returns a `schema_summary` dict containing detected column names, sensor column list, per-sensor statistics (min, max, mean, std, p25, p75), asset IDs, row count, date range, log event type values, and log extra column samples. Raises `UploadValidationError` with descriptive messages on any failure.

### schema_inferrer.py

Makes one Anthropic API call (claude-sonnet-4-6, max_tokens=2500) with the full schema_summary. Accepts an optional `retrieved_context: dict` parameter. When provided and `retrieval_available` is True, a RETRIEVED DOMAIN KNOWLEDGE block is injected into the prompt between the sensor statistics and TASK sections, containing `standards_chunks`, `similar_configs`, and `failure_case_chunks` from the RAG pipeline. Claude returns a CriteriaConfig JSON dict -- the single source of truth for all downstream files. After parsing, validates every column name Claude returns against schema_summary to prevent hallucinated names from breaking the pipeline. Raises `RuntimeError` on API failure or invalid response. All existing behavior is unchanged when `retrieved_context` is None.

**failure_event_values fallback:** If Claude returns an empty `failure_event_values` list, the inferrer automatically populates it by scanning `schema_summary["log_event_type_values"]` for entries containing "fail", "fault", "error", or "breakdown" (case-insensitive). If no keyword matches, the first value in the list is used as fallback. Only raises an error if `log_event_type_values` itself is empty.

**Markdown fence stripping:** Claude's response is stripped of any leading ` ```json ` / ` ``` ` fences before JSON parsing.

### column_resolver.py

The single centralized module for all column lookups. Any file that reads a column from a data row must use this module -- never index by a hardcoded column name string.

```python
resolve(row, role, criteria_config, default=None, required=False)
resolve_sensor(row, column_name, default=None, required=False)
is_failure_event(row, criteria_config) -> bool
get_sensor_columns(criteria_config) -> list[str]
```

### dynamic_aggregator.py

Reads an uploaded Excel file and produces one asset snapshot dict per unique asset. For each asset: sorts by date column, computes rolling mean/std for every sensor column, then takes the row at **70% through the asset's data** (`index = int(len(asset_rows) * 0.7)`) as the snapshot. This captures a mid-life observation with meaningful remaining RUL rather than the near-zero value at end of life. From the log sheet, counts failures in last 90 days, total failure count, and days since last event. Sensor values and rolling features are keyed by actual column names from the data, not normalized names.

Also exports `compute_correlation_features(window, sensor_cols) -> dict`, the shared helper behind the multi-sensor correlation features below (see next section). `dynamic_train.py` imports this same function so training and inference compute identical features -- never duplicate this logic.

### Multi-Sensor Correlation and Trend Features

Beyond rolling mean/std, `dynamic_aggregator.py` computes a second layer of features over each asset's **trailing 14-row window** ending at the snapshot row (fewer rows if less than 14 are available). These feed both the RUL model (`dynamic_feature_engineering.py`) and the RUL explainer prompt.

```python
compute_correlation_features(window: pd.DataFrame, sensor_cols: list[str]) -> dict
```

For each sensor column:
```
trend_{col} = (last_value - first_value) / n
  where n = 14 if the window has >= 14 rows, else the actual window length
```

For each unique pair of sensor columns, taken in alphabetically sorted order so key names are deterministic regardless of column order in the source file:
```
interaction_{col_a}_{col_b}  = mean(col_a over window) * mean(col_b over window)
alignment_{col_a}_{col_b}    = trend_{col_a} * trend_{col_b}   (positive = co-degrading)
corr_{col_a}_{col_b}         = window[col_a].corr(window[col_b])  (0.0 if <2 rows or computation fails)
```

Composite stress index (single feature, mean of only the positive/degrading trends):
```
composite_stress_index = mean(t for t in all sensor trends if t > 0), else 0.0
```

`dynamic_train.py` calls `compute_correlation_features()` per historical training row (over that row's own trailing 14-row window) so the model is trained on the same feature distribution it sees at inference time.

`rul_explainer.py` reads `pump.get("correlation_summary")` -- a dict of `{"composite_stress_index", "top_correlated_pairs", "sensors_degrading_together"}` built by `upload/api.py` from the raw `corr_*`/`composite_stress_index` snapshot keys -- and injects a MULTI-SENSOR CORRELATION ANALYSIS block into the prompt when present, with an instruction to call out the multi-sensor degradation pattern when the stress index exceeds 0.3 or any pair's correlation exceeds 0.6. This is read from the `pump` dict directly, not a new function parameter, so it stays within the frozen-file exception for `rul_explainer.py` (see Frozen Files).

### Threshold Breach Detection (`ahp/threshold_breach_detector.py`)

Deterministic, no-API-call detection of sensor readings that have crossed into risky threshold or penalty bands. Runs on every `/upload/predict-all` call, for every asset.

```python
detect_breaches(asset_row: dict, criteria_config: dict) -> list[dict]
get_breach_summary(breaches: list[dict]) -> dict
```

For each non-manual criterion: walks its `thresholds` list (same left-to-right, first-match-wins logic as `dynamic_criteria_scorer.py`) to find the band the current `primary_column` value falls into. If that band's `score > 3`, it's a breach -- `threshold_max` is the `max` of the last band encountered with `score <= 3` (the safe/risk boundary that was crossed), not the ceiling of the matched band itself. Severity from `exceeded_pct = (value - threshold_max) / threshold_max`: `< 0.10` -> low, `0.10-0.25` -> medium, `> 0.25` -> high. The same walk runs over each `penalties[].bands` list; a band with `penalty <= -2` is a breach, using the same safe-boundary logic keyed on `penalty > -2` instead of `score <= 3`.

`get_breach_summary()` rolls a breach list up into `{"total_breaches", "high_severity", "medium_severity", "low_severity", "most_severe_criterion", "alert_required"}`. `alert_required` is `True` when there is at least one high-severity breach or two or more medium-severity breaches -- this gates whether the frontend's "Breach Alerts" button is enabled and whether Claude is ever called.

### On-Demand Breach Alerts (`rul/breach_explainer.py`)

Separate from `rul_explainer.py`. Only called when the user clicks "Breach Alerts" in the dashboard (never during scoring or training).

```python
explain_breach(asset_snapshot, breach, criteria_config, retrieved_context=None) -> str
explain_all_breaches(asset_snapshot, breaches, criteria_config, retrieved_context=None) -> list[dict]
```

`explain_all_breaches()` calls Claude only for breaches with `severity` in `("high", "medium")` -- low-severity breaches are skipped to minimize API calls. On any Anthropic API failure, `explain_breach()` never raises; it returns a deterministic fallback string naming the sensor and the percentage exceeded.

### SME Criteria Approval Gate

Claude's inferred `CriteriaConfig` is a **draft suggestion**, never authoritative on its own. After `/upload/analyze` trains a model, the bundle is saved with `bundle["approved"] = False`. The dashboard shows a "Review and Approve Criteria" screen (see Frontend Architecture) where a human can edit criterion names, `ui_label`, `default_score` (manual criteria), and threshold/penalty band values -- `primary_column` and sensor assignments are always read-only, since changing them would invalidate the already-trained model.

```
POST /upload/approve-criteria
  {"criteria_config": {...edited...}, "model_path": "rul/dynamic_model.pkl", "file_path": "..."}
```
Validates: 3-7 criteria; every criterion has `id`/`name`/`description`/`manual_input`; every non-manual criterion has `primary_column` (must still exist in the bundle's `schema_summary["sensor_columns"]`) and at least 2 thresholds; every threshold `score` is a number between 1 and 10. On success, overwrites `bundle["criteria_config"]`, sets `bundle["approved"] = True`, re-dumps the bundle, and calls `knowledge_base.store_criteria_config()` with the **approved** config so RAG retrieval for future uploads is built on human-validated data, not Claude's raw draft. Returns `{"status": "approved", "criteria_config": {...}, "changes_from_original": int}` where the change count is a per-field diff (`name`, `ui_label`, `default_score`, `thresholds`, `penalties`) across all criteria.

`POST /upload/predict-all` loads `criteria_config` exclusively from the model bundle (never from the request body) and returns HTTP 400 if `bundle.get("approved")` is not `True`: `"Criteria have not been approved. Complete the review step before running predictions."` This is the same CR > 0.10 style hard gate applied to an unapproved CriteriaConfig -- there is no way to bypass it from the API layer, and the frontend enforces the identical rule by disabling the Run button.

### Versioned CriteriaConfig Storage

`knowledge_base.store_criteria_config()` never overwrites a prior file for the same asset type. Filenames are `{sanitized_asset_type}_{YYYYMMDD_HHMMSS}.json` (UTC), e.g. `KSB_Calio_Centrifugal_Pump_20260701_142311.json`. Sanitization replaces any run of non-alphanumeric characters with a single underscore and preserves the original casing -- it does not lowercase. Every call to `store_criteria_config()` (after schema inference, and again after approval with the SME-edited version) writes a brand-new file, so the full inference history per asset type is preserved on disk and each gets its own ChromaDB document ID.

`GET /rag/documents` (see FastAPI Endpoints) sorts `criteria_configs` newest-first by the timestamp parsed out of the filename, and additionally returns `latest_per_asset_type`, built by reading each file's actual `asset_type` field from its JSON content (not reverse-engineered from the sanitized filename, since that transform is lossy) and keeping the first -- i.e. newest -- file seen per asset type. Legacy files saved before this scheme existed (no timestamp suffix) degrade gracefully to the bottom of the sort rather than erroring.

### Audit Trail Logging (`rag/audit_log.py`)

Every `POST /upload/approve-criteria` call records what Claude suggested versus what the human actually approved.

```python
log_approval(file_path, asset_type, original_config, approved_config,
             changes_count, config_filename=None) -> str
get_audit_log() -> list[dict]
```

`log_approval()` appends one JSON object per line to `docs/audit_log.jsonl` (created on first use) containing `timestamp`, `config_filename` (the exact versioned file written by `store_criteria_config()` for this approval), `file_path`, `asset_type`, `changes_from_claude`, `original_criteria`/`approved_criteria` (each criterion reduced to `id`/`name`/`thresholds`/`default_score`), and a `diff` list -- one entry per changed field (`name`, `thresholds`, `default_score`, `penalties`) per criterion, each with `criterion_id`, `field`, `claude_value`, `approved_value`. Never raises: on any failure it prints a warning and returns `""`. `get_audit_log()` reads the file back into a list of dicts, returning `[]` if it doesn't exist yet.

`upload/api.py`'s `approve_criteria()` handler captures `bundle["criteria_config"]` as `original_config` *before* overwriting it, calls `log_approval()` after the bundle is saved, and returns the logged timestamp to the caller as `approved_at` (see `POST /upload/approve-criteria` response). `GET /upload/audit-log` returns `{"entries": [...], "total_entries": int}` by calling `get_audit_log()` directly -- entries are the full stored dicts, not a trimmed projection.

The KnowledgeBasePanel's "Approval Audit Log" section (see Frontend Architecture) fetches this endpoint lazily on its own expand toggle (separate from the panel's own expand, and separate from the manuals/failure-cases/configs fetch), showing a Timestamp/Asset Type/File/Changes Made table where clicking a row expands a Criterion/Field/Claude's Value/Approved Value diff table.

### Maintenance Planning: MTBF, MTBM, Replace-vs-Maintain (`rul/mtbf_mtbm.py`)

Simplified, deterministic (no API call) approximations run on every `/upload/predict-all` call, for every asset -- not full Weibull statistical models.

```python
calculate_mtbf(asset_snapshot, criteria_config) -> dict
calculate_mtbm(mtbf_days, risk_factor, current_interval_days=90) -> dict
calculate_replace_vs_maintain(mtbf_days, maintenance_cost_last_year, asset_snapshot) -> dict
```

`calculate_mtbf()` estimates days between failures from `total_failure_count` and `total_runtime_hours` (using `operating_hours_per_day` from the snapshot, defaulting to 22 if absent): `>= 2` failures divides total operating days by the failure count (`basis="observed_failures"`); exactly `1` failure divides `total_runtime_hours` by 24 as a rough single-data-point approximation (`basis="single_failure"`); `0` failures returns `mtbf_days=None` (`basis="insufficient_data"`). `mtbf_confidence` is `"high"` at 5+ failures, `"medium"` at 2-4, `"low"` below that. Returns `{"mtbf_days", "mtbf_confidence", "mtbf_note", "basis"}`.

`calculate_mtbm()` takes `mtbf_days * 0.6` as a base recommended interval (industry heuristic: maintain at 60% of MTBF), then shortens it by up to 40% as `risk_factor` (1-9 Saaty scale) rises: `mtbm_adjusted = base * (1 - ((risk_factor - 1) / 8) * 0.4)`. Compares the rounded result to `current_interval_days` (passed in from the asset's `days_since_last_event` at the call site) to recommend `"shorten"` (< 80% of current), `"extend"` (> 120% of current), or `"maintain"`. Returns `{"mtbm_recommended_days", "current_interval_days", "recommendation", "recommendation_text", "next_maintenance_date"}` (ISO date, today + recommended days). If `mtbf_days` is `None`, every field is `None` except `recommendation = "insufficient_data"`.

`calculate_replace_vs_maintain()` opportunistically searches `asset_snapshot` for any key (excluding `maintenance_cost_last_year` itself, to avoid matching the input against itself) whose name contains "replacement", "value", or "cost" (case-insensitive) and holds a numeric value, using it as `estimated_replacement_cost`; falls back to a flagged $50,000 default (`replacement_cost_estimated=True`) if nothing matches. Amortizes that cost over `max(mtbf_days / 365, 1)` years and compares it to `annual_maintenance_cost`: `decision="replace"` if maintenance cost exceeds the amortized replacement cost per year, else `"maintain"`; `"insufficient_data"` if `mtbf_days` is `None`.

`upload/api.py`'s `POST /upload/predict-all` calls all three per asset and attaches `mtbf`, `mtbm`, `replace_vs_maintain` to each result (see FastAPI Endpoints). The frontend shows these in a "Maintenance Planning" section of the explain popup (three cards -- MTBF with confidence badge, PM interval with shorten/extend/maintain badge, economic decision -- plus a bold "Next Recommended Maintenance" date) and as two extra risk-ranking table columns, "Est. MTBF" and "PM Interval" (colored arrow: red down for shorten, green up for extend, grey dash for maintain).

---

## RAG Knowledge Pipeline

The RAG system enriches Claude's prompts in both schema inference and RUL explanation with retrieved domain knowledge. It is additive only -- the knowledge base is never required, and all RAG-dependent code paths degrade gracefully when it is missing or empty.

### Document Sources

Three document types are ingested:

| Type | Location | Format | Chunking |
|---|---|---|---|
| Manuals | `docs/manuals/` | PDF | RecursiveCharacterTextSplitter, chunk_size=500, overlap=50 |
| Failure cases | `docs/failure_cases/` | Markdown | RecursiveCharacterTextSplitter, chunk_size=300, overlap=30 |
| CriteriaConfigs | `rag/stored_configs/` | JSON | One chunk per file (full JSON) |

Failure case markdown files are auto-generated after each successful upload training run. They contain asset type, sensor columns, failure modes, inferred criteria names, and training RMSE. Manual failure case files can also be placed in the directory.

### document_loader.py

Loads and chunks all three document types. Returns a list of dicts with `content`, `source`, `page`, `doc_type` fields. Gracefully skips files that fail to load. `doc_type` values: `"manual"`, `"failure_case"`, `"criteria_config"`.

### knowledge_base.py

Manages the ChromaDB vector store at `rag/chroma_db/` using `chromadb.utils.embedding_functions.DefaultEmbeddingFunction()` (onnxruntime-based, ~50 MB). **Note:** an earlier version used `SentenceTransformer("all-MiniLM-L6-v2")` (PyTorch, ~3 GB). If you see `sentence-transformers` referenced anywhere, it has been replaced -- do not re-add it as it inflates the Docker image size prohibitively.

```python
build_knowledge_base(force_rebuild=False) -> int
```
Loads all document types via `document_loader.load_all_documents()` and ingests into ChromaDB. Deduplicates by `source::page=N` ID. Returns total document count.

```python
query(query_text, n_results=5, doc_type=None) -> list[str]
```
Returns list of content strings. Filters by `doc_type` metadata when provided. Raises `RuntimeError` with a helpful message if the store is missing.

```python
store_criteria_config(criteria_config, asset_type) -> Path
```
Saves CriteriaConfig as JSON to `rag/stored_configs/<sanitized_asset_type>_<YYYYMMDD_HHMMSS>.json` (see Upload Pipeline > Versioned CriteriaConfig Storage -- never overwrites a prior file) and calls `build_knowledge_base()` to add it to the store. Called automatically after each successful schema inference in `upload/api.py`, and again after each successful `POST /upload/approve-criteria` with the SME-approved version.

### retriever.py

Single entry point for all RAG retrieval. Two public functions, both returning dicts with a `retrieval_available` boolean. Both catch `RuntimeError` from `knowledge_base.query()` and return `retrieval_available=False` instead of raising -- missing knowledge base is always graceful degradation, never a failure.

```python
retrieve_for_schema_inference(schema_summary) -> dict
```
Makes three targeted queries (standards/manuals, similar past configs, failure cases). Returns `{"standards_chunks", "similar_configs", "failure_case_chunks", "retrieval_available"}`.

```python
retrieve_for_explanation(asset_snapshot, criteria_config, risk_factor) -> dict
```
Makes two targeted queries (failure precedents, maintenance standards). Returns `{"failure_precedents", "maintenance_guidance", "retrieval_available"}`.

### ingest.py

CLI script invoked via `python -m rag.ingest` (or `python -m rag`). Supports `--rebuild` flag for full rebuild. Creates `docs/manuals/`, `docs/failure_cases/`, `rag/stored_configs/`, and `rag/chroma_db/` if they don't exist, with `.gitkeep` files in the first three. Prints a helpful message if source directories are empty.

### Integration Points

**upload/api.py POST /upload/analyze:**
1. Calls `retrieve_for_schema_inference(schema_summary)` before `infer_criteria_config()`
2. Passes retrieved context as `retrieved_context` to `infer_criteria_config()`
3. Calls `store_criteria_config()` after successful inference
4. Auto-generates a failure case markdown file in `docs/failure_cases/` after successful training

**upload/api.py POST /upload/explain:**
1. Calls `retrieve_for_explanation()` before `rul_explainer.explain()`
2. Passes retrieved context as `retrieved_context` to `explain()`

**rul/rul_explainer.py:**
When `retrieved_context` is provided and `retrieval_available` is True, a RETRIEVED MAINTENANCE KNOWLEDGE block is injected into the prompt containing `failure_precedents` and `maintenance_guidance`. An instruction is added to cite the most relevant precedent by describing the case (not quoting verbatim). All existing behavior is unchanged when `retrieved_context` is None.

---

## CriteriaConfig Schema

```json
{
  "asset_type": "<inferred string>",
  "failure_modes": ["<mode 1>", "<mode 2>", "<mode 3>"],

  "column_roles": {
    "asset_id": "<exact column name from telemetry sheet>",
    "date": "<exact column name from telemetry sheet>",
    "rul_target": "<exact column name -- never assume True_RUL_Days>",
    "operating_hours": "<exact column name>",
    "log_asset_id": "<exact column name from log sheet>",
    "log_date": "<exact column name from log sheet>",
    "log_event_type": "<exact column name from log sheet>",
    "log_component": "<exact column name from log sheet, or null>"
  },

  "failure_event_values": ["<exact string values that indicate failure in log>"],

  "criteria": [
    {
      "id": "C1",
      "name": "<criterion name>",
      "description": "<one sentence>",
      "manual_input": true,
      "default_score": 7,
      "ui_label": "<label for dashboard input>"
    },
    {
      "id": "C2",
      "name": "<criterion name>",
      "description": "<one sentence>",
      "manual_input": false,
      "primary_column": "<exact sensor column name>",
      "secondary_columns": ["<exact names or empty list>"],
      "thresholds": [
        {"max": 1.0, "score": 9},
        {"max": 2.5, "score": 5},
        {"score": 1}
      ],
      "penalties": [
        {
          "column": "<exact sensor column name>",
          "description": "<what this penalizes>",
          "bands": [
            {"max": 70.0, "penalty": 0},
            {"max": 90.0, "penalty": -1},
            {"penalty": -2}
          ]
        }
      ]
    }
  ]
}
```

All column names in CriteriaConfig must exactly match column names present in the uploaded file. `schema_inferrer.py` validates this after every API call. No downstream file may hardcode a column name -- all lookups go through `column_resolver.py`.

This is the shape Claude produces as a **draft**. It is not authoritative until a human approves it via `POST /upload/approve-criteria` (see Upload Pipeline > SME Criteria Approval Gate) -- only then does `dynamic_criteria_scorer.py`, `dynamic_aggregator.py`, and the RUL model treat it as final. The SME may edit `name`, `ui_label`, `default_score`, and the values inside `thresholds`/`penalties`; `primary_column`, `secondary_columns`, and `column_roles` are never editable in the review screen because they are load-bearing for the already-trained model.

---

## ML RUL Pipeline

### Default Fleet RUL

Training data: CEO telemetry (1095 days x 5 pumps). Target: `True_RUL_Days / 365`.

24-feature input vector:
```python
[
    pump["total_runtime_hours"],          # 1
    pump["operating_hours_per_day"],      # 2
    pump["condition_score"],              # 3
    pump["number_of_failures_last_3yr"],  # 4
    pump["days_since_maintenance"],       # 5
    pump["maintenance_cost_last_year"],   # 6
    pump["criticality_raw"],             # 7
    pump["downtime_impact_raw"],         # 8
    weights[0..4],                        # 9-13 (5 AHP weights)
    weighted_scores[0..4],                # 14-18 (5 w*s products)
    risk_factor,                          # 19 (sum of 14-18)
    pump["rolling_vibration_mean"],       # 20
    pump["rolling_vibration_std"],        # 21
    pump["rolling_winding_temp_mean"],    # 22
    pump["rolling_spm_temp_mean"],        # 23
    pump["voltage_anomaly_count"],        # 24
]
```

Functions: `get_feature_names() -> list[str]`, `validate_feature_vector(v) -> None`.

```python
def predict(feature_vector) -> {"rul_years": float, "ci_low": float, "ci_high": float}
def predict_adjusted(feature_vector, risk_factor) -> same dict structure

# AHP risk adjustment:
R_asset = (risk_factor - 1) / 8    # normalize 1-9 to 0-1
rul_adjusted = rul_years * (1 - R_asset)
```

XGBoost params:
```python
n_estimators=200, max_depth=6, learning_rate=0.05,
subsample=0.8, colsample_bytree=0.8, objective="reg:squarederror"
```

Model location: `rul/model.pkl`. Train/test split by Pump_ID (hold out 2 pumps).

### Dynamic RUL (Uploaded Assets)

Training data: uploaded file, all rows with sufficient rolling window (skip first 7 per asset). Target: `row[criteria_config["column_roles"]["rul_target"]] / 365`.

Feature vector construction (deterministic order, built by `rul/dynamic_feature_engineering.py`):
1. total_runtime_hours, failures_last_90_days, days_since_last_event, total_failure_count (4 features)
2. weights[0..N-1] (N features)
3. For i in 0..N-1: weights[i] * convert_to_saaty(scores_raw[f"C{i+1}"]) (N features)
4. risk_factor = sum of step 3 (1 feature)
5. For each sensor column from `get_sensor_columns(criteria_config)`: rolling mean + rolling std (2M features)
6. For each sensor column, in the same order as step 5: `trend_{col}` (M features)
7. For each unique sensor pair, in `itertools.combinations(sorted(sensor_cols), 2)` order: `interaction_{col_a}_{col_b}` (C(M,2) features)
8. Same pair order: `alignment_{col_a}_{col_b}` (C(M,2) features)
9. Same pair order: `corr_{col_a}_{col_b}` (C(M,2) features)
10. `composite_stress_index` (1 feature)
11. `breach_count`, `high_severity_count`, `medium_severity_count`, `max_exceeded_pct` -- computed from `ahp.threshold_breach_detector.detect_breaches()` and passed into `build_dynamic_feature_vector()` as the optional `breaches` parameter; all four default to 0.0 when `breaches` is `None` or empty (4 features)

Total length: 4 + N + N + 1 + 2M + M + 3*C(M,2) + 1 + 4, where N = number of criteria (3-7) and M = number of unique sensor columns referenced by non-manual criteria. Variable across uploads but fixed for a given model. `get_dynamic_feature_names(criteria_config)` returns the matching name list in the same order -- always keep the two in lockstep when either changes.

All correlation/trend/breach features degrade gracefully to 0.0 via `column_resolver.resolve_sensor(snapshot, key, default=0.0)` with a logged warning if a key is missing from the snapshot -- never a hard failure. Steps 6-10 use the same sorted-pair key naming as `compute_correlation_features()` in `dynamic_aggregator.py` so lookups always match regardless of the sensor column's position in the original file.

Train/test split: hold out asset with most rows. Same XGBoost params as default fleet. `dynamic_train.py` computes `detect_breaches()` and `compute_correlation_features()` per training row (same trailing-14-row window logic as inference) so training and inference see an identical feature distribution.

Model bundle saved as dict: `{"model", "feature_names", "criteria_config", "schema_summary", "approved"}`. Feature vector length validated against `bundle["feature_names"]` at inference time. `approved` starts `False` at training time and is flipped to `True` only by `POST /upload/approve-criteria` (see Upload Pipeline > SME Criteria Approval Gate) -- `POST /upload/predict-all` refuses to run against an unapproved bundle.

Model location: `rul/dynamic_model.pkl`.

---

## GenAI Explainability

Model: claude-sonnet-4-6. API key: `ANTHROPIC_API_KEY` from `.env` via python-dotenv.

```python
def explain(pump, weights, scores, risk_factor, predicted_rul, ci_low, ci_high,
            asset_type="KSB Calio 30-40", failure_modes=None,
            sensor_context=None, retrieved_context=None) -> str
```

Prompt includes: asset ID and type, all 5 AHP criteria weights by name, all 5 per-criterion risk scores on 1-9 Saaty scale, overall risk factor out of 9, predicted RUL in years + confidence interval, key telemetry indicators, known failure modes.

When `sensor_context` is provided (uploaded mode), telemetry fields in the prompt are built from the dict keys rather than hardcoded field names. When `failure_modes` is provided, the hardcoded failure mode list is replaced. When `retrieved_context` is provided and `retrieval_available` is True, a RETRIEVED MAINTENANCE KNOWLEDGE block is injected containing failure precedents and maintenance guidance, with an instruction to cite the most relevant precedent by describing the case. All four optional parameters have defaults that preserve existing behavior for default fleet callers.

When `pump.get("correlation_summary")` is present (uploaded mode, set by `upload/api.py` from the asset's `corr_*`/`composite_stress_index` snapshot keys -- see Upload Pipeline > Multi-Sensor Correlation and Trend Features), a MULTI-SENSOR CORRELATION ANALYSIS block is injected listing the composite stress index and the top 3 correlated sensor pairs by absolute correlation, with an instruction to call out the multi-sensor degradation pattern when the stress index exceeds 0.3 or any pair exceeds 0.6 correlation. This reads an existing dict key rather than adding a fifth function parameter, so the frozen-file exception below is unaffected.

Returns plain text string only. Strip whitespace. On API failure: raise RuntimeError.

CR Guard (all RUL endpoints): If CR > 0.10 return HTTP 400: "AHP matrix is inconsistent (CR > 0.10). Revise pairwise comparisons before requesting RUL predictions."

---

## FastAPI Endpoints

### AHP Router (`ahp/api.py`) -- mounted at /ahp

| Method | Route | Description |
|---|---|---|
| POST | `/ahp/calculate-weights` | 5x5 matrix -> weights + CR + valid flag |
| POST | `/ahp/score-asset` | pump variables -> C1-C5 scores |
| POST | `/ahp/risk-factor` | weights + scores -> risk factor |
| GET  | `/ahp/assets` | all pumps ranked by risk score |

GET /ahp/assets query params:
```
?weights=0.35&weights=0.25&weights=0.2&weights=0.12&weights=0.08&c1_score=7&c4_score=6
```
- weights: repeated float params, defaults to [0.2, 0.2, 0.2, 0.2, 0.2]
- c1_score: int 1-10, default 7
- c4_score: int 1-10, default 6

### RUL Router (`rul/api.py`) -- mounted at /rul

| Method | Route | Description |
|---|---|---|
| POST | `/rul/predict` | pump + AHP features -> adjusted RUL + CI |
| POST | `/rul/explain` | pump + AHP + RUL -> Claude explanation |

POST /rul/predict body:
```json
{"pump": {}, "weights": [0.35, 0.25, 0.2, 0.12, 0.08],
 "scores": [6.33, 4.56, 5.44, 5.44, 3.67], "cr": 0.07}
```

POST /rul/explain body:
```json
{"pump": {}, "weights": [], "scores": [], "risk_factor": 5.2,
 "predicted_rul": 4.7, "ci_low": 3.2, "ci_high": 6.2, "cr": 0.07}
```

### Upload Router (`upload/api.py`) -- mounted at /upload

| Method | Route | Description |
|---|---|---|
| POST | `/upload/analyze` | Upload .xlsx -> validate, infer criteria (draft), train model (`approved=False`), score assets |
| POST | `/upload/approve-criteria` | SME approves/edits the draft CriteriaConfig -> locks the bundle, `approved=True` |
| POST | `/upload/predict-all` | Re-score + predict RUL with user weights; 400 if the bundle is not yet approved |
| POST | `/upload/explain` | Claude explanation for uploaded asset with dynamic sensor context + correlation summary |
| POST | `/upload/explain-breach` | On-demand Claude alerts for an asset's high/medium severity threshold breaches |
| GET  | `/upload/audit-log` | Full approval audit trail (draft vs. approved diffs across all uploads) |

POST /upload/approve-criteria body:
```json
{"criteria_config": {}, "model_path": "rul/dynamic_model.pkl", "file_path": "data/raw/uploads/file.xlsx"}
```
Response:
```json
{"status": "approved", "criteria_config": {}, "changes_from_original": 2, "approved_at": "2026-07-16T21:47:38"}
```
Returns HTTP 422 with a specific message if validation fails (wrong criteria count, missing fields, unknown `primary_column`, too few thresholds, out-of-range score). `approved_at` is the timestamp `rag/audit_log.py` logged the approval under (empty string if logging itself failed -- logging never blocks the approval).

GET /upload/audit-log response:
```json
{"entries": [{"timestamp": "...", "config_filename": "...", "file_path": "...", "asset_type": "...",
  "changes_from_claude": 2, "original_criteria": [], "approved_criteria": [], "diff": []}],
 "total_entries": 1}
```

POST /upload/predict-all body:
```json
{"file_path": "data/raw/uploads/file.xlsx", "weights": [0.35, 0.25, 0.2, 0.12, 0.08],
 "cr": 0.07, "manual_scores": {"C1": 7, "C4": 6}, "model_path": "rul/dynamic_model.pkl"}
```
`weights` length must match the number of criteria in the stored CriteriaConfig (3-7). The endpoint uses `range(n_criteria)` internally -- never hardcodes 5. `criteria_config` is loaded from the model bundle, never accepted in this body. Returns HTTP 400 if `bundle["approved"]` is not `True`. Each returned asset also includes `correlation_summary` (`composite_stress_index`, `top_correlated_pairs`, `sensors_degrading_together`), `breaches` (list), `breach_summary` (counts + `alert_required`), and `mtbf`/`mtbm`/`replace_vs_maintain` (see Upload Pipeline > Maintenance Planning).

POST /upload/explain body:
```json
{"pump": {}, "weights": [], "scores": [], "risk_factor": 5.2,
 "predicted_rul": 4.7, "ci_low": 3.2, "ci_high": 6.2, "cr": 0.07,
 "asset_type": "Centrifugal Pump", "failure_modes": ["Bearing wear"],
 "sensor_context": {"Vibration_Score": 2.3, "Winding_Temp_C": 85.0}}
```
`pump` is expected to be the full asset object from `/upload/predict-all` (including `correlation_summary`) so the explainer can read it directly.

POST /upload/explain-breach body:
```json
{"asset_snapshot": {}, "breaches": [], "criteria_config": {}, "model_path": "rul/dynamic_model.pkl", "cr": 0.0}
```
`criteria_config` is optional -- if omitted, it is loaded from the model bundle. Returns HTTP 400 if `cr > 0.10` (same CR guard as the other RUL endpoints). Response:
```json
{"asset_id": "...", "breach_alerts": [
  {"criterion_id": "C2", "criterion_name": "Bearing & Mechanical Condition",
   "column": "Vibration_Score", "severity": "high", "alert_text": "..."}
]}
```
Only breaches with `severity` in `("high", "medium")` produce an alert (see On-Demand Breach Alerts).

### RAG Router (`rag/api.py`) -- mounted at /rag

| Method | Route | Description |
|---|---|---|
| POST | `/rag/upload-document` | Multipart PDF upload -> save to docs/manuals/, ingest into ChromaDB |
| GET  | `/rag/documents` | List all ingested documents (manuals, failure_cases, criteria_configs) |
| DELETE | `/rag/document` | Delete a document by filename + type, rebuild knowledge base |

GET /rag/documents response:
```json
{"manuals": ["ksb_manual.pdf"], "failure_cases": ["pump_20260630.md"],
 "criteria_configs": ["KSB_Calio_Pump_20260705_120000.json", "KSB_Calio_Pump_20260701_100000.json"],
 "latest_per_asset_type": {"KSB Calio Pump": "KSB_Calio_Pump_20260705_120000.json"}}
```
`criteria_configs` is sorted newest-first by the timestamp embedded in each filename (see Upload Pipeline > Versioned CriteriaConfig Storage). `latest_per_asset_type` maps each config's actual `asset_type` JSON field to its newest filename.

DELETE /rag/document body:
```json
{"filename": "ksb_manual.pdf", "doc_type": "manual"}
```
`doc_type` must be one of `"manual"`, `"failure_case"`, `"criteria_config"`.
Delete triggers `build_knowledge_base(force_rebuild=True)` to purge stale embeddings.

---

## Frontend Architecture

`Dashboard.jsx` renders a single view -- there is no mode toggle and no default-fleet state. It owns one `useUpload` instance plus a small amount of local UI state; everything else default-fleet-related (`ahpResult`, `manualScores`, `assets`, `rulPredictions`, `rulExplanations`, `useRiskScores`, `useRUL`, and their imports) was removed from the component entirely -- see Two Backend Modes, One Rendered Dashboard.

### State in Dashboard.jsx

**All state is uploaded-mode state (owned by the `useUpload` hook, lifted into Dashboard.jsx):**
```javascript
criteriaConfig:          null   // Claude's draft, from /upload/analyze -- passed only to UploadPanel
criteriaApproved:        false  // flips true after /upload/approve-criteria succeeds
approvedCriteriaConfig:  null   // the SME-approved config returned by approve-criteria
approvalChanges:         0      // per-field diff count vs. the draft
predictedAssets:         []     // includes correlation_summary, breaches, breach_summary,
                                 // mtbf, mtbm, replace_vs_maintain per asset
uploadedExplanations:    {}     // keyed by asset_id
uploadedBreachAlerts:    {}     // keyed by asset_id, from /upload/explain-breach
uploadedAhpResult:       null   // { weights, cr, valid } from AHPMatrix's onWeightsUpdate
```
Dashboard computes `activeCriteriaConfig = approvedCriteriaConfig ?? criteriaConfig` and passes that (not the raw draft) to `AHPMatrix` and `DynamicAssetTable` -- everything downstream of approval sees the SME-approved version. `UploadPanel` alone still receives the raw `criteriaConfig` draft, since its own review screen needs the original for the "Reset to Claude's Suggestions" button.

### Dynamic Behavior

When file uploaded and analyzed:
  criteriaConfig set (draft) -> uploadedAssets populated with scores (no RUL yet) ->
  criteriaApproved reset to false, approvedCriteriaConfig reset to null

When criteria are approved:
  POST /upload/approve-criteria -> criteriaApproved = true, approvedCriteriaConfig set,
  approvalChanges set -> Run Risk and RUL Analysis button unlocks (still requires ahpValid too)

When predict-all runs:
  blocked client-side unless criteriaApproved -> predictedAssets set with RUL values in years
  (converted to days at display layer), each asset carrying correlation_summary + breaches +
  breach_summary + mtbf + mtbm + replace_vs_maintain

When explain requested:
  uploadedExplanations updated for that asset_id with sensor_context from the approved CriteriaConfig

When breach alerts requested:
  POST /upload/explain-breach -> uploadedBreachAlerts updated for that asset_id;
  button is disabled up front when breach_summary.alert_required is false

### Dashboard Layout (top to bottom)

1. AHPMatrix (only rendered after a criteria config -- draft or approved -- is available)
2. UploadPanel (file drop zone + Review & Approve Criteria screen + predict button, gated on approval)
3. KnowledgeBasePanel (collapsible; manuals/failure cases/criteria configs + Approval Audit Log)
4. DynamicAssetTable (only rendered when predictedAssets.length > 0; includes breach status
   column, MTBF/PM Interval columns, high-severity banner, and per-asset Explain / Breach Alerts popups)

### Component Inventory

| Component | File | Rendered by Dashboard.jsx? | Purpose |
|---|---|---|---|
| AHPMatrix | AHPMatrix.jsx | Yes | NxN pairwise matrix with CR validation, N = criteria count from CriteriaConfig (3-7) |
| UploadPanel | UploadPanel.jsx | Yes | File drop zone + Review & Approve Criteria screen (editable names/thresholds/penalties/default scores, Reset + Approve, locks on approval) + predict button gated on `criteriaApproved` |
| KnowledgeBasePanel | KnowledgeBasePanel.jsx | Yes | Collapsible RAG document manager (manuals/failure cases/criteria configs) + Approval Audit Log viewer; uses `useKnowledgeBase` internally |
| DynamicAssetTable | DynamicAssetTable.jsx | Yes | Risk ranking + RUL + MTBF/PM Interval columns + breach status column, high-severity banner, and Explain / Breach Alerts popups (Multi-Sensor Analysis + Maintenance Planning + breach metrics) |
| ManualScoreInputs | ManualScoreInputs.jsx | No (orphaned) | C1/C4 manual inputs component; uploaded mode edits `default_score` inline inside UploadPanel's review cards instead |
| DataUpload | DataUpload.jsx | No (orphaned) | CSV/JSON upload for KSB pump data |
| WeightDisplay | WeightDisplay.jsx | No (orphaned) | Recharts bar chart of criterion weights (default fleet) |
| AssetRegistry | AssetRegistry.jsx | No (orphaned) | Pump table with expandable detail rows (default fleet) |
| RiskRanking | RiskRanking.jsx | No (orphaned) | Ranked risk table + color-coded bar chart (default fleet) |
| CriteriaContribution | CriteriaContribution.jsx | No (orphaned) | Stacked bar of weighted criterion contributions (default fleet) |
| RiskScatterPlot | RiskScatterPlot.jsx | No (orphaned) | Risk vs Condition scatter with quadrants (default fleet) |
| RULDisplay | RULDisplay.jsx | No (orphaned) | RUL progress bars in months + CI (default fleet) |
| RULExplanation | RULExplanation.jsx | No (orphaned) | Claude explanation cards per pump (default fleet) |

"Orphaned" components/hooks are kept on disk deliberately (never delete component or hook files) -- they are simply not imported by `Dashboard.jsx` anymore. The default fleet's backend endpoints they used to call remain fully functional for direct API use.

### Hook Inventory

| Hook | File | Used by Dashboard.jsx? | State Managed |
|---|---|---|---|
| useAHP | useAHP.js | Indirectly (via AHPMatrix) | AHP matrix calculation API calls |
| useUpload | useUpload.js | Yes | Upload flow state: analyze, criteria approval (`criteriaApproved`, `approvedCriteriaConfig`, `approvalChanges`, `approveCriteria()`), predict-all (gated on approval), explain, explain-breach |
| useKnowledgeBase | useKnowledgeBase.js | Yes (via KnowledgeBasePanel) | RAG document lists, upload/delete status, audit log fetch (`auditLog`, `auditLogStatus`, `fetchAuditLog()`) |
| useRiskScores | useRiskScores.js | No (orphaned) | GET /ahp/assets with current weights (default fleet) |
| useRUL | useRUL.js | No (orphaned) | Auto-predict + on-demand explain (default fleet) |

### Data Upload Schema (dataParser.js)

Required fields for KSB pump CSV/JSON upload (26 total):
```
asset_id, asset_name, manufacturer, model_number, location,
total_runtime_hours, operating_hours_per_day,
condition_score, vibration_level, temperature_celsius,
seal_condition, bearing_condition,
number_of_failures_last_3yr, days_since_maintenance,
maintenance_frequency_days, maintenance_cost_last_year,
maintenance_cost_trend, criticality_raw, downtime_impact_raw,
rolling_vibration_mean, rolling_vibration_std,
rolling_winding_temp_mean, rolling_spm_temp_mean,
rolling_current_mean, voltage_anomaly_count, true_rul_days
```

Validation rules:
- condition_score, criticality_raw, downtime_impact_raw: 1-10
- total_runtime_hours: > 0
- rolling_vibration_mean, rolling_vibration_std, voltage_anomaly_count, true_rul_days: >= 0
- Enums: vibration_level, seal_condition, bearing_condition, maintenance_cost_trend
- 1-20 pumps per file, all fields required

On upload, Dashboard computes `age_years = total_runtime_hours / 22 / 365` and sets `expected_lifespan_years = 20`.

---

## Environment Variables

.env (never commit):
```
ANTHROPIC_API_KEY=your_key_here
API_BASE_URL=http://localhost:8000
```

.env.example:
```
ANTHROPIC_API_KEY=
API_BASE_URL=http://localhost:8000
```

---

## Key Design Constraints

| Constraint | Reason |
|---|---|
| telemetry_aggregator.py is the sole data source for the default fleet |
| Frozen files must not be modified | AHP and default RUL logic is stable and tested |
| age_years = total_runtime_hours / 22 / 365 | Not derived from install_date |
| Full AHP weight vector [w1-w5] as 5 separate features | Never collapse to scalar |
| Weighted score vector [w1*s1 ... w5*s5] as 5 separate features | Never collapse to scalar |
| ANTHROPIC_API_KEY always from .env via python-dotenv | Never hardcode |
| CR > 0.10 blocks RUL prediction in all modes | Invalid weights must not feed the ML model |
| RUL recalculates when weights or manual scores change | Everything must stay dynamic |
| RUL explanations fetch on demand only | Avoid excessive Anthropic API calls |
| C1 default = 7, C4 default = 6 (default fleet) | Grounded in KSB Calio operational context |
| C1 and C4 user input is always 1-10 | convert_to_saaty() handles conversion internally |
| predict_adjusted() applies AHP risk adjustment | R_asset = (risk_factor-1)/8, RUL *= (1-R_asset) |
| No file downstream of schema_inferrer may hardcode a column name | Column names vary across asset types and uploads |
| All column reads use column_resolver.resolve() or resolve_sensor() | Single point of change if CriteriaConfig structure evolves |
| column_roles in CriteriaConfig carries exact detected column names | Prevents re-detection drift between pipeline stages |
| failure_event_values carries exact log event type strings | Failure counts are wrong if the string doesn't match |
| schema_inferrer validates all column names Claude returns | Prevents hallucinated column names breaking the pipeline |
| Feature vector length is variable across uploads but fixed per model | Bundle stores feature_names alongside model for inference validation |
| RUL target column name from criteria_config["column_roles"]["rul_target"] | Never hardcode "True_RUL_Days" |
| RAG knowledge base is never required | Missing or empty knowledge base is graceful degradation, never a failure |
| retriever.py catches RuntimeError and returns retrieval_available=False | No RAG failure may block the upload or explain pipeline |
| CriteriaConfigs are stored after every successful inference | Builds retrieval context for future uploads of similar asset types |
| Failure case markdown is auto-generated after successful training | Accumulates domain knowledge for future RAG retrieval |
| Only .xlsx files are accepted for upload | CSV parsing adds complexity with no benefit given the two-sheet requirement |
| Minimum 10 telemetry rows required | Insufficient data produces unreliable rolling features and model training |
| CriteriaConfig from Claude is a draft until `POST /upload/approve-criteria` sets `bundle["approved"] = True` | Claude's output must be human-validated before it drives any risk/RUL calculation |
| `POST /upload/predict-all` loads `criteria_config` only from the approved model bundle, never the request body | Prevents an unapproved or stale config from ever driving predictions |
| `primary_column` and sensor assignments are read-only in the criteria review screen | Changing them would invalidate the already-trained XGBoost model |
| Editing thresholds/names/default scores in the review screen never retriggers Claude | The model stays trained; only the SME-editable fields change |
| `threshold_breach_detector.py` is pure deterministic math, no API call | Breach detection must run on every scoring cycle without Anthropic cost or latency |
| `breach_explainer.py` is only called on demand (Breach Alerts button), and skips low-severity breaches | Claude explanations are expensive; only medium/high severity warrants one |
| Multi-sensor trend/correlation/breach features computed identically in `dynamic_aggregator.py`/`dynamic_train.py` and at inference | Prevents train/inference feature skew; all new features append to the end of the vector, never reorder existing positions |
| `store_criteria_config()` never overwrites an existing file -- always writes a new `{asset_type}_{timestamp}.json` | Preserves the full inference history per asset type, not just the latest |
| Every `POST /upload/approve-criteria` call is logged to `docs/audit_log.jsonl` via `rag/audit_log.py` | Auditable record of exactly what Claude suggested vs. what the human approved |
| `log_approval()` never raises -- logs a warning and returns `""` on failure | Audit logging must never block the approval it's recording |
| `mtbf_mtbm.py` is pure deterministic math, no API call | MTBF/MTBM/replace-vs-maintain must run on every scoring cycle without Anthropic cost or latency |
| MTBF/MTBM are simplified heuristic approximations, not full Weibull models | Explicitly scoped as such; do not add statistical reliability modeling without being asked |
| `Dashboard.jsx` renders only the uploaded asset mode; default-fleet components/hooks are kept on disk but not imported | Default fleet backend endpoints remain available for direct API use by the AI team |

---

## Key Conventions

- All Python files: snake_case
- All React components: PascalCase. Hooks and utils: camelCase
- Internal scoring: 1-10. AHP output: 1-9 Saaty scale
- Higher score = higher risk across all 5 criteria
- CR > 0.10 must always surface a warning -- never silently proceed
- clamp() and convert_to_saaty() live in ahp/criteria_scoring.py
- No em dashes in UI
- RUL displayed in **days** in the UI (Math.round(rul_years * 365)), backend always returns years
- RUL color thresholds: green > 365 days, yellow 180-365 days, red < 180 days
- Progress bar max = 7300 days (20 years * 365)
- Test RMSE displayed in **days** in UploadPanel's training summary (Math.round(test_rmse * 365)), same day-conversion convention as RUL; backend (`dynamic_train.py`) always returns years
- Composite Stress Index is clamped to [0, 1] at the display layer (`Math.min(1, Math.max(0, value))`) before both the progress bar width and the text label -- the raw computed value can exceed 1

---

## Dev Server Setup

```
Backend:  uvicorn main:app --reload  ->  http://localhost:8000
Frontend: cd frontend && npm run dev ->  http://localhost:5173
Vite proxies /ahp/*, /rul/*, /upload/*, and /rag/* to http://localhost:8000
```

Prerequisites before starting backend:
```
pip install -r requirements.txt
python data/generate_maintenance_log.py   (generates telemetry + maintenance log)
python -m rul.train                       (generates rul/model.pkl)
python -m rag.ingest                      (optional: builds RAG knowledge base)
macOS: brew install libomp                (required for XGBoost)
```

Run tests:
```
python -m pytest tests/
```

The dynamic model (`rul/dynamic_model.pkl`) is not run at startup. It is trained automatically when a file is uploaded via the dashboard's uploaded asset mode.

The RAG knowledge base (`rag/chroma_db/`) is optional. If not built, the upload pipeline and explainer work identically to before -- RAG retrieval returns `retrieval_available=False` and no context is injected. To populate it, place PDF manuals in `docs/manuals/` and/or failure case markdown in `docs/failure_cases/`, then run `python -m rag.ingest`. Use `--rebuild` to force a full rebuild. CriteriaConfigs are stored automatically in `rag/stored_configs/` after each successful upload analysis.

---

## Deployment

The app is deployed on Railway as a single service. FastAPI serves 
both the API and the built React frontend.

Build and start command are configured in railway.toml:
- Build: installs Python deps, builds React frontend, generates 
  telemetry data, trains RUL model
- Start: uvicorn main:app --host 0.0.0.0 --port $PORT

Required environment variables on Railway:
  ANTHROPIC_API_KEY — Anthropic API key
  VITE_API_BASE_URL — leave empty in production

To redeploy after making changes:
  git push origin main
Railway auto-detects the push and redeploys automatically.

Frontend is built to frontend/dist/ and served from FastAPI via 
StaticFiles mount in main.py. In production all API requests use 
relative paths (no VITE_API_BASE_URL needed).

The dynamic model (rul/dynamic_model.pkl) and RAG knowledge base 
(rag/chroma_db/) are regenerated on each deploy via the build 
command. To persist them across deploys, add a Railway volume 
mounted at /app/rul and /app/rag.
