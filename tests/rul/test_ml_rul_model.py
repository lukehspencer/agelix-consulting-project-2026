from pathlib import Path
from unittest import mock

import pytest

from rul.feature_engineering import build_feature_vector

SAMPLE_PUMP = {
    "total_runtime_hours": 3200.0,
    "operating_hours_per_day": 22,
    "condition_score": 5,
    "number_of_failures_last_3yr": 2,
    "days_since_maintenance": 30,
    "maintenance_cost_last_year": 6500,
    "criticality_raw": 7,
    "downtime_impact_raw": 6,
    "rolling_vibration_mean": 0.81,
    "rolling_vibration_std": 0.11,
    "rolling_winding_temp_mean": 48.7,
    "rolling_spm_temp_mean": 57.5,
    "voltage_anomaly_count": 0,
}

WEIGHTS = [0.2, 0.2, 0.2, 0.2, 0.2]
SCORES = [6.33, 9.0, 1.0, 5.44, 3.67]


class TestPredict:
    def test_returns_correct_keys(self):
        from rul.ml_rul_model import predict

        vec = build_feature_vector(SAMPLE_PUMP, WEIGHTS, SCORES)
        result = predict(vec)
        assert set(result.keys()) == {"rul_years", "ci_low", "ci_high"}

    def test_rul_years_is_non_negative_float(self):
        from rul.ml_rul_model import predict

        vec = build_feature_vector(SAMPLE_PUMP, WEIGHTS, SCORES)
        result = predict(vec)
        assert isinstance(result["rul_years"], float)
        assert result["rul_years"] >= 0.0

    def test_ci_low_non_negative(self):
        from rul.ml_rul_model import predict

        vec = build_feature_vector(SAMPLE_PUMP, WEIGHTS, SCORES)
        result = predict(vec)
        assert result["ci_low"] >= 0.0

    def test_ci_high_greater_than_ci_low(self):
        from rul.ml_rul_model import predict

        vec = build_feature_vector(SAMPLE_PUMP, WEIGHTS, SCORES)
        result = predict(vec)
        assert result["ci_high"] > result["ci_low"]

    def test_ci_width(self):
        from rul.ml_rul_model import predict

        vec = build_feature_vector(SAMPLE_PUMP, WEIGHTS, SCORES)
        result = predict(vec)
        assert result["ci_high"] - result["rul_years"] == pytest.approx(1.5, abs=0.01)

    def test_rul_rounded_to_one_decimal(self):
        from rul.ml_rul_model import predict

        vec = build_feature_vector(SAMPLE_PUMP, WEIGHTS, SCORES)
        result = predict(vec)
        assert result["rul_years"] == round(result["rul_years"], 1)


class TestPredictAdjusted:
    def test_returns_correct_keys(self):
        from rul.ml_rul_model import predict_adjusted

        vec = build_feature_vector(SAMPLE_PUMP, WEIGHTS, SCORES)
        result = predict_adjusted(vec, risk_factor=5.0)
        assert set(result.keys()) == {"rul_years", "ci_low", "ci_high"}

    def test_adjusted_lower_than_raw_when_risk_above_1(self):
        from rul.ml_rul_model import predict, predict_adjusted

        vec = build_feature_vector(SAMPLE_PUMP, WEIGHTS, SCORES)
        raw = predict(vec)
        adjusted = predict_adjusted(vec, risk_factor=5.0)
        assert adjusted["rul_years"] <= raw["rul_years"]

    def test_adjusted_equals_raw_when_risk_is_1(self):
        from rul.ml_rul_model import predict, predict_adjusted

        vec = build_feature_vector(SAMPLE_PUMP, WEIGHTS, SCORES)
        raw = predict(vec)
        adjusted = predict_adjusted(vec, risk_factor=1.0)
        assert adjusted["rul_years"] == raw["rul_years"]

    def test_adjusted_is_zero_when_risk_is_9(self):
        from rul.ml_rul_model import predict_adjusted

        vec = build_feature_vector(SAMPLE_PUMP, WEIGHTS, SCORES)
        adjusted = predict_adjusted(vec, risk_factor=9.0)
        assert adjusted["rul_years"] == 0.0

    def test_adjusted_ci_low_non_negative(self):
        from rul.ml_rul_model import predict_adjusted

        vec = build_feature_vector(SAMPLE_PUMP, WEIGHTS, SCORES)
        result = predict_adjusted(vec, risk_factor=7.0)
        assert result["ci_low"] >= 0.0


class TestMissingModel:
    def test_raises_runtime_error_with_message(self):
        import rul.ml_rul_model as mod
        saved = mod._model

        with mock.patch.object(mod, "_MODEL_PATH", Path("/nonexistent/model.pkl")):
            with pytest.raises(RuntimeError, match="Run rul/train.py first"):
                mod._load_model()

        mod._model = saved
