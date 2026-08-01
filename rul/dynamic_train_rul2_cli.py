"""
Train a dynamic decommissioning RUL (RUL 2) model on historical
run-to-failure data.

Usage:
  python -m rul.dynamic_train_rul2_cli --file <path_to_excel>
  python -m rul.dynamic_train_rul2_cli --file <path> --config <path_to_criteria_config.json>

The trained model is saved to rul/models/<asset_type>_rul2.pkl

A decommissioning RUL column (e.g. True_RUL_2_Years) is required in the
training file, distinct from the RUL 1 (failure) target column that
rul/dynamic_train_cli.py trains against. Unlike RUL 1, this column is
expected to already be expressed in years -- it is used as the training
label as-is, with no /365 conversion.

This is the RUL 2 counterpart to rul/dynamic_train_cli.py. It is never
called from the API or frontend -- the user-facing upload flow only
predicts against models this script (or a training-mode analyze call
for RUL 2, if one is ever added) has already produced.
"""
import argparse
import json
import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import root_mean_squared_error
from xgboost import XGBRegressor
import joblib

from ahp.dynamic_criteria_scorer import score_asset_dynamic
from ahp.threshold_breach_detector import detect_breaches
from data.column_resolver import is_failure_event
from data.dynamic_aggregator import compute_correlation_features
from data.schema_inferrer import infer_criteria_config
from data.upload_schema import UploadValidationError, validate_upload
from rag.knowledge_base import store_criteria_config
from rag.retriever import retrieve_for_schema_inference
from rul import model_registry
from rul.dynamic_feature_engineering import (
    build_dynamic_feature_vector,
    get_dynamic_feature_names,
)

_ROLLING_WINDOW = 7
_TREND_WINDOW = 14

# Keywords specific enough to identify a decommissioning RUL column even
# when a generic RUL (failure) column is also present in the same file.
_RUL2_PRIORITY_KEYWORDS = ("rul_2", "decommission", "eol")
# Same generic keywords data/upload_schema.py uses for RUL 1 detection,
# used only as a fallback once the priority keywords come up empty.
_RUL2_FALLBACK_KEYWORDS = ("rul", "remaining", "life", "ttf")


def _equal_weights(n):
    return [1.0 / n] * n


def _detect_rul2_column(columns, df, exclude=None) -> str | None:
    """Same substring-keyword + numeric-dtype heuristic as
    data/upload_schema.py's RUL column detection, extended with
    decommissioning-specific keywords. Priority keywords are checked
    across all columns first (they're specific enough to never collide
    with a RUL 1 column); the generic fallback keywords are checked only
    against columns other than the one already claimed as the RUL 1
    target, so a file with both a RUL 1 and RUL 2 column doesn't
    accidentally detect the same column twice.
    """
    exclude = exclude or set()

    for c in columns:
        cl = c.lower()
        if any(kw in cl for kw in _RUL2_PRIORITY_KEYWORDS) and pd.api.types.is_numeric_dtype(df[c]):
            return c

    for c in columns:
        if c in exclude:
            continue
        cl = c.lower()
        if any(kw in cl for kw in _RUL2_FALLBACK_KEYWORDS) and pd.api.types.is_numeric_dtype(df[c]):
            return c

    return None


def _rul2_model_path_for_asset_type(asset_type: str) -> str:
    sanitized = model_registry.sanitize_asset_type(asset_type)
    return str(Path("rul/models") / f"{sanitized}_rul2.pkl")


