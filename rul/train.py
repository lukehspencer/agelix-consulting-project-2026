from pathlib import Path
from datetime import timedelta

import numpy as np
import pandas as pd
from sklearn.metrics import root_mean_squared_error
from xgboost import XGBRegressor
import joblib

from ahp.criteria_scoring import score_asset
from rul.feature_engineering import build_feature_vector, get_feature_names

_TELEMETRY_PATH = Path(__file__).parent.parent / "data" / "raw" / "telemetry" / "KSB_Calio_Predictive_Maintenance_Complete.xlsx"
_MAINT_LOG_PATH = Path(__file__).parent.parent / "data" / "raw" / "maintenance" / "maintenance_log.xlsx"
_MODEL_PATH = Path(__file__).parent / "model.pkl"

_EQUAL_WEIGHTS = [0.2, 0.2, 0.2, 0.2, 0.2]
_TRAIN_PUMPS = ["KSB-CALIO-3040-1000", "KSB-CALIO-3040-1001", "KSB-CALIO-3040-1002"]
_TEST_PUMPS = ["KSB-CALIO-3040-1003", "KSB-CALIO-3040-1004"]

_MAX_CURRENT = 0.91
_REPAIR_COSTS = {"Bearings": 2500, "Electronics": 4000, "Motor_Winding": 3500}
_DEFAULT_REPAIR_COST = 3000


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _detect_date_column(df: pd.DataFrame) -> str:
    if "Date" in df.columns:
        return "Date"
    if "Timestamp" in df.columns:
        return "Timestamp"
    raise KeyError(f"No 'Date' or 'Timestamp' column found. Columns: {list(df.columns)}")


def _compute_condition_score(vib_mean, winding_mean, spm_mean, current_mean):
    if vib_mean < 0.3:
        base = 9
    elif vib_mean < 0.5:
        base = 7
    elif vib_mean < 0.8:
        base = 5
    elif vib_mean < 1.2:
        base = 3
    else:
        base = 1

    if winding_mean < 55:
        wp = 0
    elif winding_mean < 77:
        wp = -1
    elif winding_mean < 99:
        wp = -2
    else:
        wp = -3

    if spm_mean < 52:
        sp = 0
    elif spm_mean < 73:
        sp = -1
    elif spm_mean < 94:
        sp = -2
    else:
        sp = -3

    pct = current_mean / _MAX_CURRENT
    if pct < 0.60:
        cp = 0
    elif pct < 0.75:
        cp = -1
    elif pct < 0.90:
        cp = -2
    else:
        cp = -3

    return _clamp(base + wp + sp + cp, 1, 10)


def _vibration_level(vib_mean):
    if vib_mean < 0.5:
        return "Normal"
    elif vib_mean <= 1.0:
        return "High"
    return "Critical"


def _bearing_condition(vib_std):
    if vib_std < 0.1:
        return "Good"
    elif vib_std <= 0.3:
        return "Worn"
    return "Failed"


def _seal_condition(current_7d):
    if len(current_7d) < 2:
        return "Good"
    x = np.arange(len(current_7d), dtype=float)
    slope = np.polyfit(x, current_7d.values, 1)[0]
    mean_val = current_7d.mean()
    if mean_val == 0 or abs(slope) < 0.001:
        return "Good"
    if slope > 0 and abs(slope) / mean_val >= 0.10:
        return "Leaking"
    if slope > 0:
        return "Worn"
    return "Good"


def _cost_trend(current_failures, previous_failures):
    if current_failures > previous_failures + 1:
        return "Increasing"
    elif current_failures < previous_failures - 1:
        return "Decreasing"
    return "Stable"


