"""
Physics-based RUL projection using sensor trend extrapolation.
No training required. Works with any amount of time series data.
Fits linear and exponential curves to each sensor trend and
projects when each sensor will cross its failure threshold.
"""

import logging
import math
from datetime import datetime, timedelta

import numpy as np
from scipy.optimize import curve_fit
from scipy.stats import linregress

logger = logging.getLogger(__name__)


def _finite(value, default=0.0) -> float:
    """Guards against NaN/inf leaking into a JSON response -- a bare NaN
    serializes as the literal token `NaN`, which is invalid JSON and makes
    the entire response unparsable on the frontend, not just this field.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


def _fit_linear(days: np.ndarray, values: np.ndarray) -> dict:
    """
    Fits a linear trend to sensor values over time.
    Returns slope, intercept, and R-squared goodness of fit.
    """
    if len(days) < 3:
        return {"slope": 0, "intercept": values[-1], "r_squared": 0}

    slope, intercept, r, _, _ = linregress(days, values)
    return {
        "slope": _finite(slope),
        "intercept": _finite(intercept, default=float(values[-1])),
        "r_squared": _finite(r ** 2),
    }


def _fit_exponential(days: np.ndarray, values: np.ndarray) -> dict:
    """
    Fits an exponential curve: value = a * exp(b * t) + c
    Falls back to linear if exponential fit fails.
    """
    def exp_func(t, a, b, c):
        return a * np.exp(b * t) + c

    try:
        # Initial guess based on data range
        a0 = values[-1] - values[0]
        b0 = 0.01
        c0 = values[0]
        # curve_fit's internal search can transiently probe large b values
        # before converging, which can overflow exp() -- harmless, scipy
        # handles it internally, just noisy without this suppressed.
        with np.errstate(over="ignore"):
            popt, _ = curve_fit(
                exp_func, days, values,
                p0=[a0, b0, c0],
                maxfev=5000,
                bounds=([-np.inf, -1, -np.inf], [np.inf, 1, np.inf])
            )
        fitted = exp_func(days, *popt)
        ss_res = np.sum((values - fitted) ** 2)
        ss_tot = np.sum((values - np.mean(values)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
        return {
            "params": popt,
            "r_squared": _finite(max(0, r_squared)),
            "func": exp_func
        }
    except Exception:
        return None


def _days_to_threshold_linear(current_value: float, slope: float,
                               threshold: float) -> float | None:
    """
    Projects days until sensor crosses threshold using linear trend.
    Returns None if sensor is stable or moving away from threshold.
    """
    if slope <= 0:
        return None  # Sensor improving or stable
    days = (threshold - current_value) / slope
    if days <= 0:
        return 0  # Already breached
    return days


def _days_to_threshold_exponential(current_value: float, params: tuple,
                                    threshold: float,
                                    func) -> float | None:
    """
    Projects days until sensor crosses threshold using exponential trend.
    Uses binary search to find the crossing point.
    """
    a, b, c = params
    # b > 0 alone is not sufficient: value = a*exp(b*t) + c only grows toward
    # +inf as t increases when the exponential term itself is growing in the
    # positive direction, i.e. a > 0 too. With b > 0 but a < 0, the curve
    # instead plunges toward -inf, and the bisection below (which assumes a
    # monotonically increasing function) would converge on a bogus "crossing"
    # near the search ceiling instead of correctly reporting no crossing.
    if b <= 0 or a <= 0:
        return None

    try:
        # Binary search for threshold crossing. Probing near the 10-year
        # ceiling with a slow-growing curve can legitimately overflow exp()
        # to +inf -- that's a correct "past threshold" signal for the search,
        # not an error, so overflow warnings are suppressed rather than
        # treated as a problem.
        with np.errstate(over="ignore"):
            t_low, t_high = 0, 3650  # Search up to 10 years
            for _ in range(50):
                t_mid = (t_low + t_high) / 2
                val = func(t_mid, a, b, c)
                if val >= threshold:
                    t_high = t_mid
                else:
                    t_low = t_mid
                if t_high - t_low < 0.5:
                    break

        result = (t_low + t_high) / 2
        if result <= 0:
            return 0
        return result
    except Exception:
        return None


def project_sensor_rul(sensor_values: list,
                        failure_threshold: float,
                        sensor_name: str = "") -> dict:
    """
    Projects when a single sensor will cross its failure threshold.

    Args:
        sensor_values: list of daily sensor readings (chronological)
        failure_threshold: the value at which this sensor indicates failure
        sensor_name: for logging only

    Returns:
        {
            "days_to_threshold": float or None,
            "current_value": float,
            "threshold": float,
            "trend_direction": "increasing" | "decreasing" | "stable",
            "trend_rate": float,  # units per day
            "fit_method": "exponential" | "linear" | "none",
            "fit_quality": float,  # R-squared 0-1
            "already_breached": bool,
            "projected_date": str or None  # ISO date string
        }
    """
    if len(sensor_values) < 3:
        return {
            "days_to_threshold": None,
            "current_value": sensor_values[-1] if sensor_values else 0,
            "threshold": failure_threshold,
            "trend_direction": "stable",
            "trend_rate": 0,
            "fit_method": "none",
            "fit_quality": 0,
            "already_breached": False,
            "projected_date": None
        }

    values = np.array(sensor_values, dtype=float)
    days = np.arange(len(values), dtype=float)
    current = values[-1]

    # Check if already breached
    if current >= failure_threshold:
        return {
            "days_to_threshold": 0,
            "current_value": float(current),
            "threshold": failure_threshold,
            "trend_direction": "increasing",
            "trend_rate": 0,
            "fit_method": "none",
            "fit_quality": 0,
            "already_breached": True,
            "projected_date": datetime.today().strftime("%Y-%m-%d")
        }

    # Try exponential fit first (better for wear degradation)
    exp_result = _fit_exponential(days, values)
    linear_result = _fit_linear(days, values)

    # Choose best fit
    use_exponential = (
        exp_result is not None and
        exp_result["r_squared"] > linear_result["r_squared"] + 0.05
    )

    if use_exponential:
        days_to = _days_to_threshold_exponential(
            current, exp_result["params"],
            failure_threshold, exp_result["func"]
        )
        fit_method = "exponential"
        fit_quality = exp_result["r_squared"]
        trend_rate = _finite(
            exp_result["func"](len(values), *exp_result["params"]) -
            exp_result["func"](len(values) - 1, *exp_result["params"])
        )
    else:
        days_to = _days_to_threshold_linear(
            current, linear_result["slope"], failure_threshold
        )
        fit_method = "linear"
        fit_quality = linear_result["r_squared"]
        trend_rate = _finite(linear_result["slope"])

    # Determine trend direction
    if trend_rate > 0.001:
        trend_direction = "increasing"
    elif trend_rate < -0.001:
        trend_direction = "decreasing"
    else:
        trend_direction = "stable"

    # Compute projected date
    projected_date = None
    if days_to is not None and days_to > 0:
        proj = datetime.today() + timedelta(days=days_to)
        projected_date = proj.strftime("%Y-%m-%d")

    logger.info(
        f"{sensor_name}: {fit_method} fit (R²={fit_quality:.2f}), "
        f"trend={trend_rate:.4f}/day, days_to_threshold={days_to}"
    )

    return {
        "days_to_threshold": round(days_to, 1) if days_to is not None else None,
        "current_value": float(current),
        "threshold": failure_threshold,
        "trend_direction": trend_direction,
        "trend_rate": round(trend_rate, 4),
        "fit_method": fit_method,
        "fit_quality": round(fit_quality, 3),
        "already_breached": False,
        "projected_date": projected_date
    }


def project_asset_rul(telemetry_df,
                       criteria_config: dict,
                       asset_id: str,
                       date_column: str,
                       sensor_columns: list) -> dict:
    """
    Projects RUL for a single asset using physics-based sensor extrapolation.

    Args:
        telemetry_df: DataFrame of telemetry rows for this asset,
                      sorted by date ascending
        criteria_config: CriteriaConfig from schema_inferrer
        asset_id: for logging
        date_column: name of date column
        sensor_columns: list of sensor column names to analyze

    Returns:
        {
            "physics_rul_days": float or None,
            "limiting_sensor": str or None,
            "limiting_sensor_projected_date": str or None,
            "sensor_projections": {
                "<sensor_name>": {sensor_rul_result}
            },
            "consensus_with_ml": str,  # populated later
            "confidence": "high" | "medium" | "low"
        }
    """
    try:
        return _project_asset_rul_impl(
            telemetry_df, criteria_config, asset_id, date_column, sensor_columns,
        )
    except Exception:
        logger.exception(
            "Physics RUL projection failed for asset '%s' -- returning empty projection", asset_id,
        )
        return {
            "physics_rul_days": None,
            "limiting_sensor": None,
            "limiting_sensor_projected_date": None,
            "sensor_projections": {},
            "consensus_with_ml": "unknown",
            "confidence": "low"
        }


def _project_asset_rul_impl(telemetry_df,
                             criteria_config: dict,
                             asset_id: str,
                             date_column: str,
                             sensor_columns: list) -> dict:
    # Extract failure thresholds from CriteriaConfig
    # For each non-manual criterion, find the catch-all threshold score
    # and use the last "max" value before catch-all as the failure threshold
    sensor_thresholds = {}
    for criterion in criteria_config.get("criteria", []):
        if criterion.get("manual_input"):
            continue
        primary_col = criterion.get("primary_column")
        if not primary_col or primary_col not in sensor_columns:
            continue
        thresholds = criterion.get("thresholds", [])
        # Find the highest max value (just before catch-all)
        max_values = [t["max"] for t in thresholds if "max" in t]
        if max_values:
            # Use the second-to-last threshold max as the critical threshold
            # (last max before catch-all = boundary of worst normal zone)
            sensor_thresholds[primary_col] = max(max_values)

    if not sensor_thresholds:
        return {
            "physics_rul_days": None,
            "limiting_sensor": None,
            "limiting_sensor_projected_date": None,
            "sensor_projections": {},
            "consensus_with_ml": "unknown",
            "confidence": "low"
        }

    # Project each sensor
    sensor_projections = {}
    min_days = None
    limiting_sensor = None

    for sensor_col, threshold in sensor_thresholds.items():
        if sensor_col not in telemetry_df.columns:
            continue
        values = telemetry_df[sensor_col].dropna().tolist()
        if len(values) < 3:
            continue

        result = project_sensor_rul(values, threshold, sensor_col)
        sensor_projections[sensor_col] = result

        days = result.get("days_to_threshold")
        if days is not None:
            if min_days is None or days < min_days:
                min_days = days
                limiting_sensor = sensor_col

    # Assess confidence based on fit quality and data length
    n_rows = len(telemetry_df)
    fit_qualities = [
        p["fit_quality"] for p in sensor_projections.values()
        if p["fit_quality"] > 0
    ]
    avg_fit_quality = float(np.mean(fit_qualities)) if fit_qualities else 0.0

    if n_rows >= 60 and avg_fit_quality > 0.7:
        confidence = "high"
    elif n_rows >= 30 and avg_fit_quality > 0.4:
        confidence = "medium"
    else:
        confidence = "low"

    limiting_date = None
    if limiting_sensor:
        limiting_date = sensor_projections[limiting_sensor].get(
            "projected_date"
        )

    return {
        "physics_rul_days": round(min_days, 1) if min_days is not None else None,
        "limiting_sensor": limiting_sensor,
        "limiting_sensor_projected_date": limiting_date,
        "sensor_projections": sensor_projections,
        "consensus_with_ml": "pending",  # set after ML prediction
        "confidence": confidence
    }


def assess_consensus(ml_rul_days: float,
                     physics_rul_days: float | None) -> str:
    """
    Compares ML and physics predictions and returns a consensus assessment.

    Returns:
        "high"    — both agree within 30%
        "medium"  — both agree within 60%
        "low"     — estimates diverge significantly
        "unknown" — physics projection unavailable
    """
    if physics_rul_days is None:
        return "unknown"

    if ml_rul_days <= 0 or physics_rul_days <= 0:
        return "high" if abs(ml_rul_days - physics_rul_days) < 30 else "low"

    ratio = max(ml_rul_days, physics_rul_days) / max(
        min(ml_rul_days, physics_rul_days), 1
    )

    if ratio <= 1.3:
        return "high"
    elif ratio <= 1.6:
        return "medium"
    else:
        return "low"
