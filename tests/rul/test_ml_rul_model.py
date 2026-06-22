import os
from pathlib import Path
from unittest import mock

import pytest

from rul.feature_engineering import build_feature_vector

SAMPLE_PUMP = {
    "age_years": 10.0,
    "usage_intensity_pct": 76.0,
    "total_runtime_hours": 50000,
    "operating_hours_per_day": 18,
    "condition_score": 6,
    "number_of_failures_last_3yr": 2,
    "days_since_maintenance": 90,
    "maintenance_cost_last_year": 3200,
}

WEIGHTS = [0.2, 0.2, 0.2, 0.2, 0.2]
SCORES = [5.0, 5.0, 5.0, 5.0, 5.0]


class TestPredict:
    def test_returns_dict_with_correct_keys(self):
        from rul.ml_rul_model import predict

        vec = build_feature_vector(SAMPLE_PUMP, WEIGHTS, SCORES)
        result = predict(vec)
        assert isinstance(result, dict)
        assert set(result.keys()) == {"rul_years", "ci_low", "ci_high"}

    def test_rul_years_is_non_negative_float(self):
        from rul.ml_rul_model import predict

        vec = build_feature_vector(SAMPLE_PUMP, WEIGHTS, SCORES)
        result = predict(vec)
        assert isinstance(result["rul_years"], float)
        assert result["rul_years"] >= 0.0

    def test_confidence_interval_surrounds_prediction(self):
        from rul.ml_rul_model import predict

        vec = build_feature_vector(SAMPLE_PUMP, WEIGHTS, SCORES)
        result = predict(vec)
        assert result["ci_low"] <= result["rul_years"]
        assert result["ci_high"] >= result["rul_years"]

    def test_ci_low_is_non_negative(self):
        from rul.ml_rul_model import predict

        old_pump = {**SAMPLE_PUMP, "age_years": 24.0, "condition_score": 1}
        vec = build_feature_vector(old_pump, WEIGHTS, SCORES)
        result = predict(vec)
        assert result["ci_low"] >= 0.0

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

    def test_different_inputs_produce_different_predictions(self):
        from rul.ml_rul_model import predict

        vec_young = build_feature_vector(
            {**SAMPLE_PUMP, "age_years": 2.0, "condition_score": 9},
            WEIGHTS,
            SCORES,
        )
        vec_old = build_feature_vector(
            {**SAMPLE_PUMP, "age_years": 22.0, "condition_score": 2},
            WEIGHTS,
            SCORES,
        )
        assert predict(vec_young)["rul_years"] != predict(vec_old)["rul_years"]


class TestMissingModel:
    def test_raises_file_not_found_with_message(self):
        with mock.patch(
            "rul.ml_rul_model._MODEL_PATH",
            Path("/nonexistent/model.pkl"),
        ):
            import rul.ml_rul_model as mod
            old_model = mod._model
            mod._model = None
            try:
                with pytest.raises(FileNotFoundError, match="Run rul/train.py first"):
                    mod.predict([1.0] * 19)
            finally:
                mod._model = old_model
