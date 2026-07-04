import logging

from data.column_resolver import resolve_sensor

logger = logging.getLogger(__name__)


def _severity(exceeded_pct: float) -> str:
    if exceeded_pct > 0.25:
        return "high"
    if exceeded_pct >= 0.10:
        return "medium"
    return "low"


def _walk_bands(value: float, bands: list, key: str, is_safe):
    """Walk an ordered list of bands (each with 'max' except possibly the
    last) and return (matched_band, safe_boundary) where safe_boundary is
    the 'max' of the last band satisfying `is_safe` seen before the match.
    """
    safe_boundary = None
    for entry in bands:
        has_max = "max" in entry
        if has_max and value < entry["max"]:
            return entry, safe_boundary
        if has_max and is_safe(entry.get(key, 0)):
            safe_boundary = entry["max"]
    return (bands[-1] if bands else None), safe_boundary


def _record_breach(cid, cname, column, value, threshold_max, breach_type):
    exceeded_by = value - threshold_max
    exceeded_pct = exceeded_by / threshold_max
    return {
        "criterion_id": cid,
        "criterion_name": cname,
        "column": column,
        "current_value": round(value, 4),
        "threshold_max": round(threshold_max, 4),
        "exceeded_by": round(exceeded_by, 4),
        "exceeded_pct": round(exceeded_pct, 4),
        "severity": _severity(exceeded_pct),
        "breach_type": breach_type,
    }


def detect_breaches(asset_row: dict, criteria_config: dict) -> list[dict]:
    breaches = []

    for crit in criteria_config.get("criteria", []):
        if crit.get("manual_input"):
            continue

        cid = crit.get("id", "")
        cname = crit.get("name", cid)

        primary_col = crit.get("primary_column")
        thresholds = crit.get("thresholds", [])
        if primary_col and thresholds:
            raw_val = resolve_sensor(asset_row, primary_col, default=None)
            if raw_val is None:
                logger.warning(
                    "Breach detection: column '%s' (criterion %s) not found "
                    "in asset row, skipping", primary_col, cid,
                )
            else:
                try:
                    value = float(raw_val)
                except (TypeError, ValueError):
                    logger.warning(
                        "Breach detection: value for '%s' (criterion %s) is "
                        "not numeric, skipping", primary_col, cid,
                    )
                    value = None

                if value is not None:
                    matched, safe_boundary = _walk_bands(value, thresholds, "score", lambda s: s <= 3)
                    if matched is not None and matched.get("score", 0) > 3:
                        threshold_max = safe_boundary if safe_boundary is not None else matched.get("max")
                        if threshold_max:
                            breaches.append(
                                _record_breach(cid, cname, primary_col, value, threshold_max, "primary")
                            )

        for pen in crit.get("penalties", []):
            pcol = pen.get("column")
            bands = pen.get("bands", [])
            if not pcol or not bands:
                continue

            raw_val = resolve_sensor(asset_row, pcol, default=None)
            if raw_val is None:
                logger.warning(
                    "Breach detection: penalty column '%s' (criterion %s) "
                    "not found in asset row, skipping", pcol, cid,
                )
                continue

            try:
                value = float(raw_val)
            except (TypeError, ValueError):
                logger.warning(
                    "Breach detection: penalty value for '%s' (criterion %s) "
                    "is not numeric, skipping", pcol, cid,
                )
                continue

            matched, safe_boundary = _walk_bands(value, bands, "penalty", lambda p: p > -2)
            if matched is not None and matched.get("penalty", 0) <= -2:
                threshold_max = safe_boundary if safe_boundary is not None else matched.get("max")
                if threshold_max:
                    breaches.append(
                        _record_breach(cid, cname, pcol, value, threshold_max, "penalty")
                    )

    return breaches


def get_breach_summary(breaches: list[dict]) -> dict:
    high = sum(1 for b in breaches if b.get("severity") == "high")
    medium = sum(1 for b in breaches if b.get("severity") == "medium")
    low = sum(1 for b in breaches if b.get("severity") == "low")

    most_severe_criterion = None
    if breaches:
        rank = {"high": 3, "medium": 2, "low": 1}
        most_severe_criterion = max(
            breaches, key=lambda b: rank.get(b.get("severity"), 0)
        ).get("criterion_name")

    return {
        "total_breaches": len(breaches),
        "high_severity": high,
        "medium_severity": medium,
        "low_severity": low,
        "most_severe_criterion": most_severe_criterion,
        "alert_required": high >= 1 or medium >= 2,
    }
