import logging
import math

from ahp.criteria_scoring import convert_to_saaty
from data.column_resolver import get_sensor_columns, resolve_sensor

logger = logging.getLogger(__name__)


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

    return names


def build_dynamic_feature_vector(asset_snapshot: dict,
                                  criteria_config: dict,
                                  weights: list,
                                  scores_raw: dict) -> list:
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

    return vector
