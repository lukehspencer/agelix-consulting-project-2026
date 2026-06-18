def clamp(value: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(max_val, value))


def convert_to_saaty(score: float) -> float:
    return round(1 + (score - 1) * (8 / 9), 2)


def score_criticality(criticality_raw: float) -> float:
    """C1 — Manual 1–10 input."""
    return convert_to_saaty(clamp(criticality_raw, 1, 10))


def score_condition(
    condition_score: float,
    vibration_level: str,
    seal_condition: str,
    bearing_condition: str,
) -> float:
    """C2 — Inverted condition score plus component-state penalties."""
    if condition_score >= 9:
        base = 1
    elif condition_score >= 7:
        base = 3
    elif condition_score >= 5:
        base = 5
    elif condition_score >= 3:
        base = 7
    else:
        base = 9

    vibration_penalty = {"Normal": 0, "High": 1, "Critical": 2}.get(vibration_level, 0)
    seal_penalty      = {"Good": 0, "Worn": 1, "Leaking": 2}.get(seal_condition, 0)
    bearing_penalty   = {"Good": 0, "Worn": 1, "Failed": 2}.get(bearing_condition, 0)

    raw = clamp(base + vibration_penalty + seal_penalty + bearing_penalty, 1, 10)
    return convert_to_saaty(raw)


def score_failure_probability(
    age_years: float,
    expected_lifespan_years: float,
    number_of_failures_last_3yr: int,
    days_since_maintenance: float,
    maintenance_frequency_days: float,
) -> float:
    """C3 — Age ratio, failure count, and maintenance overdue ratio."""
    ratio = age_years / expected_lifespan_years if expected_lifespan_years > 0 else 0.0

    if ratio < 0.2:
        age_factor = 0
    elif ratio < 0.4:
        age_factor = 1
    elif ratio < 0.6:
        age_factor = 2
    elif ratio < 0.8:
        age_factor = 3
    elif ratio < 1.0:
        age_factor = 4
    else:
        age_factor = 5

    failure_factor = min(number_of_failures_last_3yr, 4)

    overdue_ratio = (
        days_since_maintenance / maintenance_frequency_days
        if maintenance_frequency_days > 0
        else 0.0
    )
    if overdue_ratio < 0.5:
        overdue_factor = 0
    elif overdue_ratio < 1.0:
        overdue_factor = 1
    else:
        overdue_factor = 2

    raw = clamp(round((age_factor + failure_factor + overdue_factor) / 11 * 10), 1, 10)
    return convert_to_saaty(raw)


def score_downtime_impact(downtime_raw: float) -> float:
    """C4 — Manual 1–10 input."""
    return convert_to_saaty(clamp(downtime_raw, 1, 10))


def score_maintenance_cost_trend(
    maintenance_cost_trend: str,
    maintenance_cost_last_year: float,
) -> float:
    """C5 — Trend direction base plus cost-level modifier."""
    trend_base = {"Decreasing": 2, "Stable": 5, "Increasing": 8}.get(
        maintenance_cost_trend, 5
    )

    if maintenance_cost_last_year < 1000:
        cost_modifier = -1
    elif maintenance_cost_last_year < 3000:
        cost_modifier = 0
    elif maintenance_cost_last_year < 6000:
        cost_modifier = 1
    else:
        cost_modifier = 2

    raw = clamp(trend_base + cost_modifier, 1, 10)
    return convert_to_saaty(raw)


def score_asset(pump: dict) -> dict:
    """Compute all five C1–C5 Saaty scores for a pump.

    Expects the same fields as pumps.json, plus two manual inputs
    that the API caller supplies:
      - criticality_raw      (int 1–10)
      - downtime_impact_raw  (int 1–10)
    """
    return {
        "score_criticality": score_criticality(pump["criticality_raw"]),
        "score_condition": score_condition(
            pump["condition_score"],
            pump["vibration_level"],
            pump["seal_condition"],
            pump["bearing_condition"],
        ),
        "score_failure_probability": score_failure_probability(
            pump["age_years"],
            pump["expected_lifespan_years"],
            pump["number_of_failures_last_3yr"],
            pump["days_since_maintenance"],
            pump["maintenance_frequency_days"],
        ),
        "score_downtime_impact": score_downtime_impact(pump["downtime_impact_raw"]),
        "score_maintenance_cost_trend": score_maintenance_cost_trend(
            pump["maintenance_cost_trend"],
            pump["maintenance_cost_last_year"],
        ),
    }
