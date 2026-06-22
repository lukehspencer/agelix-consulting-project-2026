from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from rul.feature_engineering import build_feature_vector, validate_feature_vector
from rul.ml_rul_model import predict
from rul.rul_explainer import explain

router = APIRouter(prefix="/rul", tags=["RUL"])

_CR_THRESHOLD = 0.10
_CR_ERROR = (
    "AHP matrix is inconsistent (CR > 0.10). "
    "Revise pairwise comparisons before requesting RUL predictions."
)


class PredictInput(BaseModel):
    pump: dict
    weights: list[float]
    scores: list[float]
    cr: float

    @field_validator("weights", "scores")
    @classmethod
    def must_be_length_5(cls, v: list) -> list:
        if len(v) != 5:
            raise ValueError("must have exactly 5 elements")
        return v


class ExplainInput(BaseModel):
    pump: dict
    weights: list[float]
    scores: list[float]
    risk_factor: float
    predicted_rul: float
    ci_low: float
    ci_high: float
    cr: float

    @field_validator("weights", "scores")
    @classmethod
    def must_be_length_5(cls, v: list) -> list:
        if len(v) != 5:
            raise ValueError("must have exactly 5 elements")
        return v


@router.post("/predict")
def predict_rul(body: PredictInput) -> dict:
    if body.cr > _CR_THRESHOLD:
        raise HTTPException(status_code=400, detail=_CR_ERROR)

    try:
        vector = build_feature_vector(body.pump, body.weights, body.scores)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        validate_feature_vector(vector)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        result = predict(vector)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return {
        "asset_id": body.pump.get("asset_id", ""),
        "rul_years": result["rul_years"],
        "ci_low": result["ci_low"],
        "ci_high": result["ci_high"],
    }


@router.post("/explain")
def explain_rul(body: ExplainInput) -> dict:
    if body.cr > _CR_THRESHOLD:
        raise HTTPException(status_code=400, detail=_CR_ERROR)

    try:
        text = explain(
            pump=body.pump,
            weights=body.weights,
            scores=body.scores,
            risk_factor=body.risk_factor,
            predicted_rul=body.predicted_rul,
            ci_low=body.ci_low,
            ci_high=body.ci_high,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {
        "asset_id": body.pump.get("asset_id", ""),
        "explanation": text,
    }
