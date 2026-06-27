from pathlib import Path

import joblib
from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, field_validator

from data.upload_schema import validate_upload, UploadValidationError
from data.schema_inferrer import infer_criteria_config
from data.dynamic_aggregator import aggregate_uploaded_data
from ahp.dynamic_criteria_scorer import score_asset_dynamic
from ahp.criteria_scoring import convert_to_saaty
from rul.dynamic_train import train_dynamic_model
from rul.dynamic_feature_engineering import build_dynamic_feature_vector
from rul.dynamic_ml_rul_model import predict_adjusted_dynamic
from rul.rul_explainer import explain
from data.column_resolver import get_sensor_columns

router = APIRouter(prefix="/upload", tags=["Upload"])

_UPLOAD_DIR = Path("data/raw/uploads")
_CR_THRESHOLD = 0.10


class PredictAllInput(BaseModel):
    file_path: str
    weights: list[float]
    cr: float
    manual_scores: dict
    model_path: str = "rul/dynamic_model.pkl"

    @field_validator("weights")
    @classmethod
    def must_be_3_to_7(cls, v):
        if not (3 <= len(v) <= 7):
            raise ValueError("weights must have 3-7 elements")
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
    asset_type: str = "KSB Calio 30-40"
    failure_modes: list[str] = None
    sensor_context: dict = None

    @field_validator("weights", "scores")
    @classmethod
    def must_be_3_to_7(cls, v):
        if not (3 <= len(v) <= 7):
            raise ValueError("must have 3-7 elements")
        return v


@router.post("/analyze")
async def analyze_upload(file: UploadFile):
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_path = _UPLOAD_DIR / file.filename
    content = await file.read()
    file_path.write_bytes(content)

    try:
        schema_summary = validate_upload(str(file_path))
    except UploadValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        criteria_config = infer_criteria_config(schema_summary)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        training_result = train_dynamic_model(
            str(file_path), schema_summary, criteria_config,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        snapshots = aggregate_uploaded_data(
            str(file_path), schema_summary, criteria_config,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    default_manual = {
        c["id"]: c["default_score"]
        for c in criteria_config["criteria"] if c.get("manual_input")
    }

    assets = []
    for snap in snapshots:
        try:
            result = score_asset_dynamic(snap, criteria_config, default_manual)
            raw_scores = result.pop("raw_scores")
            assets.append({
                "asset_id": snap["asset_id"],
                "snapshot_date": snap.get("snapshot_date", ""),
                "scores": result,
                "raw_scores": raw_scores,
                "rul_years": None,
                "rul_months": None,
                **{k: v for k, v in snap.items()
                   if k not in ("asset_id", "snapshot_date")},
            })
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    return {
        "criteria_config": criteria_config,
        "schema_summary": schema_summary,
        "training_result": {
            "train_rmse": training_result["train_rmse"],
            "test_rmse": training_result["test_rmse"],
            "n_train_samples": training_result["n_train_samples"],
            "n_test_samples": training_result["n_test_samples"],
        },
        "assets": assets,
        "model_path": training_result["model_path"],
    }


@router.post("/predict-all")
def predict_all(body: PredictAllInput):
    if body.cr > _CR_THRESHOLD:
        raise HTTPException(
            status_code=400,
            detail="AHP matrix is inconsistent (CR > 0.10). "
                   "Revise pairwise comparisons.",
        )

    try:
        bundle = joblib.load(body.model_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Model not found at '{body.model_path}'.")

    criteria_config = bundle["criteria_config"]
    schema_summary = bundle["schema_summary"]

    try:
        snapshots = aggregate_uploaded_data(
            body.file_path, schema_summary, criteria_config,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    results = []
    for snap in snapshots:
        scores_result = score_asset_dynamic(snap, criteria_config, body.manual_scores)
        raw_scores = scores_result.pop("raw_scores")

        saaty_list = [scores_result[f"C{i+1}"] for i in range(5)]
        weighted_scores = [body.weights[i] * saaty_list[i] for i in range(5)]
        risk_factor = sum(weighted_scores)

        vec = build_dynamic_feature_vector(
            snap, criteria_config, body.weights, raw_scores,
        )

        try:
            prediction = predict_adjusted_dynamic(
                vec, risk_factor, model_path=body.model_path,
            )
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        rul_months = round(prediction["rul_years"] * 12, 1)

        results.append({
            "asset_id": snap["asset_id"],
            "snapshot_date": snap.get("snapshot_date", ""),
            "scores": scores_result,
            "raw_scores": raw_scores,
            "risk_factor": round(risk_factor, 4),
            "weighted_scores": [round(ws, 6) for ws in weighted_scores],
            "rul_years": prediction["rul_years"],
            "rul_months": rul_months,
            "ci_low": prediction["ci_low"],
            "ci_high": prediction["ci_high"],
            "ci_low_months": round(prediction["ci_low"] * 12, 1),
            "ci_high_months": round(prediction["ci_high"] * 12, 1),
            **{k: v for k, v in snap.items()
               if k not in ("asset_id", "snapshot_date")},
        })

    return {"assets": sorted(results, key=lambda x: x["risk_factor"], reverse=True)}


@router.post("/explain")
def explain_asset(body: ExplainInput):
    if body.cr > _CR_THRESHOLD:
        raise HTTPException(
            status_code=400,
            detail="AHP matrix is inconsistent (CR > 0.10). "
                   "Revise pairwise comparisons.",
        )

    try:
        text = explain(
            pump=body.pump,
            weights=body.weights,
            scores=body.scores,
            risk_factor=body.risk_factor,
            predicted_rul=body.predicted_rul,
            ci_low=body.ci_low,
            ci_high=body.ci_high,
            asset_type=body.asset_type,
            failure_modes=body.failure_modes,
            sensor_context=body.sensor_context,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {
        "asset_id": body.pump.get("asset_id", ""),
        "explanation": text,
    }
