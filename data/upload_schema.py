import pandas as pd


class UploadValidationError(Exception):
    pass


_TELEMETRY_SHEET = "Operational Telemetry"
_LOG_SHEET = "Failure & Maintenance Logs"

_RUL_KEYWORDS = ("rul", "remaining", "life", "ttf")
_HOURS_KEYWORDS = ("hour", "runtime", "operating", "cycles", "cumulative")
_DATE_KEYWORDS = ("date", "time", "timestamp", "datetime")
_EVENT_KEYWORDS = ("event", "type", "status", "category")


def _match_sheet(sheet_names, target):
    for name in sheet_names:
        if name.strip().lower() == target.lower():
            return name
    return None


def _detect_id_column(columns, cross_ref_columns=None):
    id_candidates = [c for c in columns if "id" in c.lower()]
    if id_candidates and cross_ref_columns:
        cross_lower = {c.lower() for c in cross_ref_columns}
        for candidate in id_candidates:
            if candidate.lower() in cross_lower:
                return candidate
    if id_candidates:
        return id_candidates[0]
    return None


def _detect_id_column_fallback(columns, df):
    for c in columns:
        if df[c].dtype == object:
            return c
    return None


def _detect_date_column(columns, df):
    candidates = [c for c in columns
                  if any(kw in c.lower() for kw in _DATE_KEYWORDS)]
    for c in candidates:
        try:
            parsed = pd.to_datetime(df[c], format="mixed", dayfirst=False)
            fail_rate = parsed.isna().sum() / max(len(df), 1)
            if fail_rate <= 0.10:
                return c, parsed
        except Exception:
            continue
    return None, None


def _detect_role_column(columns, keywords, df):
    for c in columns:
        cl = c.lower()
        if any(kw in cl for kw in keywords):
            if pd.api.types.is_numeric_dtype(df[c]):
                return c
    return None


def _detect_event_column(columns):
    for c in columns:
        cl = c.lower()
        if any(kw in cl for kw in _EVENT_KEYWORDS):
            if "date" not in cl and "timestamp" not in cl:
                return c
    return None


