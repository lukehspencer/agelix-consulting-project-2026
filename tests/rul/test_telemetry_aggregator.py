import pytest

from data.telemetry_aggregator import get_pump_data

REQUIRED_KEYS = [
    "asset_id", "asset_name", "manufacturer", "model_number", "location",
    "expected_lifespan_years",
    "total_runtime_hours", "age_years", "operating_hours_per_day", "rated_flow_rate_gpm",
    "condition_score", "vibration_level", "temperature_celsius",
    "seal_condition", "bearing_condition",
    "number_of_failures_last_3yr", "days_since_maintenance", "maintenance_frequency_days",
    "maintenance_cost_last_year", "maintenance_cost_trend",
    "criticality_raw", "downtime_impact_raw",
    "rolling_vibration_mean", "rolling_vibration_std",
    "rolling_winding_temp_mean", "rolling_spm_temp_mean",
    "rolling_current_mean", "voltage_anomaly_count",
    "true_rul_days",
]


@pytest.fixture(scope="module")
def pumps():
    return get_pump_data()


class TestGetPumpData:
    def test_returns_exactly_5_dicts(self, pumps):
        assert len(pumps) == 5
        for p in pumps:
            assert isinstance(p, dict)

    def test_all_required_keys_present(self, pumps):
        for p in pumps:
            missing = [k for k in REQUIRED_KEYS if k not in p]
            assert missing == [], f"{p['asset_id']} missing keys: {missing}"

    def test_vibration_level_valid_enum(self, pumps):
        for p in pumps:
            assert p["vibration_level"] in ("Normal", "High", "Critical"), \
                f"{p['asset_id']}: {p['vibration_level']}"

    def test_bearing_condition_valid_enum(self, pumps):
        for p in pumps:
            assert p["bearing_condition"] in ("Good", "Worn", "Failed"), \
                f"{p['asset_id']}: {p['bearing_condition']}"

    def test_seal_condition_valid_enum(self, pumps):
        for p in pumps:
            assert p["seal_condition"] in ("Good", "Worn", "Leaking"), \
                f"{p['asset_id']}: {p['seal_condition']}"

    def test_maintenance_cost_trend_valid_enum(self, pumps):
        for p in pumps:
            assert p["maintenance_cost_trend"] in ("Increasing", "Stable", "Decreasing"), \
                f"{p['asset_id']}: {p['maintenance_cost_trend']}"

    def test_days_since_maintenance_non_negative(self, pumps):
        for p in pumps:
            assert isinstance(p["days_since_maintenance"], int)
            assert p["days_since_maintenance"] >= 0, \
                f"{p['asset_id']}: {p['days_since_maintenance']}"

    def test_age_years_positive(self, pumps):
        for p in pumps:
            assert p["age_years"] > 0, f"{p['asset_id']}: {p['age_years']}"

    def test_condition_score_in_range(self, pumps):
        for p in pumps:
            assert 1 <= p["condition_score"] <= 10, \
                f"{p['asset_id']}: {p['condition_score']}"

    def test_c1_default(self, pumps):
        for p in pumps:
            assert p["criticality_raw"] == 7

    def test_c4_default(self, pumps):
        for p in pumps:
            assert p["downtime_impact_raw"] == 6

    def test_c1_override(self):
        pumps = get_pump_data(c1_score=9, c4_score=6)
        for p in pumps:
            assert p["criticality_raw"] == 9

    def test_c4_override(self):
        pumps = get_pump_data(c1_score=7, c4_score=3)
        for p in pumps:
            assert p["downtime_impact_raw"] == 3

    def test_both_overrides(self):
        pumps = get_pump_data(c1_score=2, c4_score=10)
        for p in pumps:
            assert p["criticality_raw"] == 2
            assert p["downtime_impact_raw"] == 10

    def test_pump_ids_are_correct(self, pumps):
        ids = [p["asset_id"] for p in pumps]
        assert ids == [
            "KSB-CALIO-3040-1000",
            "KSB-CALIO-3040-1001",
            "KSB-CALIO-3040-1002",
            "KSB-CALIO-3040-1003",
            "KSB-CALIO-3040-1004",
        ]

    def test_age_years_derived_from_runtime_hours(self, pumps):
        for p in pumps:
            expected = round(p["total_runtime_hours"] / 22 / 365, 2)
            assert p["age_years"] == expected, \
                f"{p['asset_id']}: age_years={p['age_years']}, expected={expected}"
