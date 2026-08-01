"""
Prediction functions for the RUL 2 (decommissioning) dynamic model.

Mirrors rul/dynamic_ml_rul_model.py's structure, but RUL 2 answers a
different question than RUL 1: not "how long until this asset fails,"
but "how long until this asset should be decommissioned." The model
bundle is produced by rul/dynamic_train_rul2_cli.py and is loaded from
its own <asset_type>_rul2.pkl path -- never rul/dynamic_ml_rul_model.py's
RUL 1 bundles.
"""
from datetime import date
from pathlib import Path

import joblib
import numpy as np

# KSB Calio spec default, used only when a bundle doesn't carry its own
# design_life (e.g. an asset type whose expected service life differs).
_DEFAULT_DESIGN_LIFE_YEARS = 25
_CI_HALF_WIDTH_YEARS = 2

_cache = {}


def _load_bundle(model_path: str) -> dict:
    if model_path in _cache:
        return _cache[model_path]

    p = Path(model_path)
    if not p.exists():
        raise FileNotFoundError(
            f"No RUL 2 model found at {model_path}. "
            "Train first: python -m rul.dynamic_train_rul2_cli --file <data.xlsx>"
        )

    bundle = joblib.load(p)
    _cache[model_path] = bundle
    return bundle


def _build_result(rul_2_years_raw: float, design_life_years: float) -> dict:
    rul_2_years = round(max(0.0, rul_2_years_raw), 1)
    decommission_year = date.today().year + int(round(rul_2_years))

    pct_life_remaining = (
        round((rul_2_years / design_life_years) * 100, 1)
        if design_life_years > 0 else 0.0
    )

    return {
        "rul_2_years": rul_2_years,
        "decommission_year": decommission_year,
        "ci_low_years": round(max(0.0, rul_2_years - _CI_HALF_WIDTH_YEARS), 1),
        "ci_high_years": round(rul_2_years + _CI_HALF_WIDTH_YEARS, 1),
        "pct_life_remaining": pct_life_remaining,
    }


def predict_rul2(feature_vector: list, model_path: str) -> dict:
    bundle = _load_bundle(model_path)
    expected_names = bundle["feature_names"]
    expected_len = len(expected_names)

    if len(feature_vector) != expected_len:
        raise ValueError(
            f"Feature vector length mismatch: expected {expected_len}, "
            f"got {len(feature_vector)}. "
            f"Expected features: {expected_names}"
        )

    X = np.array([feature_vector])
    raw = float(bundle["model"].predict(X)[0])

    design_life_years = bundle.get("design_life", _DEFAULT_DESIGN_LIFE_YEARS)

    return _build_result(raw, design_life_years)


def predict_rul2_adjusted(feature_vector: list,
                           risk_factor: float,
                           model_path: str) -> dict:
    """Applies a dampened AHP risk adjustment to RUL 2.

    Uses a 0.3 multiplier (vs. RUL 1's full 1.0) because decommissioning
    timelines are driven mostly by absolute age, not current sensor/risk
    state -- a spike in risk_factor should nudge the estimate, not swing
    it the way it does for operational (failure) RUL.
    """
    result = predict_rul2(feature_vector, model_path)
    r_asset = (risk_factor - 1) / 8
    rul_2_adjusted_raw = result["rul_2_years"] * (1 - r_asset * 0.3)

    bundle = _load_bundle(model_path)
    design_life_years = bundle.get("design_life", _DEFAULT_DESIGN_LIFE_YEARS)

    return _build_result(rul_2_adjusted_raw, design_life_years)