def train_and_save():
    telemetry = pd.read_excel(_TELEMETRY_PATH, sheet_name="Operational Telemetry", header=0)
    date_col = _detect_date_column(telemetry)
    print(f"Detected date column: '{date_col}'")
    print(f"Telemetry columns: {list(telemetry.columns)}")
    telemetry[date_col] = pd.to_datetime(telemetry[date_col])
    telemetry = telemetry.sort_values(["Pump_ID", date_col]).reset_index(drop=True)

    maint_log = pd.read_excel(_MAINT_LOG_PATH)
    maint_log["Event_Timestamp"] = pd.to_datetime(maint_log["Event_Timestamp"])
    maint_log["Failed_Component"] = maint_log["Failed_Component"].fillna("None")

    X_rows = []
    y_labels = []
    pump_ids_per_row = []

    for pump_id in sorted(telemetry["Pump_ID"].unique()):
        pump_tel = telemetry[telemetry["Pump_ID"] == pump_id].reset_index(drop=True)
        pump_maint = maint_log[maint_log["Pump_ID"] == pump_id]

        for i in range(7, len(pump_tel)):
            row = pump_tel.iloc[i]
            rul_days = row["True_RUL_Days"]
            if pd.isna(rul_days):
                continue

            window = pump_tel.iloc[i - 7:i]
            current_date = row[date_col]

            rolling_vib_mean = float(window["Vibration_Score"].mean())
            rolling_vib_std = float(window["Vibration_Score"].std(ddof=0))
            rolling_winding_mean = float(window["Winding_Temp_C"].mean())
            rolling_spm_mean = float(window["SPM_Temp_C"].mean())
            rolling_current_mean = float(window["Current_A"].mean())

            condition_score = _compute_condition_score(
                rolling_vib_mean, rolling_winding_mean,
                rolling_spm_mean, rolling_current_mean,
            )

            cutoff_365 = current_date - timedelta(days=365)
            failures_yr = pump_maint[
                (pump_maint["Event_Type"] == "Failure")
                & (pump_maint["Event_Timestamp"] >= cutoff_365)
                & (pump_maint["Event_Timestamp"] <= current_date)
            ]
            num_failures = len(failures_yr)

            maint_before = pump_maint[
                (pump_maint["Event_Type"] == "Maintenance")
                & (pump_maint["Event_Timestamp"] <= current_date)
            ]
            if len(maint_before) > 0:
                last_maint = maint_before["Event_Timestamp"].max()
                days_since_maint = max(0, (current_date - last_maint).days)
            else:
                days_since_maint = 90

            cost = 0
            if len(failures_yr) > 0:
                for _, frow in failures_yr.iterrows():
                    cost += _REPAIR_COSTS.get(frow["Failed_Component"], _DEFAULT_REPAIR_COST)
            else:
                cost = 3000

            cutoff_90 = current_date - timedelta(days=90)
            cutoff_180 = current_date - timedelta(days=180)
            cur_fail = len(pump_maint[
                (pump_maint["Event_Type"] == "Failure")
                & (pump_maint["Event_Timestamp"] >= cutoff_90)
                & (pump_maint["Event_Timestamp"] <= current_date)
            ])
            prev_fail = len(pump_maint[
                (pump_maint["Event_Type"] == "Failure")
                & (pump_maint["Event_Timestamp"] >= cutoff_180)
                & (pump_maint["Event_Timestamp"] < cutoff_90)
            ])
            trend = _cost_trend(cur_fail, prev_fail)

            last_30 = pump_tel.iloc[max(0, i - 30):i]
            voltage_anomalies = int(
                ((last_30["Mains_Voltage"] < 207) | (last_30["Mains_Voltage"] > 253)).sum()
            )

            total_hours = float(row["Operating_Hours"])
            age_years = round(total_hours / 22 / 365, 2)

            pump_dict = {
                "asset_id": pump_id,
                "total_runtime_hours": total_hours,
                "operating_hours_per_day": 22,
                "condition_score": condition_score,
                "vibration_level": _vibration_level(rolling_vib_mean),
                "seal_condition": _seal_condition(window["Current_A"]),
                "bearing_condition": _bearing_condition(rolling_vib_std),
                "age_years": age_years,
                "expected_lifespan_years": 20,
                "number_of_failures_last_3yr": num_failures,
                "days_since_maintenance": days_since_maint,
                "maintenance_frequency_days": 90,
                "criticality_raw": 7,
                "downtime_impact_raw": 6,
                "maintenance_cost_trend": trend,
                "maintenance_cost_last_year": cost,
                "rolling_vibration_mean": round(rolling_vib_mean, 4),
                "rolling_vibration_std": round(rolling_vib_std, 4),
                "rolling_winding_temp_mean": round(rolling_winding_mean, 2),
                "rolling_spm_temp_mean": round(rolling_spm_mean, 2),
                "rolling_current_mean": round(rolling_current_mean, 4),
                "voltage_anomaly_count": voltage_anomalies,
            }

            scores_dict = score_asset(pump_dict)
            scores_list = [
                scores_dict["score_criticality"],
                scores_dict["score_condition"],
                scores_dict["score_failure_probability"],
                scores_dict["score_downtime_impact"],
                scores_dict["score_maintenance_cost_trend"],
            ]

            vector = build_feature_vector(pump_dict, _EQUAL_WEIGHTS, scores_list)
            X_rows.append(vector)
            y_labels.append(float(rul_days) / 365.0)
            pump_ids_per_row.append(pump_id)

    X = np.array(X_rows)
    y = np.array(y_labels)
    pump_arr = np.array(pump_ids_per_row)

    print(f"\nTotal training samples: {len(X)}")
    print(f"  Feature matrix shape: {X.shape}")
    print(f"  RUL label range: {y.min():.4f} - {y.max():.4f} years")

    train_mask = np.isin(pump_arr, _TRAIN_PUMPS)
    test_mask = np.isin(pump_arr, _TEST_PUMPS)

    X_train, y_train = X[train_mask], y[train_mask]
    X_test, y_test = X[test_mask], y[test_mask]

    print(f"\n  Train set: {len(X_train)} rows ({_TRAIN_PUMPS})")
    print(f"  Test set:  {len(X_test)} rows ({_TEST_PUMPS})")

    model = XGBRegressor(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="reg:squarederror",
        random_state=42,
    )

    print("\nTraining XGBoost Regressor...")
    model.fit(X_train, y_train)

    train_rmse = root_mean_squared_error(y_train, model.predict(X_train))
    test_rmse = root_mean_squared_error(y_test, model.predict(X_test))

    print(f"\n  Train RMSE: {train_rmse:.4f} years")
    print(f"  Test  RMSE: {test_rmse:.4f} years")

    feature_names = get_feature_names()
    importances = model.feature_importances_
    ranked = sorted(zip(feature_names, importances), key=lambda x: x[1], reverse=True)

    print("\n  Top 10 Feature Importances:")
    for name, imp in ranked[:10]:
        print(f"    {name:<40s} {imp:.4f}")

    joblib.dump(model, _MODEL_PATH)
    print(f"\nModel saved to {_MODEL_PATH}")


if __name__ == "__main__":
    train_and_save()
