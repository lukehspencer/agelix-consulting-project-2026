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
from rul.mtbf_mtbm import calculate_mtbf, calculate_mtbm, calculate_replace_vs_maintain
from rul.physics_rul import assess_consensus
from rul.consensus_rul import select_rul
from rul import model_registry
from data.column_resolver import get_sensor_columns
from rag.retriever import retrieve_for_schema_inference, retrieve_for_explanation
from rag.knowledge_base import store_criteria_config
from rag.audit_log import log_approval, get_audit_log

router = APIRouter(prefix="/upload", tags=["Upload"])

_UPLOAD_DIR = Path("data/raw/uploads")
_FAILURE_CASES_DIR = Path("docs/failure_cases")
_CR_THRESHOLD = 0.10
_PM_INTERVAL_MIN_DAYS = 7
_PM_INTERVAL_MAX_DAYS = 730
_PM_INTERVAL_DEFAULT_DAYS = 90


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


def _sensor_warn_crit(criteria_config: dict) -> dict:
    """Maps sensor column -> (warning, critical) numeric bounds, derived from
    each non-manual criterion's `thresholds` list: the warning boundary is
    the `max` of the last "safe" band (score <= 3, same convention as
    ahp/threshold_breach_detector.py's safe/risk boundary), critical is the
    `max` of the first band beyond it. Used to populate rul_explainer.py's
    CURRENT SENSOR READINGS section with real per-sensor thresholds instead
    of a bare value.
    """
    bounds = {}
    for crit in (criteria_config or {}).get("criteria", []):
        if crit.get("manual_input"):
            continue
        col = crit.get("primary_column")
        thresholds = crit.get("thresholds", [])
        if not col or not thresholds:
            continue

        safe_max = None
        risk_max = None
        for t in thresholds:
            if "max" not in t:
                continue
            if t.get("score", 0) <= 3:
                safe_max = t["max"]
            elif risk_max is None:
                risk_max = t["max"]

        if safe_max is not None:
            bounds[col] = (safe_max, risk_max if risk_max is not None else safe_max)

    return bounds


