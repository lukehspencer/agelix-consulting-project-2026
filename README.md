# Asset Management Dashboard -- Agelix Consulting

An asset management dashboard extending the *Assets Maestro* platform. Combines AHP (Analytic
Hierarchy Process) risk scoring with XGBoost-based Remaining Useful Life (RUL) prediction, a
physics-based degradation projection as an independent second opinion, Claude-powered GenAI
explainability, and a RAG knowledge pipeline that enriches both schema inference and RUL
explanations with domain knowledge from manuals, past failure cases, and prior approved criteria
configs.

The system ships two backend pipelines:
- **Default fleet mode** -- fixed scoring rules calibrated to 5 KSB Calio 30-40 pumps. Backend
  endpoints (`ahp/api.py`, `rul/api.py`) are fully functional and used directly by the AI team,
  but nothing in the dashboard UI renders this mode.
- **Uploaded asset mode** -- accepts any asset type's telemetry and maintenance log; Claude infers
  AHP criteria and column roles dynamically. This is the dashboard's only rendered view.

Full architecture, data flow, API contracts, and design constraints are documented in
[CLAUDE.md](CLAUDE.md) -- read that first for anything beyond a quick start.

## Getting Started

### Prerequisites
- Python 3.11
- Node.js 20
- `brew install libomp` (macOS, required for XGBoost)
- An `ANTHROPIC_API_KEY` (see `.env.example`) -- required for schema inference, RUL explanations,
  and breach alerts

### Install and seed data
```bash
pip install -r requirements.txt
cd frontend && npm install && cd ..

python data/generate_maintenance_log.py   # generates default fleet telemetry + maintenance log
python -m rul.train                       # trains rul/model.pkl (default fleet RUL model)
python -m rag.ingest                      # optional: builds the RAG knowledge base
```

### Run the dev servers
```bash
uvicorn main:app --reload                 # backend -> http://localhost:8000
cd frontend && npm run dev                # frontend -> http://localhost:5173
```
Vite proxies `/ahp/*`, `/rul/*`, `/upload/*`, and `/rag/*` to `http://localhost:8000`.

### Train a dynamic RUL model for a new asset type
Required once per asset type before a prediction-mode upload of that type will succeed:
```bash
python -m rul.dynamic_train_cli --file <path_to_historical_run_to_failure_data.xlsx>
```
The uploaded file must include a RUL target column and follow the two-sheet `.xlsx` contract
(`Operational Telemetry` + `Failure & Maintenance Logs`) described in CLAUDE.md. This is the only
way to train a dynamic model from scratch -- it's never triggered from the API or frontend. A
training-mode `POST /upload/analyze` call (uploading a file that already has a RUL column)
accomplishes the same thing.

## Build and Test

```bash
python -m pytest tests/          # backend test suite
```

The frontend is not built by the dev server config for production -- if you change anything under
`frontend/src/`, run `npm run build` inside `frontend/` and commit the resulting `frontend/dist/`
before pushing, since Railway serves that committed build directly (see CLAUDE.md > Deployment).

## Contribute

- Read [CLAUDE.md](CLAUDE.md) before making changes -- it documents the full pipeline, the
  CriteriaConfig schema, frozen files, and the design constraints behind non-obvious decisions.
- **Frozen files must never be modified** (see CLAUDE.md > Frozen Files): `ahp/criteria_scoring.py`,
  `ahp/ahp_engine.py`, `ahp/risk_calculator.py`, `rul/feature_engineering.py`,
  `rul/ml_rul_model.py`, `rul/train.py`, `data/telemetry_aggregator.py`. New functionality goes in
  new files that import from these, not edits to them.
- No file downstream of `data/schema_inferrer.py` may hardcode a column name -- all column lookups
  go through `data/column_resolver.py`.
- Run `python -m pytest tests/` before opening a PR and confirm the default fleet pipeline still
  works alongside any uploaded-mode changes.
