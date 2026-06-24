import math

import pytest

from rul.feature_engineering import (
    build_feature_vector,
    get_feature_names,
    validate_feature_vector,
    NUM_FEATURES,
)

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

EQUAL_WEIGHTS = [0.2, 0.2, 0.2, 0.2, 0.2]
SAMPLE_SCORES = [6.33, 9.0, 1.0, 5.44, 3.67]


class TestGetFeatureNames:
    def test_returns_24_names(self):
        names = get_feature_names()
        assert len(names) == NUM_FEATURES

    def test_returns_new_list_each_call(self):
        a = get_feature_names()
        b = get_feature_names()
        assert a == b
        assert a is not b

    def test_first_feature(self):
        assert get_feature_names()[0] == "total_runtime_hours"

    def test_last_feature(self):
        assert get_feature_names()[-1] == "voltage_anomaly_count"

    def test_risk_factor_at_index_18(self):
        assert get_feature_names()[18] == "risk_factor"


class TestBuildFeatureVector:
    def test_returns_exactly_24(self):
        vec = build_feature_vector(SAMPLE_PUMP, EQUAL_WEIGHTS, SAMPLE_SCORES)
        assert len(vec) == NUM_FEATURES

    def test_raw_variables_positions(self):
        vec = build_feature_vector(SAMPLE_PUMP, EQUAL_WEIGHTS, SAMPLE_SCORES)
        assert vec[0] == 3200.0
        assert vec[1] == 22
        assert vec[2] == 5
        assert vec[3] == 2
        assert vec[4] == 30
        assert vec[5] == 6500
        assert vec[6] == 7
        assert vec[7] == 6

    def test_weight_positions(self):
        vec = build_feature_vector(SAMPLE_PUMP, EQUAL_WEIGHTS, SAMPLE_SCORES)
        for i in range(8, 13):
            assert vec[i] == 0.2

    def test_weighted_scores_positions(self):
        vec = build_feature_vector(SAMPLE_PUMP, EQUAL_WEIGHTS, SAMPLE_SCORES)
        assert vec[13] == pytest.approx(0.2 * 6.33)
        assert vec[14] == pytest.approx(0.2 * 9.0)
        assert vec[15] == pytest.approx(0.2 * 1.0)
        assert vec[16] == pytest.approx(0.2 * 5.44)
        assert vec[17] == pytest.approx(0.2 * 3.67)

    def test_risk_factor_equals_sum_of_weighted_scores(self):
        vec = build_feature_vector(SAMPLE_PUMP, EQUAL_WEIGHTS, SAMPLE_SCORES)
        expected_risk = sum(vec[13:18])
        assert vec[18] == pytest.approx(expected_risk)

    def test_rolling_features_positions(self):
        vec = build_feature_vector(SAMPLE_PUMP, EQUAL_WEIGHTS, SAMPLE_SCORES)
        assert vec[19] == 0.81
        assert vec[20] == 0.11
        assert vec[21] == 48.7
        assert vec[22] == 57.5
        assert vec[23] == 0

    def test_unequal_weights(self):
        w = [0.4, 0.25, 0.15, 0.12, 0.08]
        vec = build_feature_vector(SAMPLE_PUMP, w, SAMPLE_SCORES)
        assert vec[8] == 0.4
        assert vec[12] == 0.08
        assert vec[13] == pytest.approx(0.4 * 6.33)
        assert vec[18] == pytest.approx(sum(wi * si for wi, si in zip(w, SAMPLE_SCORES)))

    def test_all_values_are_floats(self):
        vec = build_feature_vector(SAMPLE_PUMP, EQUAL_WEIGHTS, SAMPLE_SCORES)
        for val in vec:
            assert isinstance(val, float)

    def test_weights_wrong_length(self):
        with pytest.raises(ValueError, match="weights must have exactly 5"):
            build_feature_vector(SAMPLE_PUMP, [0.5, 0.5], SAMPLE_SCORES)

    def test_scores_wrong_length(self):
        with pytest.raises(ValueError, match="scores must have exactly 5"):
            build_feature_vector(SAMPLE_PUMP, EQUAL_WEIGHTS, [1.0, 2.0])

    def test_missing_pump_field(self):
        bad_pump = {k: v for k, v in SAMPLE_PUMP.items() if k != "total_runtime_hours"}
        with pytest.raises(KeyError):
            build_feature_vector(bad_pump, EQUAL_WEIGHTS, SAMPLE_SCORES)


class TestValidateFeatureVector:
    def test_valid_vector(self):
        vec = build_feature_vector(SAMPLE_PUMP, EQUAL_WEIGHTS, SAMPLE_SCORES)
        validate_feature_vector(vec)

    def test_wrong_length_short(self):
        with pytest.raises(ValueError, match="exactly 24"):
            validate_feature_vector([1.0] * 23)

    def test_wrong_length_long(self):
        with pytest.raises(ValueError, match="exactly 24"):
            validate_feature_vector([1.0] * 25)

    def test_empty_vector(self):
        with pytest.raises(ValueError, match="exactly 24"):
            validate_feature_vector([])

    def test_nan_value(self):
        vec = [1.0] * 24
        vec[4] = float("nan")
        with pytest.raises(ValueError, match="finite number"):
            validate_feature_vector(vec)

    def test_inf_value(self):
        vec = [1.0] * 24
        vec[0] = float("inf")
        with pytest.raises(ValueError, match="finite number"):
            validate_feature_vector(vec)

    def test_negative_inf_value(self):
        vec = [1.0] * 24
        vec[7] = float("-inf")
        with pytest.raises(ValueError, match="finite number"):
            validate_feature_vector(vec)

    def test_non_numeric_value(self):
        vec = [1.0] * 23 + ["not_a_number"]
        with pytest.raises(ValueError, match="finite number"):
            validate_feature_vector(vec)