def validate_upload(file_path: str, require_rul_column: bool = False) -> dict:
    try:
        xls = pd.ExcelFile(file_path, engine="openpyxl")
    except Exception as exc:
        raise UploadValidationError(f"Cannot open file: {exc}") from exc

    xl = pd.ExcelFile(file_path)
    print(f"DEBUG sheet names found: {xl.sheet_names}")

    tel_sheet = _match_sheet(xls.sheet_names, _TELEMETRY_SHEET)
    if tel_sheet is None:
        raise UploadValidationError(
            f"Missing required sheet '{_TELEMETRY_SHEET}'. "
            f"Found sheets: {xls.sheet_names}"
        )

    log_sheet = _match_sheet(xls.sheet_names, _LOG_SHEET)
    if log_sheet is None:
        raise UploadValidationError(
            f"Missing required sheet '{_LOG_SHEET}'. "
            f"Found sheets: {xls.sheet_names}"
        )

    df_tel = pd.read_excel(xls, sheet_name=tel_sheet, header=0)
    df_log = pd.read_excel(file_path, sheet_name="Failure & Maintenance Logs")
    if df_log.empty or len(df_log.columns) == 0:
        df_log = pd.read_excel(file_path, sheet_name="Failure & Maintenance Logs", header=1)
    if df_log.empty or len(df_log.columns) == 0:
        df_log = pd.read_excel(file_path, sheet_name="Failure & Maintenance Logs", header=2)

    print(f"DEBUG df_log after fix columns: {list(df_log.columns)}")
    print(f"DEBUG df_log shape: {df_log.shape}")

    print(f"DEBUG log sheet columns: {list(df_log.columns)}")
    print(f"DEBUG log sheet shape: {df_log.shape}")
    print(f"DEBUG log sheet head:\n{df_log.head()}")

    if len(df_tel) < 10:
        raise UploadValidationError(
            f"Telemetry sheet has only {len(df_tel)} rows. Minimum 10 required."
        )

    tel_cols = list(df_tel.columns)
    log_cols = list(df_log.columns)

    # --- Asset ID column ---
    asset_id_col = _detect_id_column(tel_cols, cross_ref_columns=log_cols)
    if asset_id_col is None:
        asset_id_col = _detect_id_column_fallback(tel_cols, df_tel)
    if asset_id_col is None:
        raise UploadValidationError(
            f"Cannot detect asset ID column in telemetry. "
            f"Columns found: {tel_cols}"
        )

    # --- Date column ---
    date_col, parsed_dates = _detect_date_column(tel_cols, df_tel)
    if date_col is None:
        raise UploadValidationError(
            f"Cannot detect date column in telemetry. "
            f"Looked for columns containing: {_DATE_KEYWORDS}. "
            f"Columns found: {tel_cols}"
        )
    df_tel[date_col] = parsed_dates

    # --- RUL target column ---
    rul_col = _detect_role_column(tel_cols, _RUL_KEYWORDS, df_tel)
    if rul_col is None and require_rul_column:
        raise UploadValidationError(
            f"Cannot detect RUL target column. "
            f"Looked for numeric columns containing: {_RUL_KEYWORDS}. "
            f"Columns found: {tel_cols}"
        )

    # --- Operating hours column ---
    hours_col = _detect_role_column(tel_cols, _HOURS_KEYWORDS, df_tel)
    if hours_col is None:
        raise UploadValidationError(
            f"Cannot detect operating hours column. "
            f"Looked for numeric columns containing: {_HOURS_KEYWORDS}. "
            f"Columns found: {tel_cols}"
        )

    # --- Sensor columns ---
    role_cols = {asset_id_col.lower(), date_col.lower(), hours_col.lower()}
    if rul_col:
        role_cols.add(rul_col.lower())
    sensor_columns = [
        c for c in tel_cols
        if c.lower() not in role_cols and pd.api.types.is_numeric_dtype(df_tel[c])
    ]

    if len(sensor_columns) < 2:
        raise UploadValidationError(
            f"Need at least 2 numeric sensor columns beyond the four role columns. "
            f"Found {len(sensor_columns)}: {sensor_columns}. "
            f"Role columns detected: asset_id={asset_id_col}, date={date_col}, "
            f"rul={rul_col}, hours={hours_col}"
        )

    # --- Log columns ---
    log_asset_id_col = _detect_id_column(log_cols, cross_ref_columns=tel_cols)
    if log_asset_id_col is None:
        log_asset_id_col = _detect_id_column_fallback(log_cols, df_log)

    log_date_col, _ = _detect_date_column(log_cols, df_log) if len(df_log) > 0 else (None, None)
    if log_date_col is None and len(df_log) > 0:
        date_candidates = [c for c in log_cols
                           if any(kw in c.lower() for kw in _DATE_KEYWORDS)]
        log_date_col = date_candidates[0] if date_candidates else None

    log_event_col = _detect_event_column(log_cols)

    log_known = {log_asset_id_col, log_date_col, log_event_col}
    log_extra = [c for c in log_cols if c not in log_known]

    # --- Cross-sheet validation ---
    tel_asset_ids = set(df_tel[asset_id_col].dropna().astype(str).unique())
    if len(df_log) > 0 and log_asset_id_col is not None:
        log_asset_ids = set(df_log[log_asset_id_col].dropna().astype(str).unique())
        orphans = log_asset_ids - tel_asset_ids
        if orphans:
            raise UploadValidationError(
                f"Maintenance log contains asset IDs not in telemetry: {sorted(orphans)}"
            )

    # --- Sensor stats ---
    sensor_stats = {}
    for c in sensor_columns:
        series = pd.to_numeric(df_tel[c], errors="coerce").dropna()
        if len(series) == 0:
            sensor_stats[c] = {"min": 0.0, "max": 0.0, "mean": 0.0,
                               "std": 0.0, "p25": 0.0, "p75": 0.0}
        else:
            sensor_stats[c] = {
                "min": round(float(series.min()), 4),
                "max": round(float(series.max()), 4),
                "mean": round(float(series.mean()), 4),
                "std": round(float(series.std()), 4),
                "p25": round(float(series.quantile(0.25)), 4),
                "p75": round(float(series.quantile(0.75)), 4),
            }

    # --- Log sample values ---
    log_event_values = []
    if log_event_col and len(df_log) > 0:
        log_event_type_values = df_log[log_event_col].dropna().unique().tolist()
        log_event_type_values = [str(v).strip() for v in log_event_type_values if str(v).strip()]
        log_event_values = log_event_type_values
        print(f"[DEBUG] log_event_type_column: {log_event_col!r}")
        print(f"[DEBUG] log_event_type_values: {log_event_values!r}")

    log_extra_samples = {}
    for c in log_extra:
        if len(df_log) > 0:
            vals = df_log[c].dropna().astype(str).unique().tolist()
            log_extra_samples[c] = sorted(vals[:10])
        else:
            log_extra_samples[c] = []

    date_min = df_tel[date_col].min()
    date_max = df_tel[date_col].max()

    return {
        "asset_id_column": asset_id_col,
        "date_column": date_col,
        "rul_column": rul_col,
        "has_rul_column": bool(rul_col),
        "operating_hours_column": hours_col,
        "sensor_columns": sensor_columns,
        "log_asset_id_column": log_asset_id_col,
        "log_date_column": log_date_col,
        "log_event_type_column": log_event_col,
        "log_extra_columns": log_extra,
        "asset_ids": sorted(tel_asset_ids),
        "row_count": len(df_tel),
        "date_range": {
            "min": str(date_min.date()) if pd.notna(date_min) else "",
            "max": str(date_max.date()) if pd.notna(date_max) else "",
        },
        "sensor_stats": sensor_stats,
        "log_event_type_values": log_event_values,
        "log_extra_column_samples": log_extra_samples,
    }
