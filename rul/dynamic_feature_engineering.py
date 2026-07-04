import itertools
import logging
import math

from ahp.criteria_scoring import convert_to_saaty
from data.column_resolver import get_sensor_columns, resolve_sensor

logger = logging.getLogger(__name__)


def _sorted_sensor_pairs(criteria_config: dict) -> list[tuple[str, str]]:
    return list(itertools.combinations(sorted(get_sensor_columns(criteria_config)), 2))


def _safe_float(value, feature_name: str) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        logger.warning("Feature '%s': cannot convert %r to float, using 0.0", feature_name, value)
        return 0.0
    if not math.isfinite(v):
        logger.warning("Feature '%s': non-finite value %r, using 0.0", feature_name, v)
        return 0.0
    return v


def _n_criteria(criteria_config: dict) -> int:
    return len(criteria_config.get("criteria", []))


def get_dynamic_feature_names(criteria_config: dict) -> list[str]:
    n = _n_criteria(criteria_config)

    names = [
        "total_runtime_hours",
        "failures_last_90_days",
        "days_since_last_event",
        "total_failure_count",
    ]

    for i in range(n):
        names.append(f"weight_C{i+1}")

    for i in range(n):
        names.append(f"weighted_score_C{i+1}")

    names.append("risk_factor")

    for col in get_sensor_columns(criteria_config):
        names.append(f"rolling_{col}_mean")
        names.append(f"rolling_{col}_std")

    for col in get_sensor_columns(criteria_config):
        names.append(f"trend_{col}")

    pairs = _sorted_sensor_pairs(criteria_config)

    for col_a, col_b in pairs:
        names.append(f"interaction_{col_a}_{col_b}")

    for col_a, col_b in pairs:
        names.append(f"alignment_{col_a}_{col_b}")

    for col_a, col_b in pairs:
        names.append(f"corr_{col_a}_{col_b}")

    names.append("composite_stress_index")

    names.append("breach_count")
    names.append("high_severity_count")
    names.append("medium_severity_count")
    names.append("max_exceeded_pct")

    return names


def build_dynamic_feature_vector(asset_snapshot: dict,
                                  criteria_config: dict,
                                  weights: list,
                                  scores_raw: dict,
                                  breaches: list = None) -> list:
    n = _n_criteria(criteria_config)
    vector = []

    vector.append(_safe_float(asset_snapshot.get("total_runtime_hours", 0), "total_runtime_hours"))
    vector.append(_safe_float(asset_snapshot.get("failures_last_90_days", 0), "failures_last_90_days"))
    vector.append(_safe_float(asset_snapshot.get("days_since_last_event", 0), "days_since_last_event"))
    vector.append(_safe_float(asset_snapshot.get("total_failure_count", 0), "total_failure_count"))

    for i in range(n):
        w = weights[i] if i < len(weights) else 1.0 / n
        vector.append(_safe_float(w, f"weight_C{i+1}"))

    weighted_saaty = []
    for i in range(n):
        cid = f"C{i+1}"
        raw_score = scores_raw.get(cid, 5)
        saaty = convert_to_saaty(raw_score)
        w = weights[i] if i < len(weights) else 1.0 / n
        ws = w * saaty
        weighted_saaty.append(ws)
        vector.append(_safe_float(ws, f"weighted_score_{cid}"))

    risk_factor = sum(weighted_saaty)
    vector.append(_safe_float(risk_factor, "risk_factor"))

    for col in get_sensor_columns(criteria_config):
        mean_key = f"rolling_{col}_mean"
        std_key = f"rolling_{col}_std"

        mean_val = resolve_sensor(asset_snapshot, mean_key, default=None)
        if mean_val is None:
            logger.warning("Feature '%s': missing in snapshot, using 0.0", mean_key)
            mean_val = 0.0

        std_val = resolve_sensor(asset_snapshot, std_key, default=None)
        if std_val is None:
            logger.warning("Feature '%s': missing in snapshot, using 0.0", std_key)
            std_val = 0.0

        vector.append(_safe_float(mean_val, mean_key))
        vector.append(_safe_float(std_val, std_key))

    for col in get_sensor_columns(criteria_config):
        key = f"trend_{col}"
        val = resolve_sensor(asset_snapshot, key, default=None)
        if val is None:
            logger.warning("Feature '%s': missing in snapshot, using 0.0", key)
            val = 0.0
        vector.append(_safe_float(val, key))

    pairs = _sorted_sensor_pairs(criteria_config)

    for prefix in ("interaction", "alignment", "corr"):
        for col_a, col_b in pairs:
            key = f"{prefix}_{col_a}_{col_b}"
            val = resolve_sensor(asset_snapshot, key, default=None)
            if val is None:
                logger.warning("Feature '%s': missing in snapshot, using 0.0", key)
                val = 0.0
            vector.append(_safe_float(val, key))

    stress_val = resolve_sensor(asset_snapshot, "composite_stress_index", default=None)
    if stress_val is None:
        logger.warning("Feature 'composite_stress_index': missing in snapshot, using 0.0")
        stress_val = 0.0
    vector.append(_safe_float(stress_val, "composite_stress_index"))

    if breaches:
        high_count = sum(1 for b in breaches if b.get("severity") == "high")
        medium_count = sum(1 for b in breaches if b.get("severity") == "medium")
        breach_count = len(breaches)
        max_pct = max((b.get("exceeded_pct", 0.0) for b in breaches), default=0.0)
    else:
        high_count = medium_count = breach_count = 0
        max_pct = 0.0

    vector.append(_safe_float(breach_count, "breach_count"))
    vector.append(_safe_float(high_count, "high_severity_count"))
    vector.append(_safe_float(medium_count, "medium_severity_count"))
    vector.append(_safe_float(max_pct, "max_exceeded_pct"))

    return vector
