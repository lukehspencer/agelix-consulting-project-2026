import json
import math
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from data.upload_schema import validate_upload, UploadValidationError
from data.column_resolver import resolve, resolve_sensor, is_failure_event, get_sensor_columns
from ahp.dynamic_criteria_scorer import score_asset_dynamic
from ahp.criteria_scoring import convert_to_saaty


PUMP_IDS = [f"KSB-CALIO-3040-{1000+i}" for i in range(5)]

VALID_CRITERIA_CONFIG = {
    "asset_type": "KSB Calio 30-40 Centrifugal Pump",
    "failure_modes": ["Bearing wear", "Electronics overload", "Winding breakdown"],
    "column_roles": {
        "asset_id": "Pump_ID",
        "date": "Date",
        "rul_target": "True_RUL_Days",
        "operating_hours": "Operating_Hours",
        "log_asset_id": "Pump_ID",
        "log_date": "Event_Timestamp",
        "log_event_type": "Event_Type",
        "log_component": "Failed_Component",
    },
    "failure_event_values": ["Failure"],
    "criteria": [
        {
            "id": "C1", "name": "Criticality", "description": "How critical this pump is.",
            "manual_input": True, "default_score": 7, "ui_label": "Criticality Score",
        },
        {
            "id": "C2", "name": "Condition", "description": "Physical condition from vibration.",
            "manual_input": False,
            "primary_column": "Vibration_Score",
            "secondary_columns": ["Winding_Temp_C"],
            "thresholds": [
                {"max": 0.5, "score": 2},
                {"max": 1.0, "score": 4},
                {"max": 2.0, "score": 6},
                {"max": 3.5, "score": 8},
                {"score": 10},
            ],
            "penalties": [
                {
                    "column": "SPM_Temp_C",
                    "description": "SPM temperature penalty",
                    "bands": [
                        {"max": 52.0, "penalty": 0},
                        {"max": 73.0, "penalty": -1},
                        {"penalty": -2},
                    ],
                },
            ],
        },
        {
            "id": "C3", "name": "Failure Probability", "description": "Likelihood of failure.",
            "manual_input": False,
            "primary_column": "Current_A",
            "secondary_columns": [],
            "thresholds": [
                {"max": 0.45, "score": 2},
                {"max": 0.65, "score": 5},
                {"score": 8},
            ],
            "penalties": [],
        },
        {
            "id": "C4", "name": "Downtime Impact", "description": "Cost of downtime.",
            "manual_input": True, "default_score": 6, "ui_label": "Downtime Impact Score",
        },
        {
            "id": "C5", "name": "Maintenance Cost Trend", "description": "Trend of costs.",
            "manual_input": False,
            "primary_column": "Mains_Voltage",
            "secondary_columns": [],
            "thresholds": [
                {"max": 215.0, "score": 7},
                {"max": 240.0, "score": 3},
                {"score": 6},
            ],
            "penalties": [],
        },
    ],
}


