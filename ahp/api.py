import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from ahp.ahp_engine import run_ahp
from ahp.criteria_scoring import score_asset
from ahp.risk_calculator import compute_risk_factor, rank_assets

# ---------------------------------------------------------------------------
# Pump data — loaded once at import time, shared across all requests
# ---------------------------------------------------------------------------

_DATA_PATH = Path(__file__).parent.parent / "data" / "pumps.json"

with _DATA_PATH.open(encoding="utf-8") as _f:
    _PUMPS: list[dict] = json.load(_f)

# ---------------------------------------------------------------------------
# App + CORS
# ---------------------------------------------------------------------------

app = FastAPI(title="Asset Risk Dashboard — AHP Module")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

_EQUAL_WEIGHTS = [0.2, 0.2, 0.2, 0.2, 0.2]


class MatrixInput(BaseModel):
    matrix: list[list[float]]

    @field_validator("matrix")
    @classmethod
    def must_be_5x5(cls, v: list) -> list:
        if len(v) != 5 or any(len(row) != 5 for row in v):
            raise ValueError("matrix must be 5×5")
        return v


class AssetScoreInput(BaseModel):
    asset_id: str = ""
    criticality_raw: float         # C1 — manual 1–10
    condition_score: float
    vibration_level: str
    seal_condition: str
    bearing_condition: str
    age_years: float
    expected_lifespan_years: float
    number_of_failures_last_3yr: int
    days_since_maintenance: float
    maintenance_frequency_days: float
    downtime_impact_raw: float     # C4 — manual 1–10
    maintenance_cost_trend: str
    maintenance_cost_last_year: float


class RiskFactorInput(BaseModel):
    weights: list[float]
    scores: list[float]

    @field_validator("weights", "scores")
    @classmethod
    def must_be_length_5(cls, v: list) -> list:
        if len(v) != 5:
            raise ValueError("weights and scores must each have exactly 5 elements")
        return v

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/ahp/calculate-weights")
def calculate_weights(body: MatrixInput) -> dict:
    """Accept a 5×5 pairwise comparison matrix and return AHP weights + CR.

    The caller fills the upper triangle and diagonal (all 1s on diagonal).
    Reciprocals are auto-filled internally.

    Returns weights [w1–w5], lambda_max, CI, CR, and a valid flag (CR ≤ 0.10).
    """
    return run_ahp(body.matrix)


@app.post("/ahp/score-asset")
def score_asset_endpoint(body: AssetScoreInput) -> dict:
    """Derive the five C1–C5 Saaty scores for a single pump from its raw variables.

    C1 (criticality_raw) and C4 (downtime_impact_raw) are manual 1–10 inputs.
    C2, C3, and C5 are derived from the pump's operational and condition data.
    """
    return score_asset(body.model_dump())


@app.post("/ahp/risk-factor")
def risk_factor_endpoint(body: RiskFactorInput) -> dict:
    """Compute the risk factor (dot product) for one pump given weights and scores.

    Returns the scalar risk_factor plus the per-criterion weighted_scores list.
    """
    return compute_risk_factor(body.weights, body.scores)


@app.get("/ahp/assets")
def get_assets(
    weights: list[float] = Query(default=_EQUAL_WEIGHTS),
) -> list[dict]:
    """Return all pumps ranked highest → lowest by risk factor.

    Pass the current AHP weight vector as repeated query params:
      GET /ahp/assets?weights=0.3&weights=0.25&weights=0.2&weights=0.15&weights=0.1

    Defaults to equal weights (0.2 each) when no weights are provided,
    so the endpoint is usable before the user has submitted a matrix.
    """
    if len(weights) != 5:
        raise HTTPException(
            status_code=400,
            detail=f"Expected 5 weights, got {len(weights)}.",
        )
    return rank_assets(weights, _PUMPS)
