from pathlib import Path
from datetime import timedelta

import numpy as np
import pandas as pd

_DATA_DIR = Path(__file__).parent
_TELEMETRY_PATH = _DATA_DIR / "raw" / "telemetry" / "KSB_Calio_Predictive_Maintenance_Complete.xlsx"
_MAINT_LOG_PATH = _DATA_DIR / "raw" / "maintenance" / "maintenance_log.xlsx"

_REPAIR_COSTS = {
    "Bearings": 2500,
    "Electronics": 4000,
    "Motor_Winding": 3500,
}
_DEFAULT_REPAIR_COST = 3000

_MAX_CURRENT = 0.91


def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _detect_date_column(df: pd.DataFrame) -> str:
    if "Date" in df.columns:
        return "Date"
    if "Timestamp" in df.columns:
        return "Timestamp"
    raise KeyError("Telemetry file has no 'Date' or 'Timestamp' column. "
                   f"Found columns: {list(df.columns)}")


def _load_telemetry() -> tuple[pd.DataFrame, str]:
    df = pd.read_excel(_TELEMETRY_PATH, sheet_name="Operational Telemetry", header=0)
    date_col = _detect_date_column(df)
    df[date_col] = pd.to_datetime(df[date_col])
    return df.sort_values(["Pump_ID", date_col]).reset_index(drop=True), date_col


def _load_maintenance_log() -> pd.DataFrame:
    df = pd.read_excel(_MAINT_LOG_PATH)
    df["Event_Timestamp"] = pd.to_datetime(df["Event_Timestamp"])
    df["Failed_Component"] = df["Failed_Component"].fillna("None")
    return df


def _compute_condition_score(vib_mean: float, winding_mean: float,
                             spm_mean: float, current_mean: float) -> int:
    if vib_mean < 0.5:
        base = 9
    elif vib_mean < 1.0:
        base = 7
    elif vib_mean < 2.0:
        base = 5
    elif vib_mean < 3.5:
        base = 3
    else:
        base = 1

    if winding_mean < 55:
        winding_penalty = 0
    elif winding_mean < 77:
        winding_penalty = -1
    elif winding_mean < 99:
        winding_penalty = -2
    else:
        winding_penalty = -3

    if spm_mean < 52:
        spm_penalty = 0
    elif spm_mean < 73:
        spm_penalty = -1
    elif spm_mean < 94:
        spm_penalty = -2
    else:
        spm_penalty = -3

    pct = current_mean / _MAX_CURRENT
    if pct < 0.60:
        current_penalty = 0
    elif pct < 0.75:
        current_penalty = -1
    elif pct < 0.90:
        current_penalty = -2
    else:
        current_penalty = -3

    return _clamp(base + winding_penalty + spm_penalty + current_penalty, 1, 10)


def _vibration_level(vib_mean: float) -> str:
    if vib_mean < 1.0:
        return "Normal"
    elif vib_mean <= 2.5:
        return "High"
    return "Critical"


def _bearing_condition(vib_std: float) -> str:
    if vib_std < 0.3:
        return "Good"
    elif vib_std <= 0.8:
        return "Worn"
    return "Failed"


def _seal_condition(current_7d: pd.Series) -> str:
    if len(current_7d) < 2:
        return "Good"
    x = np.arange(len(current_7d), dtype=float)
    slope = np.polyfit(x, current_7d.values, 1)[0]
    mean_val = current_7d.mean()
    if mean_val == 0:
        return "Good"
    if abs(slope) < 0.001:
        return "Good"
    if slope > 0 and abs(slope) / mean_val >= 0.10:
        return "Leaking"
    if slope > 0:
        return "Worn"
    return "Good"


def _cost_trend(current_failures: int, previous_failures: int) -> str:
    if current_failures > previous_failures + 1:
        return "Increasing"
    elif current_failures < previous_failures - 1:
        return "Decreasing"
    return "Stable"


_PUMP_OFFSETS = {
    "KSB-CALIO-3040-1000": -100,
    "KSB-CALIO-3040-1001": -200,
    "KSB-CALIO-3040-1002": -300,
    "KSB-CALIO-3040-1003": -500,
    "KSB-CALIO-3040-1004": -700,
}


