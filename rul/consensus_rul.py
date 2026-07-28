"""
Model selection between the ML (XGBoost) and physics-based RUL estimates.
Picks whichever single estimate (or their average) is most appropriate for
the situation, rather than blending them unconditionally.
"""


def select_rul(ml_rul_days: float,
               physics_rul_days: float | None,
               consensus: str,
               physics_confidence: str) -> dict:
    """
    Selects the most appropriate RUL estimate based on
    model agreement and physics confidence level.

    Returns:
    {
        "primary_rul_days": float,
        "primary_source": "ml" | "physics" | "average",
        "ml_rul_days": float,
        "physics_rul_days": float or None,
        "consensus": str,
        "physics_confidence": str,
        "reason": str
    }
    """

    # Rule 1 — No physics available
    if physics_rul_days is None:
        return {
            "primary_rul_days": round(ml_rul_days),
            "primary_source": "ml",
            "ml_rul_days": round(ml_rul_days),
            "physics_rul_days": None,
            "consensus": consensus,
            "physics_confidence": physics_confidence,
            "reason": "Physics projection unavailable -- ML estimate used"
        }

    # Rule 2 — High consensus (both agree within 30%)
    if consensus == "high":
        avg = round((ml_rul_days + physics_rul_days) / 2)
        return {
            "primary_rul_days": avg,
            "primary_source": "average",
            "ml_rul_days": round(ml_rul_days),
            "physics_rul_days": round(physics_rul_days),
            "consensus": consensus,
            "physics_confidence": physics_confidence,
            "reason": "Both models agree -- average of both used"
        }

    # Rule 3b/4 — Low consensus: trust physics over ML whenever physics
    # confidence is medium or high; only fall back to ML when physics
    # confidence is low. This covers every consensus/confidence combination
    # here -- otherwise a low-consensus, medium-confidence asset would fall
    # through to the medium-consensus branch below and get a "Models have
    # moderate agreement" reason string that's simply false (consensus is
    # low, not medium).
    if consensus == "low":
        if physics_confidence in ("high", "medium"):
            return {
                "primary_rul_days": round(physics_rul_days),
                "primary_source": "physics",
                "ml_rul_days": round(ml_rul_days),
                "physics_rul_days": round(physics_rul_days),
                "consensus": consensus,
                "physics_confidence": physics_confidence,
                "reason": (
                    f"Models diverge significantly -- physics prioritized "
                    f"({physics_confidence} confidence trend detected)"
                )
            }
        else:
            return {
                "primary_rul_days": round(ml_rul_days),
                "primary_source": "ml",
                "ml_rul_days": round(ml_rul_days),
                "physics_rul_days": round(physics_rul_days),
                "consensus": consensus,
                "physics_confidence": physics_confidence,
                "reason": (
                    "Models diverge -- ML prioritized "
                    "(insufficient data for reliable physics projection)"
                )
            }

    # Rule 5 — Medium consensus
    if physics_confidence in ("high", "medium"):
        return {
            "primary_rul_days": round(physics_rul_days),
            "primary_source": "physics",
            "ml_rul_days": round(ml_rul_days),
            "physics_rul_days": round(physics_rul_days),
            "consensus": consensus,
            "physics_confidence": physics_confidence,
            "reason": (
                "Models have moderate agreement -- physics selected "
                "based on data quality"
            )
        }
    else:
        return {
            "primary_rul_days": round(ml_rul_days),
            "primary_source": "ml",
            "ml_rul_days": round(ml_rul_days),
            "physics_rul_days": round(physics_rul_days),
            "consensus": consensus,
            "physics_confidence": physics_confidence,
            "reason": (
                "Models have moderate agreement -- ML selected "
                "(limited physics data quality)"
            )
        }
