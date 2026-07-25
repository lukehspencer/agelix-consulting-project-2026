from pathlib import Path

import joblib
import numpy as np

_CI_HALF_WIDTH = 0.5

_cache = {}


def _load_bundle(model_path: str) -> dict:
    if model_path in _cache:
        return _cache[model_path]

    p = Path(model_path)
    if not p.exists():
        raise FileNotFoundError(
            f"Dynamic model not found at '{model_path}'. "
            "Run rul/dynamic_train.py first to train a model for this dataset."
        )

    bundle = joblib.load(p)
    _cache[model_path] = bundle
    return bundle


def _calibrate_rul(rul_years: float, max_train_rul_years: float | None) -> tuple[float, bool]:
    """Caps RUL predictions from extrapolating far beyond what this asset
    type's own model ever saw in training. Anchored to that model's own
    training label distribution (bundle["max_train_rul_years"], set by
    dynamic_train.py) rather than an asset-type-specific engineering
    lifetime constant, so it applies the same way regardless of what kind
    of asset was uploaded. Returns (calibrated_rul_years, was_calibrated).
    """
    if not max_train_rul_years or max_train_rul_years <= 0:
        return rul_years, False

    if rul_years > max_train_rul_years * 1.5:
        calibrated = 0.4 * rul_years + 0.6 * max_train_rul_years
    elif rul_years > max_train_rul_years:
        calibrated = 0.7 * rul_years + 0.3 * max_train_rul_years
    else:
        return rul_years, False

    return max(0.0, calibrated), True


def predict_dynamic(feature_vector: list,
                    model_path: str = "rul/dynamic_model.pkl") -> dict:
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
    rul_raw = round(max(0.0, raw), 2)

    calibrated_years, calibrated = _calibrate_rul(rul_raw, bundle.get("max_train_rul_years"))
    rul_years = round(calibrated_years, 1)

    return {
        "rul_years": rul_years,
        "rul_raw": rul_raw,
        "calibrated": calibrated,
        "ci_low": round(max(0.0, rul_years - _CI_HALF_WIDTH), 1),
        "ci_high": round(rul_years + _CI_HALF_WIDTH, 1),
    }


def predict_adjusted_dynamic(feature_vector: list,
                              risk_factor: float,
                              model_path: str = "rul/dynamic_model.pkl") -> dict:
    result = predict_dynamic(feature_vector, model_path)
    r_asset = (risk_factor - 1) / 8
    rul_adjusted_raw = round(max(0.0, result["rul_years"] * (1 - r_asset)), 2)

    bundle = _load_bundle(model_path)
    calibrated_years, calibrated = _calibrate_rul(rul_adjusted_raw, bundle.get("max_train_rul_years"))
    rul_adjusted = round(calibrated_years, 1)

    return {
        "rul_years": rul_adjusted,
        "rul_raw": rul_adjusted_raw,
        "calibrated": calibrated,
        "ci_low": round(max(0.0, rul_adjusted - _CI_HALF_WIDTH), 1),
        "ci_high": round(rul_adjusted + _CI_HALF_WIDTH, 1),
    }
