import itertools
from datetime import datetime, timezone
from pathlib import Path

import joblib
from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel, field_validator

from data.upload_schema import validate_upload, UploadValidationError
from data.schema_inferrer import infer_criteria_config
from data.dynamic_aggregator import aggregate_uploaded_data
from ahp.dynamic_criteria_scorer import score_asset_dynamic
from ahp.criteria_scoring import convert_to_saaty
from ahp.threshold_breach_detector import detect_breaches, get_breach_summary
from rul.dynamic_train import train_dynamic_model
from rul.dynamic_feature_engineering import build_dynamic_feature_vector
from rul.dynamic_ml_rul_model import predict_adjusted_dynamic
from rul.rul_explainer import explain
from rul.breach_explainer import explain_all_breaches
from data.column_resolver import get_sensor_columns
from rag.retriever import retrieve_for_schema_inference, retrieve_for_explanation
from rag.knowledge_base import store_criteria_config

router = APIRouter(prefix="/upload", tags=["Upload"])

_UPLOAD_DIR = Path("data/raw/uploads")
_FAILURE_CASES_DIR = Path("docs/failure_cases")
_CR_THRESHOLD = 0.10


def _generate_failure_case(criteria_config: dict, training_result: dict) -> None:
    try:
        _FAILURE_CASES_DIR.mkdir(parents=True, exist_ok=True)
        asset_type = criteria_config.get("asset_type", "unknown")
        safe_name = asset_type.lower().replace(" ", "_").replace("/", "_")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        file_path = _FAILURE_CASES_DIR / f"{safe_name}_{timestamp}.md"

        sensor_cols = []
        for c in criteria_config.get("criteria", []):
            if c.get("primary_column"):
                sensor_cols.append(c["primary_column"])
            for sc in c.get("secondary_columns", []):
                sensor_cols.append(sc)

        criteria_names = [c["name"] for c in criteria_config.get("criteria", [])]
        failure_modes = criteria_config.get("failure_modes", [])

        lines = [
            f"# {asset_type}",
            "",
            f"## Asset Type: {asset_type}",
            "",
            f"## Sensor Columns: {', '.join(sensor_cols)}",
            "",
            f"## Failure Modes: {', '.join(failure_modes)}",
            "",
            f"## Inferred AHP Criteria: {', '.join(criteria_names)}",
            "",
            f"## Training Results",
            f"- Train RMSE: {training_result['train_rmse']:.4f}",
            f"- Test RMSE: {training_result['test_rmse']:.4f}",
        ]

        file_path.write_text("\n".join(lines), encoding="utf-8")
    except Exception:
        pass


def _build_correlation_summary(snap: dict, criteria_config: dict) -> dict:
    sensor_cols = sorted(get_sensor_columns(criteria_config))
    pairs = []

    for col_a, col_b in itertools.combinations(sensor_cols, 2):
        val = snap.get(f"corr_{col_a}_{col_b}")
        if val is None:
            continue
        corr = float(val)
        pairs.append({
            "col_a": col_a,
            "col_b": col_b,
            "correlation": round(corr, 4),
            "direction": "co-degrading" if corr > 0 else "inverse",
        })

    top_pairs = sorted(pairs, key=lambda p: abs(p["correlation"]), reverse=True)[:5]

    return {
        "composite_stress_index": round(float(snap.get("composite_stress_index", 0.0)), 4),
        "top_correlated_pairs": top_pairs,
        "sensors_degrading_together": sum(1 for p in pairs if p["correlation"] > 0.6),
    }


def _validate_approved_criteria(criteria_config: dict, schema_summary: dict) -> None:
    criteria = criteria_config.get("criteria", [])
    if not (3 <= len(criteria) <= 7):
        raise ValueError(
            f"CriteriaConfig must have between 3 and 7 criteria, got {len(criteria)}."
        )

    valid_sensor_cols = set(schema_summary.get("sensor_columns", []))

    for crit in criteria:
        for field in ("id", "name", "description", "manual_input"):
            if field not in crit or crit[field] in (None, ""):
                raise ValueError(
                    f"Criterion '{crit.get('id', '?')}' is missing required field '{field}'."
                )

        if crit.get("manual_input"):
            continue

        primary_col = crit.get("primary_column")
        if not primary_col:
            raise ValueError(
                f"Criterion '{crit['id']}' is non-manual but missing 'primary_column'."
            )
        if primary_col not in valid_sensor_cols:
            raise ValueError(
                f"Criterion '{crit['id']}' primary_column '{primary_col}' is not one of the "
                f"original schema sensor columns: {sorted(valid_sensor_cols)}."
            )

        thresholds = crit.get("thresholds", [])
        if len(thresholds) < 2:
            raise ValueError(
                f"Criterion '{crit['id']}' must have at least 2 thresholds, got {len(thresholds)}."
            )

        for t in thresholds:
            score = t.get("score")
            if not isinstance(score, (int, float)) or isinstance(score, bool) or not (1 <= score <= 10):
                raise ValueError(
                    f"Criterion '{crit['id']}' has an invalid threshold score: {t!r}. "
                    "Every threshold score must be a number between 1 and 10."
                )


