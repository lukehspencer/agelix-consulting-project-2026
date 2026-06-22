import math

_RAW_KEYS = [
    "age_years",
    "usage_intensity_pct",
    "total_runtime_hours",
    "operating_hours_per_day",
    "condition_score",
    "number_of_failures_last_3yr",
    "days_since_maintenance",
    "maintenance_cost_last_year",
]

_WEIGHT_NAMES = [
    "weight_criticality",
    "weight_condition",
    "weight_failure_probability",
    "weight_downtime_impact",
    "weight_maintenance_cost_trend",
]

_WEIGHTED_SCORE_NAMES = [
    "weighted_criticality",
    "weighted_condition",
    "weighted_failure_probability",
    "weighted_downtime_impact",
    "weighted_maintenance_cost_trend",
]

_FEATURE_NAMES = _RAW_KEYS + _WEIGHT_NAMES + _WEIGHTED_SCORE_NAMES + ["risk_factor"]

NUM_FEATURES = 19


def get_feature_names() -> list[str]:
    return list(_FEATURE_NAMES)


def build_feature_vector(
    pump: dict,
    weights: list[float],
    scores: list[float],
) -> list[float]:
    if len(weights) != 5:
        raise ValueError(f"weights must have exactly 5 elements, got {len(weights)}")
    if len(scores) != 5:
        raise ValueError(f"scores must have exactly 5 elements, got {len(scores)}")

    weighted_scores = [w * s for w, s in zip(weights, scores)]
    risk_factor = sum(weighted_scores)

    vector = [
        float(pump["age_years"]),
        float(pump["usage_intensity_pct"]),
        float(pump["total_runtime_hours"]),
        float(pump["operating_hours_per_day"]),
        float(pump["condition_score"]),
        float(pump["number_of_failures_last_3yr"]),
        float(pump["days_since_maintenance"]),
        float(pump["maintenance_cost_last_year"]),
        weights[0],
        weights[1],
        weights[2],
        weights[3],
        weights[4],
        weighted_scores[0],
        weighted_scores[1],
        weighted_scores[2],
        weighted_scores[3],
        weighted_scores[4],
        risk_factor,
    ]

    validate_feature_vector(vector)
    return vector


def validate_feature_vector(vector: list[float]) -> None:
    if len(vector) != NUM_FEATURES:
        raise ValueError(
            f"Feature vector must have exactly {NUM_FEATURES} elements, got {len(vector)}"
        )
    for i, val in enumerate(vector):
        if not isinstance(val, (int, float)) or not math.isfinite(val):
            raise ValueError(
                f"Feature at index {i} ({_FEATURE_NAMES[i]}) must be a finite number, got {val!r}"
            )