def get_pump_data(c1_score: int = 7, c4_score: int = 6) -> list[dict]:
    telemetry, date_col = _load_telemetry()
    maint_log = _load_maintenance_log()

    results = []

    for pump_id in sorted(telemetry["Pump_ID"].unique()):
        pump_tel = telemetry[telemetry["Pump_ID"] == pump_id].copy()
        pump_tel = pump_tel.sort_values(date_col).reset_index(drop=True)

        offset = _PUMP_OFFSETS.get(pump_id, -365)
        snap_idx = len(pump_tel) + offset if len(pump_tel) >= abs(offset) else len(pump_tel) // 2
        snapshot_row = pump_tel.iloc[snap_idx]
        snapshot_date = snapshot_row[date_col]

        window_start = max(0, snap_idx - 7)
        last_7 = pump_tel.iloc[window_start:snap_idx]
        if len(last_7) < 2:
            last_7 = pump_tel.iloc[:snap_idx + 1].tail(7)

        rolling_vibration_mean = float(last_7["Vibration_Score"].mean())
        rolling_vibration_std = float(last_7["Vibration_Score"].std(ddof=0))
        rolling_winding_temp_mean = float(last_7["Winding_Temp_C"].mean())
        rolling_spm_temp_mean = float(last_7["SPM_Temp_C"].mean())
        rolling_current_mean = float(last_7["Current_A"].mean())

        condition_score = _compute_condition_score(
            rolling_vibration_mean, rolling_winding_temp_mean,
            rolling_spm_temp_mean, rolling_current_mean,
        )

        seal_cond = _seal_condition(last_7["Current_A"])

        total_runtime_hours = float(snapshot_row["Operating_Hours"])
        age_years = round(total_runtime_hours / 22 / 365, 2)
        temperature_celsius = float(snapshot_row["Winding_Temp_C"])
        true_rul_days = float(snapshot_row["True_RUL_Days"])

        pump_maint = maint_log[maint_log["Pump_ID"] == pump_id]

        cutoff_365 = snapshot_date - timedelta(days=365)
        failures_last_year = pump_maint[
            (pump_maint["Event_Type"] == "Failure")
            & (pump_maint["Event_Timestamp"] >= cutoff_365)
            & (pump_maint["Event_Timestamp"] <= snapshot_date)
        ]
        number_of_failures = len(failures_last_year)

        maint_before = pump_maint[
            (pump_maint["Event_Type"] == "Maintenance")
            & (pump_maint["Event_Timestamp"] <= snapshot_date)
        ]
        if len(maint_before) > 0:
            last_maint_date = maint_before["Event_Timestamp"].max()
        else:
            last_maint_date = snapshot_date - timedelta(days=90)

        days_since_maintenance = max(0, (snapshot_date - last_maint_date).days)

        cutoff_90 = snapshot_date - timedelta(days=90)
        cutoff_180 = snapshot_date - timedelta(days=180)

        current_period_failures = len(pump_maint[
            (pump_maint["Event_Type"] == "Failure")
            & (pump_maint["Event_Timestamp"] >= cutoff_90)
            & (pump_maint["Event_Timestamp"] <= snapshot_date)
        ])
        previous_period_failures = len(pump_maint[
            (pump_maint["Event_Type"] == "Failure")
            & (pump_maint["Event_Timestamp"] >= cutoff_180)
            & (pump_maint["Event_Timestamp"] < cutoff_90)
        ])

        trend = _cost_trend(current_period_failures, previous_period_failures)

        tel_up_to_snap = pump_tel.iloc[:snap_idx + 1]
        last_30_tel = tel_up_to_snap.tail(30)
        voltage_anomaly_count = int(
            ((last_30_tel["Mains_Voltage"] < 207) | (last_30_tel["Mains_Voltage"] > 253)).sum()
        )

        cost = 0
        for _, row in failures_last_year.iterrows():
            component = row["Failed_Component"]
            cost += _REPAIR_COSTS.get(component, _DEFAULT_REPAIR_COST)

        unit_number = pump_id.split("-")[-1]

        results.append({
            "asset_id": pump_id,
            "asset_name": f"KSB Calio 3040 - Unit {unit_number}",
            "manufacturer": "KSB",
            "model_number": "Calio 30-40",
            "location": "Plant 1",
            "expected_lifespan_years": 20,

            "total_runtime_hours": total_runtime_hours,
            "age_years": age_years,
            "operating_hours_per_day": 22,
            "rated_flow_rate_gpm": 30,

            "condition_score": condition_score,
            "vibration_level": _vibration_level(rolling_vibration_mean),
            "temperature_celsius": temperature_celsius,
            "seal_condition": seal_cond,
            "bearing_condition": _bearing_condition(rolling_vibration_std),

            "number_of_failures_last_3yr": number_of_failures,
            "days_since_maintenance": days_since_maintenance,
            "maintenance_frequency_days": 90,

            "maintenance_cost_last_year": cost,
            "maintenance_cost_trend": trend,

            "criticality_raw": c1_score,
            "downtime_impact_raw": c4_score,

            "rolling_vibration_mean": round(rolling_vibration_mean, 4),
            "rolling_vibration_std": round(rolling_vibration_std, 4),
            "rolling_winding_temp_mean": round(rolling_winding_temp_mean, 2),
            "rolling_spm_temp_mean": round(rolling_spm_temp_mean, 2),
            "rolling_current_mean": round(rolling_current_mean, 4),
            "voltage_anomaly_count": voltage_anomaly_count,

            "true_rul_days": true_rul_days,
        })

    return results
