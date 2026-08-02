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


def calculate_mtbm(mtbf_days: float | None, risk_factor: float,
                    current_interval_days: int = 90,
                    rul_days: float | None = None,
                    pm_projection: dict | None = None) -> dict:
    if (pm_projection and pm_projection.get("pm_days") is not None
            and pm_projection.get("confidence") in ("high", "medium")):
        pm_days = pm_projection["pm_days"]

        # Already at or past the warning threshold, or the asset's own
        # predicted RUL is already exhausted -- there's no future interval
        # to recommend, maintenance is due now. next_maintenance_date must
        # be today, not today + 1 (rounding pm_days up to a 1-day floor, as
        # the general case below does, would otherwise push this into the
        # future for an asset that needs attention right now).
        if pm_days <= 0 or (rul_days is not None and rul_days <= 0):
            return {
                "mtbm_recommended_days": 0,
                "current_interval_days": current_interval_days,
                "recommendation": "immediate",
                "recommendation_text": (
                    "Asset has reached or exceeded warning threshold -- "
                    "maintenance required immediately."
                ),
                "next_maintenance_date": date.today().isoformat(),
                "basis": "degradation_projection",
                "rul_days_used": rul_days,
            }

        # Highest-priority method when available: degradation-projection-based.
        # Schedules maintenance at the earliest point any monitored sensor is
        # projected to cross its own WARNING threshold (see
        # rul/physics_rul.py's project_asset_pm()) -- an asset-specific
        # estimate driven by this asset's own observed degradation rate,
        # rather than a fixed percentage of RUL or population-level MTBF.
        mtbm_recommended = max(1, round(pm_days))

        # A PM schedule must never fall after this asset's own predicted
        # RUL -- recommending maintenance beyond an asset's expected
        # remaining life is never useful, regardless of which basis produced
        # the number. (The rul_based branch below can never exceed rul_days
        # by construction, since it's always 75% of it -- this cap only ever
        # bites here, when the degradation projection runs ahead of RUL.)
        if rul_days is not None and rul_days > 0 and mtbm_recommended > rul_days:
            mtbm_recommended = max(1, round(rul_days * 0.9))

        limiting_sensor = pm_projection.get("limiting_sensor")
        limiting_threshold = pm_projection.get("limiting_threshold") or 0.0
        sensor_detail = (pm_projection.get("sensor_pm_projections") or {}).get(limiting_sensor) or {}
        trend_rate = sensor_detail.get("trend_rate") or 0.0

        recommendation_text = (
            f"PM in {mtbm_recommended} days based on {limiting_sensor} trending toward "
            f"warning threshold of {limiting_threshold:.2f} at current degradation rate "
            f"of {trend_rate:.4f}/day"
        )

        if mtbm_recommended < current_interval_days * 0.8:
            recommendation = "shorten"
        elif mtbm_recommended > current_interval_days * 1.2:
            recommendation = "extend"
        else:
            recommendation = "maintain"

        next_maintenance_date = (date.today() + timedelta(days=mtbm_recommended)).isoformat()

        return {
            "mtbm_recommended_days": mtbm_recommended,
            "current_interval_days": current_interval_days,
            "recommendation": recommendation,
            "recommendation_text": recommendation_text,
            "next_maintenance_date": next_maintenance_date,
            "basis": "degradation_projection",
            "rul_days_used": rul_days,
        }

    if rul_days is not None and rul_days > 0:
        # Primary method: RUL-based. Schedules maintenance at 75% of this
        # asset's own predicted remaining life, leaving a 25% buffer before
        # it's expected to reach a critical state. This reacts to the asset's
        # actual predicted trajectory rather than population-level failure
        # statistics (MTBF) or current risk score alone, so it takes priority
        # over both fallbacks below whenever a RUL prediction is available.
        mtbm_recommended = max(1, round(rul_days * 0.75))

        if mtbm_recommended < current_interval_days * 0.8:
            recommendation = "shorten"
            recommendation_text = (
                f"Reduce PM interval to {mtbm_recommended} days based on predicted RUL of "
                f"{rul_days:.0f} days. Maintenance scheduled at 75% of remaining life."
            )
        elif mtbm_recommended > current_interval_days * 1.2:
            recommendation = "extend"
            recommendation_text = (
                f"PM interval can be extended to {mtbm_recommended} days based on predicted "
                f"RUL of {rul_days:.0f} days."
            )
        else:
            recommendation = "maintain"
            recommendation_text = (
                f"Current interval is appropriate. Recommended PM in {mtbm_recommended} days "
                f"based on predicted RUL of {rul_days:.0f} days."
            )

        next_maintenance_date = (date.today() + timedelta(days=mtbm_recommended)).isoformat()

        return {
            "mtbm_recommended_days": mtbm_recommended,
            "current_interval_days": current_interval_days,
            "recommendation": recommendation,
            "recommendation_text": recommendation_text,
            "next_maintenance_date": next_maintenance_date,
            "basis": "rul_based",
            "rul_days_used": rul_days,
        }

    if mtbf_days is None:
        # No RUL prediction and no failure history to derive an MTBF-based
        # interval from. Fall back to a risk-adjusted interval instead of
        # just "maintain current" -- higher current risk (from the AHP
        # criteria, not failure history) shortens the interval, up to a 50%
        # reduction at max risk. This is a materially weaker basis than
        # either method above (asset condition/criticality, not a predicted
        # trajectory or observed failure frequency), so "basis" is always
        # set here and callers/UI should treat it as such.
        risk_ratio = (risk_factor - 1) / 8
        adjustment = 1 - (risk_ratio * 0.5)
        mtbm_recommended = round(current_interval_days * adjustment)

        if mtbm_recommended < current_interval_days * 0.8:
            recommendation = "shorten"
            recommendation_text = (
                f"Reduce interval to {mtbm_recommended} days based on current risk level. "
                "Insufficient failure history for MTBF-based optimization."
            )
        else:
            recommendation = "maintain"
            recommendation_text = (
                f"Current interval of {current_interval_days} days is appropriate given "
                "current risk level."
            )

        next_maintenance_date = (date.today() + timedelta(days=mtbm_recommended)).isoformat()

        return {
            "mtbm_recommended_days": mtbm_recommended,
            "current_interval_days": current_interval_days,
            "recommendation": recommendation,
            "recommendation_text": recommendation_text,
            "next_maintenance_date": next_maintenance_date,
            "basis": "risk_adjusted",
            "rul_days_used": None,
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
        "basis": "mtbf_based",
        "rul_days_used": None,
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