def _build_asset_context(body: "ExplainInput") -> dict:
    """Assembles the rich, per-asset context rul_explainer.explain() needs
    for a specific, data-driven assessment -- built from the full asset
    result returned by POST /upload/predict-all (`body.pump`, expected to
    include rul_days/rul_ml_days/rul_physics_days/consensus/breaches/mtbm
    and the raw sensor/rolling-mean columns) plus the approved CriteriaConfig
    the frontend sends alongside it.
    """
    pump = body.pump or {}
    criteria_config = body.criteria_config or {}
    criteria = criteria_config.get("criteria", [])

    id_to_name = {c.get("id"): c.get("name", c.get("id")) for c in criteria}
    raw_scores = pump.get("scores") or {}
    criterion_scores = {id_to_name.get(cid, cid): score for cid, score in raw_scores.items()}

    ordered_names = [id_to_name.get(c.get("id"), c.get("id")) for c in criteria]
    if ordered_names and len(ordered_names) == len(body.weights):
        criterion_weights = dict(zip(ordered_names, body.weights))
    else:
        criterion_weights = {f"C{i + 1}": w for i, w in enumerate(body.weights)}

    sensor_readings = []
    for col, (warn, crit) in _sensor_warn_crit(criteria_config).items():
        value = pump.get(f"rolling_{col}_mean", pump.get(col))
        if value is not None:
            sensor_readings.append((col, value, warn, crit))

    # CI is a fixed +-182 day band around the primary/selected rul_days --
    # same convention as DynamicAssetTable.jsx's computeCiDays(), so the
    # explanation never cites a different range than what's on screen.
    rul_days = pump.get("rul_days")
    ci_low_days = max(0, round(rul_days - 182)) if rul_days is not None else None
    ci_high_days = round(rul_days + 182) if rul_days is not None else None

    mtbm = pump.get("mtbm") or {}

    return {
        "asset_id": pump.get("asset_id", "unknown"),
        "asset_type": body.asset_type,
        "snapshot_date": pump.get("snapshot_date", "unknown"),
        "days_since_last_event": pump.get("days_since_last_event", "unknown"),
        "predicted_rul_days": rul_days,
        "predicted_rul_years": (rul_days / 365) if rul_days is not None else None,
        "primary_source": pump.get("rul_primary_source"),
        "ml_rul_days": pump.get("rul_ml_days"),
        "physics_rul_days": pump.get("rul_physics_days"),
        "ci_low_days": ci_low_days,
        "ci_high_days": ci_high_days,
        "consensus": pump.get("consensus"),
        "risk_factor": body.risk_factor,
        "criterion_scores": criterion_scores,
        "criterion_weights": criterion_weights,
        "sensor_readings": sensor_readings,
        "breaches": pump.get("breaches") or [],
        "failure_modes": body.failure_modes or criteria_config.get("failure_modes") or [],
        "next_pm_date": mtbm.get("next_maintenance_date"),
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
    approved_criteria_config: dict | None = None
    prediction_schema_summary: dict | None = None

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
    criteria_config: dict = None

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
    file_path: str | None = None
    previous_config: dict | None = None
    approved_pm_interval_days: int | None = None


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

    # Prediction mode: no RUL target column -- use the pre-trained model's
    # CriteriaConfig directly so the feature vector always matches what the
    # model was built on, regardless of what Claude might infer from a
    # fresh schema inference of the uploaded file.
    if not schema_summary.get("has_rul_column"):
        model_path = model_registry.find_model("")
        if model_path is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "No pre-trained model found. "
                    "Train a model first using:\n"
                    "python -m rul.dynamic_train_cli --file <historical_data.xlsx>"
                ),
            )

        bundle = model_registry.get_model_bundle(model_path)
        criteria_config = bundle["criteria_config"]

        bundle_sensor_cols = sorted(bundle["schema_summary"].get("sensor_columns", []))
        upload_sensor_cols = sorted(schema_summary.get("sensor_columns", []))
        if bundle_sensor_cols != upload_sensor_cols:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Uploaded file sensor columns do not match pre-trained model.\n"
                    f"Model expects: {bundle_sensor_cols}\n"
                    f"File has: {upload_sensor_cols}"
                ),
            )

        try:
            snapshots = aggregate_uploaded_data(
                str(file_path), schema_summary, criteria_config,
                prediction_mode=True,
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

        model_asset_type = criteria_config.get("asset_type", "unknown")
        return {
            "mode": "prediction",
            "criteria_config": criteria_config,
            "criteria_source": "pre_trained_model",
            "schema_summary": schema_summary,
            "prediction_schema_summary": schema_summary,
            "training_result": None,
            "assets": assets,
            "model_path": model_path,
            "model_used": model_path,
            "model_asset_type": model_asset_type,
            "feature_count": len(bundle.get("feature_names", [])),
        }

    # Training mode: RUL target column present -- call Claude to infer AHP
    # criteria and train a fresh model on this historical run-to-failure data.
    retrieved_context = retrieve_for_schema_inference(schema_summary)

    try:
        criteria_config = infer_criteria_config(
            schema_summary, retrieved_context, file_path=str(file_path)
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        store_criteria_config(criteria_config, criteria_config.get("asset_type", "unknown"))
    except Exception:
        pass

    try:
        snapshots = aggregate_uploaded_data(
            str(file_path), schema_summary, criteria_config,
            prediction_mode=False,
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

    try:
        model_output_path = model_registry.model_path_for_asset_type(
            criteria_config.get("asset_type", "unknown"),
        )
        training_result = train_dynamic_model(
            str(file_path), schema_summary, criteria_config,
            model_output_path=model_output_path,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    _generate_failure_case(criteria_config, training_result)

    return {
        "mode": "training",
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

    # Column name lookups must always reflect the file actually being scored,
    # not the bundle's historical training file -- a later prediction-mode
    # upload of the same asset type can use different column names (e.g.
    # "Event_Date" vs. the training file's "Event_Timestamp"), and
    # aggregate_uploaded_data() indexes the dataframe directly by these names.
    # The client sends the schema it detected from its own prediction file
    # (returned by /upload/analyze as prediction_schema_summary); fall back to
    # the bundle's schema_summary when it's absent (e.g. weight-only re-runs
    # against the training file itself, or older callers).
    schema_summary = (
        body.prediction_schema_summary
        if body.prediction_schema_summary is not None
        else bundle["schema_summary"]
    )

    # A criteria config passed directly (the client's currently-approved config)
    # lets weight-only re-runs skip a full re-approval cycle. Falling back to the
    # bundle still requires that bundle to have been approved at least once --
    # first approval is always required before any prediction can run.
    if body.approved_criteria_config is not None:
        criteria_config = body.approved_criteria_config
        try:
            _validate_approved_criteria(criteria_config, schema_summary)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    else:
        if not bundle.get("approved", False):
            raise HTTPException(
                status_code=400,
                detail="Criteria have not been approved. Complete the review step before running predictions.",
            )
        criteria_config = bundle["criteria_config"]

    # PM interval always comes from the config/bundle, never a bare literal --
    # the SME-approved interval if one was set at approval time, else Claude's
    # recommended interval from schema inference, else the last-resort default.
    current_interval_days = bundle.get(
        "approved_pm_interval_days",
        criteria_config.get("recommended_pm_interval_days", _PM_INTERVAL_DEFAULT_DAYS),
    )

    prediction_mode = not schema_summary.get("has_rul_column", True)

    try:
        snapshots = aggregate_uploaded_data(
            file_path=body.file_path,
            schema_summary=schema_summary,
            criteria_config=criteria_config,
            prediction_mode=prediction_mode,
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

        mtbf_result = calculate_mtbf(snap, criteria_config)

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

        # Compare the same calibrated/adjusted RUL shown elsewhere in this
        # response (not the raw pre-calibration value) against the physics
        # projection, so the consensus assessment matches what the user
        # actually sees in the RUL column.
        physics = snap.get("physics_projection", {})
        physics_rul_days = physics.get("physics_rul_days")
        physics_confidence = physics.get("confidence", "low")
        ml_rul_days = round(prediction["rul_years"] * 365)
        consensus = assess_consensus(ml_rul_days, physics_rul_days)
        if "sensor_projections" in physics:
            physics["consensus_with_ml"] = consensus

        # Picks a single "best" RUL estimate (ML, physics, or their average)
        # based on model agreement and physics data quality, rather than
        # always blending -- see rul/consensus_rul.py.
        selection = select_rul(
            ml_rul_days=ml_rul_days,
            physics_rul_days=physics_rul_days,
            consensus=consensus,
            physics_confidence=physics_confidence,
        )

        # PM interval is primarily driven by this asset's own predicted RUL
        # (see rul/mtbf_mtbm.py) -- computed after select_rul() so it can use
        # the primary/selected estimate, not the raw ML value.
        mtbm_result = calculate_mtbm(
            mtbf_days=mtbf_result["mtbf_days"],
            risk_factor=risk_factor,
            current_interval_days=current_interval_days,
            rul_days=selection["primary_rul_days"],
        )
        replace_maintain = calculate_replace_vs_maintain(
            mtbf_days=mtbf_result["mtbf_days"],
            maintenance_cost_last_year=snap.get("maintenance_cost_last_year", 0),
            asset_snapshot=snap,
        )

        results.append({
            "asset_id": snap["asset_id"],
            "snapshot_date": snap.get("snapshot_date", ""),
            "scores": scores_result,
            "raw_scores": raw_scores,
            "risk_factor": round(risk_factor, 4),
            "weighted_scores": [round(ws, 6) for ws in weighted_scores],
            "rul_years": prediction["rul_years"],
            "rul_months": rul_months,
            "rul_raw_days": round(prediction["rul_raw"] * 365),
            "rul_calibrated": prediction["calibrated"],
            "ci_low": prediction["ci_low"],
            "ci_high": prediction["ci_high"],
            "ci_low_months": round(prediction["ci_low"] * 12, 1),
            "ci_high_months": round(prediction["ci_high"] * 12, 1),
            "correlation_summary": _build_correlation_summary(snap, criteria_config),
            "breaches": breaches,
            "breach_summary": breach_summary,
            "mtbf": mtbf_result,
            "mtbm": mtbm_result,
            "replace_vs_maintain": replace_maintain,
            "consensus": consensus,
            "physics_confidence": physics_confidence,
            "rul_days": selection["primary_rul_days"],
            "rul_primary_source": selection["primary_source"],
            "rul_ml_days": selection["ml_rul_days"],
            "rul_physics_days": selection["physics_rul_days"],
            "rul_reason": selection["reason"],
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

    asset_context = _build_asset_context(body)

    try:
        text = explain(
            asset_context=asset_context,
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
        try:
            bundle = joblib.load(body.model_path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Model not found at '{body.model_path}'.")

        schema_summary = bundle["schema_summary"]

        try:
            _validate_approved_criteria(body.criteria_config, schema_summary)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

        # On re-approval, diff against the previously approved config (if the client
        # sent one) rather than whatever is currently stored on the bundle, so the
        # change count and audit log reflect what actually changed this round.
        original_config = body.previous_config if body.previous_config is not None else bundle["criteria_config"]
        changes = _count_criteria_changes(original_config, body.criteria_config)

        bundle["criteria_config"] = body.criteria_config
        bundle["approved"] = True

        pm_days = body.approved_pm_interval_days
        if pm_days is not None and _PM_INTERVAL_MIN_DAYS <= pm_days <= _PM_INTERVAL_MAX_DAYS:
            bundle["approved_pm_interval_days"] = pm_days

        joblib.dump(bundle, body.model_path)

        config_path = None
        try:
            config_path = store_criteria_config(
                body.criteria_config, body.criteria_config.get("asset_type", "unknown"),
            )
        except Exception:
            pass

        approved_at = log_approval(
            file_path=body.file_path,
            config_filename=config_path.name if config_path else None,
            asset_type=body.criteria_config.get("asset_type", "unknown"),
            original_config=original_config,
            approved_config=body.criteria_config,
            changes_count=changes,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return {
        "status": "approved",
        "criteria_config": body.criteria_config,
        "changes_from_original": changes,
        "approved_pm_interval_days": bundle.get("approved_pm_interval_days"),
        "approved_at": approved_at,
    }


@router.get("/audit-log")
def get_upload_audit_log():
    entries = get_audit_log()
    return {"entries": entries, "total_entries": len(entries)}


@router.get("/models")
def list_trained_models():
    return {"models": model_registry.list_models()}
