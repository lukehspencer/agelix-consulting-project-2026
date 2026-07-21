from datetime import date, timedelta

_DEFAULT_REPLACEMENT_COST = 50000.0
_REPLACEMENT_COST_KEYWORDS = ("replacement", "value", "cost")


def calculate_mtbf(asset_snapshot: dict, criteria_config: dict) -> dict:
    total_failure_count = int(asset_snapshot.get("total_failure_count", 0) or 0)
    total_runtime_hours = float(asset_snapshot.get("total_runtime_hours", 0) or 0)
    operating_hours_per_day = float(asset_snapshot.get("operating_hours_per_day", 22) or 22)

    if total_failure_count >= 2:
        total_operating_days = (
            total_runtime_hours / operating_hours_per_day if operating_hours_per_day else 0.0
        )
        mtbf_days = total_operating_days / total_failure_count
        basis = "observed_failures"
        mtbf_note = (
            f"Estimated from {total_failure_count} observed failures over "
            f"{total_operating_days:.0f} operating days"
        )
    elif total_failure_count == 1:
        mtbf_days = total_runtime_hours / max(total_failure_count, 1) / 24
        basis = "single_failure"
        mtbf_note = (
            "Estimated from a single observed failure across the full recorded "
            "runtime; treat as a rough approximation"
        )
    else:
        mtbf_days = None
        basis = "insufficient_data"
        mtbf_note = "Insufficient failure history -- MTBF unavailable"

    if total_failure_count >= 5:
        mtbf_confidence = "high"
    elif total_failure_count >= 2:
        mtbf_confidence = "medium"
    else:
        mtbf_confidence = "low"

    return {
        "mtbf_days": round(mtbf_days, 1) if mtbf_days is not None else None,
        "mtbf_confidence": mtbf_confidence,
        "mtbf_note": mtbf_note,
        "basis": basis,
    }


def calculate_mtbm(mtbf_days: float, risk_factor: float,
                    current_interval_days: int = 90) -> dict:
    if mtbf_days is None:
        next_maintenance_date = (date.today() + timedelta(days=current_interval_days)).isoformat()
        return {
            "mtbm_recommended_days": current_interval_days,
            "current_interval_days": current_interval_days,
            "recommendation": "maintain",
            "recommendation_text": (
                "Insufficient failure history for interval optimization -- "
                "maintain current schedule"
            ),
            "next_maintenance_date": next_maintenance_date,
        }

    base_mtbm = mtbf_days * 0.6

    risk_ratio = (risk_factor - 1) / 8
    mtbm_adjusted = base_mtbm * (1 - risk_ratio * 0.4)
    mtbm_recommended = round(mtbm_adjusted)

    if mtbm_recommended < current_interval_days * 0.8:
        recommendation = "shorten"
        recommendation_text = (
            f"Reduce interval from {current_interval_days} to {mtbm_recommended} days. "
            "Asset risk warrants more frequent maintenance."
        )
    elif mtbm_recommended > current_interval_days * 1.2:
        recommendation = "extend"
        recommendation_text = (
            f"Interval can be extended from {current_interval_days} to {mtbm_recommended} days."
        )
    else:
        recommendation = "maintain"
        recommendation_text = "Current maintenance interval is appropriate."

    next_maintenance_date = (date.today() + timedelta(days=mtbm_recommended)).isoformat()

    return {
        "mtbm_recommended_days": mtbm_recommended,
        "current_interval_days": current_interval_days,
        "recommendation": recommendation,
        "recommendation_text": recommendation_text,
        "next_maintenance_date": next_maintenance_date,
    }


def _find_replacement_cost(asset_snapshot: dict) -> tuple[float, bool]:
    for key, val in asset_snapshot.items():
        if key == "maintenance_cost_last_year":
            continue
        key_lower = key.lower()
        if not any(kw in key_lower for kw in _REPLACEMENT_COST_KEYWORDS):
            continue
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            continue
        return float(val), False

    return _DEFAULT_REPLACEMENT_COST, True


def calculate_replace_vs_maintain(mtbf_days: float, maintenance_cost_last_year: float,
                                   asset_snapshot: dict) -> dict:
    annual_maintenance_cost = float(maintenance_cost_last_year or 0)
    estimated_replacement_cost, replacement_cost_estimated = _find_replacement_cost(asset_snapshot)

    years_of_mtbf = (mtbf_days / 365) if mtbf_days is not None else 0

    if years_of_mtbf > 0:
        replacement_amortized_per_year = estimated_replacement_cost / max(years_of_mtbf, 1)

        if annual_maintenance_cost > replacement_amortized_per_year:
            decision = "replace"
            rationale = (
                f"Annual maintenance cost (${annual_maintenance_cost:.0f}) exceeds "
                f"amortized replacement cost (${replacement_amortized_per_year:.0f}/yr)"
            )
        else:
            decision = "maintain"
            rationale = (
                f"Maintenance cost (${annual_maintenance_cost:.0f}/yr) remains below "
                f"replacement threshold (${replacement_amortized_per_year:.0f}/yr)"
            )
        years_until_economic_end_of_life = round(years_of_mtbf, 1)
    else:
        decision = "insufficient_data"
        rationale = "Insufficient failure history for cost analysis"
        years_until_economic_end_of_life = None

    return {
        "decision": decision,
        "rationale": rationale,
        "annual_maintenance_cost": annual_maintenance_cost,
        "estimated_replacement_cost": estimated_replacement_cost,
        "replacement_cost_estimated": replacement_cost_estimated,
        "years_until_economic_end_of_life": years_until_economic_end_of_life,
    }
