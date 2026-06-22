import math

import pytest

from rul.feature_engineering import (
    build_feature_vector,
    get_feature_names,
    validate_feature_vector,
    NUM_FEATURES,
)

SAMPLE_PUMP = {
    "asset_id": "PUMP-001",
    "asset_name": "Primary Cooling Feed Pump",
    "age_years": 19.26,
    "usage_intensity_pct": 76.0,
    "total_runtime_hours": 152400,
    "operating_hours_per_day": 22,
    "condition_score": 3,
    "number_of_failures_last_3yr": 5,
    "days_since_maintenance": 185,
    "maintenance_cost_last_year": 8500,
}

EQUAL_WEIGHTS = [0.2, 0.2, 0.2, 0.2, 0.2]
SAMPLE_SCORES = [8.11, 9.0, 9.0, 7.22, 9.0]


class TestGetFeatureNames:
    def test_returns_19_names(self):
        names = get_feature_names()
        assert len(names) == NUM_FEATURES

    def test_returns_new_list_each_call(self):
        a = get_feature_names()
        b = get_feature_names()
        assert a == b
        assert a is not b

    def test_first_feature_is_age_years(self):
        assert get_feature_names()[0] == "age_years"

    def test_last_feature_is_risk_factor(self):
        assert get_feature_names()[-1] == "risk_factor"


class TestBuildFeatureVector:
    def test_normal_input(self):
        vec = build_feature_vector(SAMPLE_PUMP, EQUAL_WEIGHTS, SAMPLE_SCORES)
        assert len(vec) == NUM_FEATURES

        assert vec[0] == 19.26
        assert vec[1] == 76.0
        assert vec[2] == 152400
        assert vec[3] == 22
        assert vec[4] == 3
        assert vec[5] == 5
        assert vec[6] == 185
        assert vec[7] == 8500

        for i in range(8, 13):
            assert vec[i] == 0.2

        assert vec[13] == pytest.approx(0.2 * 8.11)
        assert vec[14] == pytest.approx(0.2 * 9.0)
        assert vec[15] == pytest.approx(0.2 * 9.0)
        assert vec[16] == pytest.approx(0.2 * 7.22)
        assert vec[17] == pytest.approx(0.2 * 9.0)

        expected_risk = sum(0.2 * s for s in SAMPLE_SCORES)
        assert vec[18] == pytest.approx(expected_risk)

    def test_unequal_weights(self):
        weights = [0.4, 0.25, 0.15, 0.12, 0.08]
        vec = build_feature_vector(SAMPLE_PUMP, weights, SAMPLE_SCORES)

        assert vec[8] == 0.4
        assert vec[12] == 0.08
        assert vec[13] == pytest.approx(0.4 * 8.11)
        assert vec[17] == pytest.approx(0.08 * 9.0)

        expected_risk = sum(w * s for w, s in zip(weights, SAMPLE_SCORES))
        assert vec[18] == pytest.approx(expected_risk)

    def test_all_values_are_floats(self):
        vec = build_feature_vector(SAMPLE_PUMP, EQUAL_WEIGHTS, SAMPLE_SCORES)
        for val in vec:
            assert isinstance(val, float)

    def test_weights_wrong_length(self):
        with pytest.raises(ValueError, match="weights must have exactly 5"):
            build_feature_vector(SAMPLE_PUMP, [0.5, 0.5], SAMPLE_SCORES)

    def test_scores_wrong_length(self):
        with pytest.raises(ValueError, match="scores must have exactly 5"):
            build_feature_vector(SAMPLE_PUMP, EQUAL_WEIGHTS, [1.0, 2.0, 3.0])

    def test_empty_weights(self):
        with pytest.raises(ValueError, match="weights must have exactly 5"):
            build_feature_vector(SAMPLE_PUMP, [], SAMPLE_SCORES)

    def test_empty_scores(self):
        with pytest.raises(ValueError, match="scores must have exactly 5"):
            build_feature_vector(SAMPLE_PUMP, EQUAL_WEIGHTS, [])

    def test_missing_pump_field(self):
        bad_pump = {k: v for k, v in SAMPLE_PUMP.items() if k != "age_years"}
        with pytest.raises(KeyError):
            build_feature_vector(bad_pump, EQUAL_WEIGHTS, SAMPLE_SCORES)


class TestValidateFeatureVector:
    def test_valid_vector(self):
        vec = build_feature_vector(SAMPLE_PUMP, EQUAL_WEIGHTS, SAMPLE_SCORES)
        validate_feature_vector(vec)

    def test_wrong_length_short(self):
        with pytest.raises(ValueError, match="exactly 19 elements"):
            validate_feature_vector([1.0] * 18)

    def test_wrong_length_long(self):
        with pytest.raises(ValueError, match="exactly 19 elements"):
            validate_feature_vector([1.0] * 20)

    def test_empty_vector(self):
        with pytest.raises(ValueError, match="exactly 19 elements"):
            validate_feature_vector([])

    def test_nan_value(self):
        vec = [1.0] * 19
        vec[4] = float("nan")
        with pytest.raises(ValueError, match="finite number"):
            validate_feature_vector(vec)

    def test_inf_value(self):
        vec = [1.0] * 19
        vec[0] = float("inf")
        with pytest.raises(ValueError, match="finite number"):
            validate_feature_vector(vec)

    def test_negative_inf_value(self):
        vec = [1.0] * 19
        vec[7] = float("-inf")
        with pytest.raises(ValueError, match="finite number"):
            validate_feature_vector(vec)

    def test_non_numeric_value(self):
        vec = [1.0] * 18 + ["not_a_number"]
        with pytest.raises(ValueError, match="finite number"):
            validate_feature_vector(vec)
