from datetime import timedelta

import pandas as pd

from data.column_resolver import resolve, is_failure_event


def aggregate_uploaded_data(file_path: str,
                            schema_summary: dict,
                            criteria_config: dict,
                            rolling_window: int = 7) -> list[dict]:
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

    aid_col = schema_summary["asset_id_column"]
    date_col = schema_summary["date_column"]
    rul_col = schema_summary["rul_column"]
    hours_col = schema_summary["operating_hours_column"]
    sensor_cols = schema_summary["sensor_columns"]

    log_aid_col = schema_summary.get("log_asset_id_column")
    log_date_col = schema_summary.get("log_date_column")

    df_tel[date_col] = pd.to_datetime(df_tel[date_col])
    df_tel = df_tel.sort_values([aid_col, date_col]).reset_index(drop=True)

    if log_date_col and len(df_log) > 0:
        df_log[log_date_col] = pd.to_datetime(df_log[log_date_col])

    results = []

    for asset_id in sorted(df_tel[aid_col].dropna().astype(str).unique()):
        asset_tel = df_tel[df_tel[aid_col].astype(str) == asset_id].copy()
        asset_tel = asset_tel.sort_values(date_col).reset_index(drop=True)

        if len(asset_tel) == 0:
            continue

        for col in sensor_cols:
            asset_tel[f"rolling_{col}_mean"] = (
                asset_tel[col].rolling(rolling_window, min_periods=1).mean()
            )
            asset_tel[f"rolling_{col}_std"] = (
                asset_tel[col].rolling(rolling_window, min_periods=1).std().fillna(0.0)
            )

        snapshot_idx = int(len(asset_tel) * 0.7)
        snapshot = asset_tel.iloc[snapshot_idx]
        snapshot_date = snapshot[date_col]
        snapshot_dict = snapshot.to_dict()

        snapshot_out = {
            "asset_id": str(asset_id),
            "snapshot_date": str(snapshot_date.date()) if hasattr(snapshot_date, 'date') else str(snapshot_date),
            "total_runtime_hours": float(snapshot_dict.get(hours_col, 0)),
            "true_rul_days": float(snapshot_dict.get(rul_col, 0)),
        }

        for col in sensor_cols:
            snapshot_out[col] = float(snapshot_dict.get(col, 0))

        for col in sensor_cols:
            mean_key = f"rolling_{col}_mean"
            std_key = f"rolling_{col}_std"
            snapshot_out[mean_key] = round(float(snapshot_dict.get(mean_key, 0)), 4)
            snapshot_out[std_key] = round(float(snapshot_dict.get(std_key, 0)), 4)

        failures_90 = 0
        days_since = 999
        total_failures = 0

        if log_aid_col and len(df_log) > 0:
            asset_log = df_log[df_log[log_aid_col].astype(str) == asset_id]

            for _, log_row in asset_log.iterrows():
                row_dict = log_row.to_dict()
                if is_failure_event(row_dict, criteria_config):
                    total_failures += 1
                    if log_date_col and log_date_col in row_dict:
                        event_date = pd.to_datetime(row_dict[log_date_col])
                        if event_date >= snapshot_date - timedelta(days=90):
                            failures_90 += 1

            if log_date_col and len(asset_log) > 0:
                log_dates = pd.to_datetime(asset_log[log_date_col])
                most_recent = log_dates.max()
                if pd.notna(most_recent):
                    delta = (snapshot_date - most_recent).days
                    days_since = max(0, delta)

        snapshot_out["failures_last_90_days"] = failures_90
        snapshot_out["days_since_last_event"] = days_since
        snapshot_out["total_failure_count"] = total_failures

        results.append(snapshot_out)

    return results
