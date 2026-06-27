import logging

from ahp.criteria_scoring import clamp, convert_to_saaty
from data.column_resolver import resolve_sensor

logger = logging.getLogger(__name__)

_MISSING_SENTINEL = object()


def _apply_thresholds(value: float, thresholds: list) -> int:
    for entry in thresholds:
        if "max" in entry and value < entry["max"]:
            return entry["score"]
    return thresholds[-1]["score"]


def _apply_penalties(asset_row: dict, penalties: list, criterion_id: str) -> int:
    total = 0
    for pen in penalties:
        col = pen["column"]
        val = resolve_sensor(asset_row, col, default=_MISSING_SENTINEL)
        if val is _MISSING_SENTINEL:
            logger.warning(
                "Criterion %s: penalty column '%s' not found in asset row, using 0.0",
                criterion_id, col,
            )
            val = 0.0
        val = float(val)
        for band in pen["bands"]:
            if "max" in band and val < band["max"]:
                total += band["penalty"]
                break
        else:
            total += pen["bands"][-1]["penalty"]
    return total


def score_asset_dynamic(asset_row: dict, criteria_config: dict,
                        manual_scores: dict) -> dict:
    scores = {}
    raw_scores = {}

    for crit in criteria_config["criteria"]:
        cid = crit["id"]

        if crit.get("manual_input"):
            raw = manual_scores.get(cid, crit.get("default_score", 5))
            raw = int(clamp(raw, 1, 10))
            raw_scores[cid] = raw
            scores[cid] = convert_to_saaty(raw)
            continue

        primary_col = crit["primary_column"]
        val = resolve_sensor(asset_row, primary_col, default=_MISSING_SENTINEL)
        if val is _MISSING_SENTINEL:
            logger.warning(
                "Criterion %s: primary column '%s' not found in asset row, using 5.0",
                cid, primary_col,
            )
            val = 5.0
        val = float(val)

        base = _apply_thresholds(val, crit["thresholds"])
        penalty = _apply_penalties(asset_row, crit.get("penalties", []), cid)

        raw = int(clamp(base + penalty, 1, 10))
        raw_scores[cid] = raw
        scores[cid] = convert_to_saaty(raw)

    scores["raw_scores"] = raw_scores
    return scores
