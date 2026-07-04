import logging
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import root_mean_squared_error
from xgboost import XGBRegressor
import joblib

from ahp.dynamic_criteria_scorer import score_asset_dynamic
from ahp.threshold_breach_detector import detect_breaches
from data.column_resolver import get_sensor_columns, is_failure_event
from data.dynamic_aggregator import compute_correlation_features
from rul.dynamic_feature_engineering import (
    build_dynamic_feature_vector,
    get_dynamic_feature_names,
)

logger = logging.getLogger(__name__)

def _equal_weights(n):
    return [1.0 / n] * n
_ROLLING_WINDOW = 7
_TREND_WINDOW = 14


def train_dynamic_model(file_path: str,
                        schema_summary: dict,
                        criteria_config: dict,
                        manual_scores: dict = None,
                        model_output_path: str = "rul/dynamic_model.pkl") -> dict:

    aid_col = schema_summary["asset_id_column"]
    date_col = schema_summary["date_column"]
    rul_col = criteria_config["column_roles"]["rul_target"]
    hours_col = schema_summary["operating_hours_column"]
    sensor_cols = schema_summary["sensor_columns"]

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

    if rul_col not in df_tel.columns:
        raise ValueError(
            f"RUL target column '{rul_col}' not found in dataset. "
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

    ref_sensor_cols = get_sensor_columns(criteria_config)

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

            rul_val = row_dict.get(rul_col)
            if pd.isna(rul_val):
                continue

            snapshot_date = row[date_col]

            snapshot = {
                "asset_id": str(asset_id),
                "total_runtime_hours": float(row_dict.get(hours_col, 0)),
                "true_rul_days": float(rul_val),
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
                row_breaches,
            )

            X_rows.append(vec)
            y_labels.append(float(rul_val) / 365.0)
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

    print(f"Training dynamic RUL model...")
    print(f"  Total samples: {len(X)}")
    print(f"  Feature vector length: {X.shape[1]}")
    print(f"  RUL label range: {y.min():.4f} - {y.max():.4f} years")
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

    feature_names = get_dynamic_feature_names(criteria_config)
    importances = model.feature_importances_
    ranked = sorted(zip(feature_names, importances), key=lambda x: x[1], reverse=True)

    print(f"\n  Train RMSE: {train_rmse:.4f} years")
    print(f"  Test  RMSE: {test_rmse:.4f} years")
    print(f"\n  Top 10 Feature Importances:")
    for name, imp in ranked[:10]:
        print(f"    {name:<45s} {imp:.4f}")

    bundle = {
        "model": model,
        "feature_names": feature_names,
        "criteria_config": criteria_config,
        "schema_summary": schema_summary,
        "approved": False,
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
    }