def _count_criteria_changes(original: dict, edited: dict) -> int:
    orig_by_id = {c.get("id"): c for c in original.get("criteria", [])}
    changes = 0

    for crit in edited.get("criteria", []):
        orig = orig_by_id.get(crit.get("id"), {})
        for key in ("name", "ui_label", "default_score", "thresholds", "penalties"):
            if crit.get(key) != orig.get(key):
                changes += 1

    return changes


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


class ExplainBreachInput(BaseModel):
    asset_snapshot: dict
    breaches: list[dict]
    criteria_config: dict = None
    model_path: str = "rul/dynamic_model.pkl"
    cr: float = 0.0


class ApproveCriteriaInput(BaseModel):
    criteria_config: dict
    model_path: str = "rul/dynamic_model.pkl"
    file_path: str = None


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

    retrieved_context = retrieve_for_schema_inference(schema_summary)

    try:
        criteria_config = infer_criteria_config(schema_summary, retrieved_context)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        store_criteria_config(criteria_config, criteria_config.get("asset_type", "unknown"))
    except Exception:
        pass

    try:
        training_result = train_dynamic_model(
            str(file_path), schema_summary, criteria_config,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    _generate_failure_case(criteria_config, training_result)

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

    if not bundle.get("approved", False):
        raise HTTPException(
            status_code=400,
            detail="Criteria have not been approved. Complete the review step before running predictions.",
        )

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

        n_criteria = len(criteria_config.get("criteria", []))
        saaty_list = [scores_result[f"C{i+1}"] for i in range(n_criteria)]
        weighted_scores = [body.weights[i] * saaty_list[i] for i in range(n_criteria)]
        risk_factor = sum(weighted_scores)

        breaches = detect_breaches(snap, criteria_config)
        breach_summary = get_breach_summary(breaches)

        vec = build_dynamic_feature_vector(
            snap, criteria_config, body.weights, raw_scores, breaches,
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
            "correlation_summary": _build_correlation_summary(snap, criteria_config),
            "breaches": breaches,
            "breach_summary": breach_summary,
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

    retrieved_context = retrieve_for_explanation(
        body.pump,
        {"asset_type": body.asset_type, "failure_modes": body.failure_modes or []},
        body.risk_factor,
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
            retrieved_context=retrieved_context,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {
        "asset_id": body.pump.get("asset_id", ""),
        "explanation": text,
    }


@router.post("/explain-breach")
def explain_breach_endpoint(body: ExplainBreachInput):
    if body.cr > _CR_THRESHOLD:
        raise HTTPException(
            status_code=400,
            detail="AHP matrix is inconsistent (CR > 0.10). "
                   "Revise pairwise comparisons.",
        )

    criteria_config = body.criteria_config
    if criteria_config is None:
        try:
            bundle = joblib.load(body.model_path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Model not found at '{body.model_path}'.")
        criteria_config = bundle["criteria_config"]

    retrieved_context = retrieve_for_explanation(
        body.asset_snapshot,
        criteria_config,
        body.asset_snapshot.get("risk_factor", 0.0),
    )

    breach_alerts = explain_all_breaches(
        body.asset_snapshot, body.breaches, criteria_config, retrieved_context,
    )

    return {
        "asset_id": body.asset_snapshot.get("asset_id", ""),
        "breach_alerts": breach_alerts,
    }


@router.post("/approve-criteria")
def approve_criteria(body: ApproveCriteriaInput):
    try:
        bundle = joblib.load(body.model_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Model not found at '{body.model_path}'.")

    schema_summary = bundle["schema_summary"]

    try:
        _validate_approved_criteria(body.criteria_config, schema_summary)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    changes = _count_criteria_changes(bundle["criteria_config"], body.criteria_config)

    bundle["criteria_config"] = body.criteria_config
    bundle["approved"] = True
    joblib.dump(bundle, body.model_path)

    try:
        store_criteria_config(
            body.criteria_config, body.criteria_config.get("asset_type", "unknown"),
        )
    except Exception:
        pass

    return {
        "status": "approved",
        "criteria_config": body.criteria_config,
        "changes_from_original": changes,
    }