def train_dynamic_rul2_model(file_path: str,
                              schema_summary: dict,
                              criteria_config: dict,
                              rul2_col: str,
                              manual_scores: dict = None,
                              model_output_path: str = "rul/dynamic_rul2_model.pkl") -> dict:
    aid_col = schema_summary["asset_id_column"]
    date_col = schema_summary["date_column"]
    hours_col = schema_summary["operating_hours_column"]

    # Guard against either RUL column (RUL 1 or RUL 2) leaking into the
    # sensor feature set -- upload_schema.py's generic sensor detection
    # only excludes whichever single RUL-like column it happened to pick.
    rul1_col = schema_summary.get("rul_column")
    excluded_rul_cols = {c for c in (rul1_col, rul2_col) if c}
    sensor_cols = [c for c in schema_summary["sensor_columns"] if c not in excluded_rul_cols]

    log_aid_col = schema_summary.get("log_asset_id_column")
    log_date_col = schema_summary.get("log_date_column")

    xls = pd.ExcelFile(file_path, engine="openpyxl")
    tel_sheet = None
    log_sheet = None
    for name in xls.sheet_names:
        stripped = name.strip().lower()
        if stripped == "operational telemetry":
            tel_sheet = name
        elif stripped == "failure & maintenance logs":
            log_sheet = name

    df_tel = pd.read_excel(xls, sheet_name=tel_sheet, header=0)
    df_log = pd.read_excel(xls, sheet_name=log_sheet, header=0)

    if rul2_col not in df_tel.columns:
        raise ValueError(
            f"RUL 2 target column '{rul2_col}' not found in dataset. "
            f"Available columns: {list(df_tel.columns)}"
        )

    df_tel[date_col] = pd.to_datetime(df_tel[date_col])
    df_tel = df_tel.sort_values([aid_col, date_col]).reset_index(drop=True)

    if log_date_col and len(df_log) > 0:
        df_log[log_date_col] = pd.to_datetime(df_log[log_date_col])

    if manual_scores is None:
        manual_scores = {}
        for crit in criteria_config["criteria"]:
            if crit.get("manual_input"):
                manual_scores[crit["id"]] = crit.get("default_score", 5)

    X_rows = []
    y_labels = []
    row_asset_ids = []

    for asset_id in sorted(df_tel[aid_col].dropna().astype(str).unique()):
        asset_tel = df_tel[df_tel[aid_col].astype(str) == asset_id].copy()
        asset_tel = asset_tel.sort_values(date_col).reset_index(drop=True)

        for col in sensor_cols:
            asset_tel[f"rolling_{col}_mean"] = (
                asset_tel[col].rolling(_ROLLING_WINDOW, min_periods=1).mean()
            )
            asset_tel[f"rolling_{col}_std"] = (
                asset_tel[col].rolling(_ROLLING_WINDOW, min_periods=1).std().fillna(0.0)
            )

        asset_log = pd.DataFrame()
        if log_aid_col and len(df_log) > 0:
            asset_log = df_log[df_log[log_aid_col].astype(str) == asset_id]

        for i in range(_ROLLING_WINDOW, len(asset_tel)):
            row = asset_tel.iloc[i]
            row_dict = row.to_dict()

            rul2_val = row_dict.get(rul2_col)
            if pd.isna(rul2_val):
                continue

            snapshot_date = row[date_col]

            snapshot = {
                "asset_id": str(asset_id),
                "total_runtime_hours": float(row_dict.get(hours_col, 0)),
                "true_rul_2_years": float(rul2_val),
            }

            for col in sensor_cols:
                snapshot[col] = float(row_dict.get(col, 0))
                snapshot[f"rolling_{col}_mean"] = float(row_dict.get(f"rolling_{col}_mean", 0))
                snapshot[f"rolling_{col}_std"] = float(row_dict.get(f"rolling_{col}_std", 0))

            trend_window = asset_tel.iloc[max(0, i - _TREND_WINDOW + 1):i + 1]
            snapshot.update(compute_correlation_features(trend_window, sensor_cols))

            failures_90 = 0
            days_since = 999
            total_failures = 0

            if len(asset_log) > 0 and log_date_col:
                for _, lrow in asset_log.iterrows():
                    ldict = lrow.to_dict()
                    if is_failure_event(ldict, criteria_config):
                        total_failures += 1
                        event_date = pd.to_datetime(ldict.get(log_date_col))
                        if pd.notna(event_date) and event_date <= snapshot_date:
                            if event_date >= snapshot_date - timedelta(days=90):
                                failures_90 += 1

                log_dates = pd.to_datetime(asset_log[log_date_col])
                past_dates = log_dates[log_dates <= snapshot_date]
                if len(past_dates) > 0:
                    most_recent = past_dates.max()
                    if pd.notna(most_recent):
                        days_since = max(0, (snapshot_date - most_recent).days)

            snapshot["failures_last_90_days"] = failures_90
            snapshot["days_since_last_event"] = days_since
            snapshot["total_failure_count"] = total_failures

            scores_result = score_asset_dynamic(snapshot, criteria_config, manual_scores)
            raw_scores = scores_result["raw_scores"]

            row_breaches = detect_breaches(snapshot, criteria_config)

            vec = build_dynamic_feature_vector(
                snapshot, criteria_config,
                _equal_weights(len(criteria_config.get("criteria", []))), raw_scores,
                row_breaches, use_age_features=True,
            )

            X_rows.append(vec)
            # True_RUL_2_Years is already expressed in years -- unlike
            # RUL 1's True_RUL_Days, no /365 conversion here.
            y_labels.append(float(rul2_val))
            row_asset_ids.append(str(asset_id))

    X = np.array(X_rows)
    y = np.array(y_labels)
    asset_arr = np.array(row_asset_ids)

    unique_assets, counts = np.unique(asset_arr, return_counts=True)
    test_asset = unique_assets[np.argmax(counts)]

    train_mask = asset_arr != test_asset
    test_mask = asset_arr == test_asset

    X_train, y_train = X[train_mask], y[train_mask]
    X_test, y_test = X[test_mask], y[test_mask]

    print("Training dynamic RUL 2 (decommissioning) model...")
    print(f"  Total samples: {len(X)}")
    print(f"  Feature vector length: {X.shape[1]}")
    print(f"  RUL 2 target column: {rul2_col}")
    print(f"  RUL 2 label range: {y.min():.4f} - {y.max():.4f} years")
    print(f"  Train set: {len(X_train)} rows (assets: {sorted(set(asset_arr[train_mask]))})")
    print(f"  Test set:  {len(X_test)} rows (asset: {test_asset})")

    model = XGBRegressor(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="reg:squarederror",
        random_state=42,
    )
    model.fit(X_train, y_train)

    train_rmse = root_mean_squared_error(y_train, model.predict(X_train))
    test_rmse = root_mean_squared_error(y_test, model.predict(X_test))

    feature_names = get_dynamic_feature_names(criteria_config, use_age_features=True)
    importances = model.feature_importances_
    ranked = sorted(zip(feature_names, importances), key=lambda x: x[1], reverse=True)

    print(f"\n  Train RMSE: {train_rmse:.4f} years")
    print(f"  Test  RMSE: {test_rmse:.4f} years")
    print("\n  Top 10 Feature Importances:")
    for name, imp in ranked[:10]:
        print(f"    {name:<45s} {imp:.4f}")

    bundle = {
        "model": model,
        "feature_names": feature_names,
        "criteria_config": criteria_config,
        "schema_summary": schema_summary,
        "approved": False,
        "rul_type": "decommission",
        "rul_target_column": rul2_col,
        "use_age_features": True,
        # Max RUL 2 (years) actually observed in this asset type's own
        # training labels -- mirrors dynamic_train.py's max_train_rul_years,
        # anchoring extrapolation calibration to this model's own data
        # rather than a hardcoded engineering lifetime constant.
        "max_train_rul_years": float(y.max()),
    }

    out_path = Path(model_output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, out_path)
    print(f"\n  Model saved to {out_path}")

    return {
        "train_rmse": train_rmse,
        "test_rmse": test_rmse,
        "n_train_samples": len(X_train),
        "n_test_samples": len(X_test),
        "feature_names": feature_names,
        "model_path": str(out_path),
        "rul2_range_years": (float(y.min()), float(y.max())),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Train a dynamic decommissioning RUL (RUL 2) model on historical run-to-failure data."
    )
    parser.add_argument("--file", required=True, help="Path to the Excel training file")
    parser.add_argument("--config", default=None,
        help="Path to pre-built CriteriaConfig JSON. Skips Claude inference.")
    args = parser.parse_args()

    file_path = args.file

    print(f"Validating '{file_path}'...")
    try:
        schema_summary = validate_upload(file_path, require_rul_column=False)
    except UploadValidationError as exc:
        raise SystemExit(f"Validation failed: {exc}")

    xls = pd.ExcelFile(file_path, engine="openpyxl")
    tel_sheet = None
    for name in xls.sheet_names:
        if name.strip().lower() == "operational telemetry":
            tel_sheet = name
            break
    df_tel = pd.read_excel(xls, sheet_name=tel_sheet, header=0)

    rul1_col = schema_summary.get("rul_column")
    exclude = {rul1_col} if rul1_col else set()
    rul2_col = _detect_rul2_column(list(df_tel.columns), df_tel, exclude=exclude)
    if rul2_col is None:
        raise SystemExit(
            "Training requires a decommissioning RUL column (e.g. "
            "True_RUL_2_Years) in the telemetry sheet -- looked for numeric "
            f"columns containing: {_RUL2_PRIORITY_KEYWORDS + _RUL2_FALLBACK_KEYWORDS}. "
            f"Columns found: {list(df_tel.columns)}"
        )
    print(f"Detected RUL 2 (decommissioning) target column: '{rul2_col}'")

    if args.config:
        with open(args.config) as f:
            criteria_config = json.load(f)
        print(f"Using pre-built config from {args.config}")
    else:
        print("Inferring AHP criteria config via Claude...")
        retrieved_context = retrieve_for_schema_inference(schema_summary)
        try:
            criteria_config = infer_criteria_config(
                schema_summary, retrieved_context, file_path=file_path,
            )
        except RuntimeError as exc:
            raise SystemExit(f"Criteria inference failed: {exc}")

    try:
        store_criteria_config(criteria_config, criteria_config.get("asset_type", "unknown"))
    except Exception:
        pass

    asset_type = criteria_config.get("asset_type", "unknown_asset")
    model_output_path = _rul2_model_path_for_asset_type(asset_type)

    print(f"Training dynamic RUL 2 model for '{asset_type}'...")
    result = train_dynamic_rul2_model(
        file_path, schema_summary, criteria_config, rul2_col,
        model_output_path=model_output_path,
    )

    print("\nTraining complete.")
    print(f"  Asset type:      {asset_type}")
    print(f"  RUL 2 column:    {rul2_col}")
    print(f"  Samples:         {result['n_train_samples']} train / {result['n_test_samples']} test")
    print(f"  Train RMSE:      {result['train_rmse']:.4f} years")
    print(f"  Test RMSE:       {result['test_rmse']:.4f} years")
    lo, hi = result["rul2_range_years"]
    print(f"  RUL 2 range:     {lo:.4f} - {hi:.4f} years")
    print(f"  Model saved:     {result['model_path']}")


if __name__ == "__main__":
    main()
