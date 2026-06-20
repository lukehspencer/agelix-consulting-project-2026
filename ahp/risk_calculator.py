from ahp.ahp_constants import CRITERIA

_SCORE_KEYS = [
    "score_criticality",
    "score_condition",
    "score_failure_probability",
    "score_downtime_impact",
    "score_maintenance_cost_trend",
]


def compute_risk_factor(weights: list[float], scores: list[float]) -> dict:
    """Dot product of AHP weights × Saaty criterion scores for one pump.

    Returns the scalar risk_factor and the per-criterion weighted scores
    preserved as a list — both are required as ML feature inputs in Phase 2.
    """
    weighted_scores = [round(w * s, 6) for w, s in zip(weights, scores)]
    risk_factor = round(sum(weighted_scores), 4)
    return {
        "risk_factor": risk_factor,
        "weighted_scores": weighted_scores,
    }


def rank_assets(weights: list[float], pumps: list[dict]) -> list[dict]:
    """Compute and rank all pump risk factors from highest to lowest risk.

    Args:
        weights: 5-element weight vector from run_ahp(), summing to 1.0.
        pumps:   List of pump dicts containing the five C1–C5 Saaty score fields.

    Returns:
        List of result dicts sorted descending by risk_factor. Each entry contains:
          asset_id        – pump identifier
          asset_name      – human-readable name
          risk_factor     – scalar 1–9 (dot product of weights × scores)
          weights         – full weight vector [w1–w5]  (kept for Phase 2 ML)
          scores          – full score vector [s1–s5]   (kept for Phase 2 ML)
          weighted_scores – per-criterion products [w1·s1 … w5·s5] (Phase 2 ML)
          criteria        – criterion labels index-aligned with the above vectors
    """
    results = []
    for pump in pumps:
        scores = [pump[key] for key in _SCORE_KEYS]
        risk = compute_risk_factor(weights, scores)
        results.append({
            **pump,
            "risk_factor": risk["risk_factor"],
            "weights": list(weights),
            "scores": scores,
            "weighted_scores": risk["weighted_scores"],
            "criteria": CRITERIA,
        })

    return sorted(results, key=lambda x: x["risk_factor"], reverse=True)