@pytest.fixture(scope="module")
def sample_xlsx(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("upload")
    path = tmp / "test_data.xlsx"

    np.random.seed(42)
    rows = []
    for pid in PUMP_IDS:
        hours = 0
        for d in range(30):
            hours += np.random.uniform(20, 24)
            rows.append({
                "Pump_ID": pid,
                "Date": pd.Timestamp("2026-01-01") + pd.Timedelta(days=d),
                "Operating_Hours": round(hours, 1),
                "Speed_RPM": round(1800 + np.random.normal(0, 50)),
                "Current_A": round(0.55 + np.random.normal(0, 0.03), 2),
                "Winding_Temp_C": round(50 + d * 0.5 + np.random.normal(0, 2), 1),
                "SPM_Temp_C": round(55 + np.random.normal(0, 3), 1),
                "Mains_Voltage": round(230 + np.random.normal(0, 5), 1),
                "Fluid_Temp_C": round(25 + np.random.normal(0, 2), 1),
                "Vibration_Score": round(0.3 + d * 0.1 + np.random.exponential(0.1), 3),
                "True_RUL_Days": 29 - d,
            })
    tel = pd.DataFrame(rows)

    log = pd.DataFrame({
        "Log_ID": ["L1", "L2", "L3", "L4", "L5"],
        "Pump_ID": PUMP_IDS,
        "Event_Timestamp": ["2026-01-10", "2026-01-15", "2026-01-20", "2026-01-12", "2026-01-25"],
        "Event_Type": ["Failure", "Maintenance", "Failure", "Maintenance", "Failure"],
        "Failed_Component": ["Bearings", "None", "Electronics", "None", "Motor_Winding"],
        "Root_Cause": ["Mechanical_Wear", "Scheduled_PM", "Thermal_Overload", "Scheduled_PM", "Insulation_Breakdown"],
    })

    with pd.ExcelWriter(str(path), engine="openpyxl") as w:
        tel.to_excel(w, sheet_name="Operational Telemetry", index=False)
        log.to_excel(w, sheet_name="Failure & Maintenance Logs", index=False)

    return str(path)


@pytest.fixture(scope="module")
def schema_summary(sample_xlsx):
    return validate_upload(sample_xlsx)


# ── validate_upload tests ──

class TestValidateUpload:
    def test_success(self, schema_summary):
        s = schema_summary
        for key in [
            "asset_id_column", "date_column", "rul_column",
            "operating_hours_column", "sensor_columns",
            "log_asset_id_column", "log_date_column",
            "log_event_type_column", "log_extra_columns",
            "asset_ids", "row_count", "date_range",
            "sensor_stats", "log_event_type_values",
            "log_extra_column_samples",
        ]:
            assert key in s, f"Missing key: {key}"

        assert len(s["asset_ids"]) == 5
        assert len(s["sensor_columns"]) >= 2
        assert isinstance(s["rul_column"], str) and len(s["rul_column"]) > 0
        assert isinstance(s["operating_hours_column"], str) and len(s["operating_hours_column"]) > 0

    def test_missing_sheet(self, tmp_path):
        path = tmp_path / "bad.xlsx"
        pd.DataFrame({"x": [1]}).to_excel(str(path), sheet_name="Wrong", index=False)
        with pytest.raises(UploadValidationError, match="Missing required sheet"):
            validate_upload(str(path))

    def test_no_rul_column(self, tmp_path):
        path = tmp_path / "no_rul.xlsx"
        tel = pd.DataFrame({
            "Pump_ID": ["P1"] * 15,
            "Date": pd.date_range("2026-01-01", periods=15).tolist(),
            "Operating_Hours": list(range(100, 445, 23)),
            "Sensor_A": [1.0] * 15,
            "Sensor_B": [2.0] * 15,
        })
        log = pd.DataFrame({
            "Log_ID": ["L1"], "Pump_ID": ["P1"],
            "Event_Timestamp": ["2026-01-10"], "Event_Type": ["Failure"],
        })
        with pd.ExcelWriter(str(path), engine="openpyxl") as w:
            tel.to_excel(w, sheet_name="Operational Telemetry", index=False)
            log.to_excel(w, sheet_name="Failure & Maintenance Logs", index=False)

        with pytest.raises(UploadValidationError, match="RUL target column") as exc_info:
            validate_upload(str(path))
        assert "Pump_ID" in str(exc_info.value) or "Sensor_A" in str(exc_info.value)


# ── schema_inferrer tests ──

class TestInferCriteriaConfig:
    def test_validates_unknown_column(self, schema_summary):
        from data.schema_inferrer import _validate_config

        bad_config = json.loads(json.dumps(VALID_CRITERIA_CONFIG))
        bad_config["criteria"][1]["primary_column"] = "FAKE_SENSOR"

        with pytest.raises(RuntimeError, match="FAKE_SENSOR"):
            _validate_config(bad_config, schema_summary)

    def test_success_structure(self, schema_summary):
        from data.schema_inferrer import _validate_config

        config = json.loads(json.dumps(VALID_CRITERIA_CONFIG))
        _validate_config(config, schema_summary)

        assert len(config["criteria"]) == 5
        manual_count = sum(1 for c in config["criteria"] if c["manual_input"])
        assert manual_count == 2

        cr = config["column_roles"]
        for key in ["asset_id", "date", "rul_target", "operating_hours",
                     "log_asset_id", "log_date", "log_event_type", "log_component"]:
            assert key in cr

        assert len(config["failure_event_values"]) > 0


# ── column_resolver tests ──

class TestColumnResolver:
    def test_resolve(self):
        config = VALID_CRITERIA_CONFIG
        row = {"Pump_ID": "P1", "Date": "2026-01-01"}
        assert resolve(row, "asset_id", config) == "P1"

    def test_resolve_required_missing(self):
        config = VALID_CRITERIA_CONFIG
        with pytest.raises(KeyError, match="Pump_ID"):
            resolve({"x": 1}, "asset_id", config, required=True)

    def test_is_failure_event_true(self):
        config = VALID_CRITERIA_CONFIG
        assert is_failure_event({"Event_Type": "Failure"}, config) is True

    def test_is_failure_event_false(self):
        config = VALID_CRITERIA_CONFIG
        assert is_failure_event({"Event_Type": "Maintenance"}, config) is False

    def test_is_failure_event_case_insensitive(self):
        config = VALID_CRITERIA_CONFIG
        assert is_failure_event({"Event_Type": "failure"}, config) is True
        assert is_failure_event({"Event_Type": " Failure "}, config) is True


# ── dynamic_criteria_scorer tests ──

class TestScoreAssetDynamic:
    def test_manual_criterion(self):
        config = VALID_CRITERIA_CONFIG
        row = {"Vibration_Score": 1.0, "SPM_Temp_C": 50.0, "Current_A": 0.5, "Mains_Voltage": 230.0}
        result = score_asset_dynamic(row, config, {"C1": 8, "C4": 5})
        assert result["raw_scores"]["C1"] == 8
        assert result["C1"] == convert_to_saaty(8)

    def test_threshold_band(self):
        config = VALID_CRITERIA_CONFIG
        row = {"Vibration_Score": 1.5, "SPM_Temp_C": 50.0, "Current_A": 0.5, "Mains_Voltage": 230.0}
        result = score_asset_dynamic(row, config, {"C1": 7, "C4": 6})
        assert result["raw_scores"]["C2"] == 6

    def test_missing_column_logs_warning(self, caplog):
        config = VALID_CRITERIA_CONFIG
        row = {"Current_A": 0.5, "Mains_Voltage": 230.0}
        with caplog.at_level(logging.WARNING):
            result = score_asset_dynamic(row, config, {"C1": 7, "C4": 6})
        assert any("Vibration_Score" in r.message for r in caplog.records)
        assert 1 <= result["raw_scores"]["C2"] <= 10


# ── dynamic_aggregator tests ──

class TestAggregateUploadedData:
    def test_returns_5_snapshots(self, sample_xlsx, schema_summary):
        from data.dynamic_aggregator import aggregate_uploaded_data
        snapshots = aggregate_uploaded_data(sample_xlsx, schema_summary, VALID_CRITERIA_CONFIG)
        assert len(snapshots) == 5

    def test_rolling_features_keyed_by_actual_name(self, sample_xlsx, schema_summary):
        from data.dynamic_aggregator import aggregate_uploaded_data
        snapshots = aggregate_uploaded_data(sample_xlsx, schema_summary, VALID_CRITERIA_CONFIG)
        for snap in snapshots:
            assert "rolling_Vibration_Score_mean" in snap
            assert "rolling_Winding_Temp_C_std" in snap
            assert "rolling_vibration_mean" not in snap

    def test_true_rul_days_positive(self, sample_xlsx, schema_summary):
        from data.dynamic_aggregator import aggregate_uploaded_data
        snapshots = aggregate_uploaded_data(sample_xlsx, schema_summary, VALID_CRITERIA_CONFIG)
        for snap in snapshots:
            assert snap["true_rul_days"] >= 0


# ── dynamic_feature_engineering tests ──

class TestDynamicFeatureEngineering:
    def _make_snapshot(self):
        return {
            "total_runtime_hours": 5000.0,
            "failures_last_90_days": 1,
            "days_since_last_event": 10,
            "total_failure_count": 2,
            "rolling_Vibration_Score_mean": 1.5,
            "rolling_Vibration_Score_std": 0.3,
            "rolling_Winding_Temp_C_mean": 65.0,
            "rolling_Winding_Temp_C_std": 5.0,
            "rolling_SPM_Temp_C_mean": 60.0,
            "rolling_SPM_Temp_C_std": 3.0,
            "rolling_Current_A_mean": 0.6,
            "rolling_Current_A_std": 0.05,
            "rolling_Mains_Voltage_mean": 230.0,
            "rolling_Mains_Voltage_std": 5.0,
        }

    def test_vector_length(self):
        from rul.dynamic_feature_engineering import (
            build_dynamic_feature_vector, get_dynamic_feature_names,
        )
        snap = self._make_snapshot()
        names = get_dynamic_feature_names(VALID_CRITERIA_CONFIG)
        vec = build_dynamic_feature_vector(
            snap, VALID_CRITERIA_CONFIG, [0.2] * 5,
            {"C1": 7, "C2": 5, "C3": 4, "C4": 6, "C5": 3},
        )
        assert len(vec) == len(names)

    def test_all_finite(self):
        from rul.dynamic_feature_engineering import build_dynamic_feature_vector
        snap = self._make_snapshot()
        vec = build_dynamic_feature_vector(
            snap, VALID_CRITERIA_CONFIG, [0.2] * 5,
            {"C1": 7, "C2": 5, "C3": 4, "C4": 6, "C5": 3},
        )
        for v in vec:
            assert math.isfinite(v), f"Non-finite value: {v}"


# ── dynamic_train tests ──

class TestTrainDynamicModel:
    def test_trains_and_saves(self, sample_xlsx, schema_summary, tmp_path):
        from rul.dynamic_train import train_dynamic_model

        model_path = str(tmp_path / "test_model.pkl")
        result = train_dynamic_model(
            sample_xlsx, schema_summary, VALID_CRITERIA_CONFIG,
            model_output_path=model_path,
        )

        assert Path(model_path).exists()
        assert result["train_rmse"] >= 0
        assert result["test_rmse"] >= 0
        assert result["n_train_samples"] > 0
        assert result["n_test_samples"] > 0

        import joblib
        bundle = joblib.load(model_path)
        assert "feature_names" in bundle
        assert "criteria_config" in bundle
        assert "schema_summary" in bundle
        assert len(bundle["feature_names"]) == len(result["feature_names"])
