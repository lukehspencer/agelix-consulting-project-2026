from unittest import mock

import pytest

from rul.rul_explainer import explain

SAMPLE_PUMP = {
    "asset_id": "KSB-CALIO-3040-1000",
    "asset_name": "KSB Calio 3040 - Unit 1000",
    "location": "Plant 1",
    "condition_score": 3,
    "vibration_level": "High",
    "seal_condition": "Worn",
    "bearing_condition": "Worn",
    "number_of_failures_last_3yr": 2,
    "days_since_maintenance": 30,
    "rolling_vibration_mean": 0.81,
    "rolling_vibration_std": 0.11,
    "rolling_winding_temp_mean": 48.7,
    "rolling_spm_temp_mean": 57.5,
    "voltage_anomaly_count": 0,
}

WEIGHTS = [0.2, 0.2, 0.2, 0.2, 0.2]
SCORES = [6.33, 9.0, 1.0, 5.44, 3.67]
RISK_FACTOR = 5.09
PREDICTED_RUL = 0.1
CI_LOW = 0.0
CI_HIGH = 1.6


def _make_mock_response(text):
    block = mock.MagicMock()
    block.text = text
    resp = mock.MagicMock()
    resp.content = [block]
    return resp


class TestExplain:
    @mock.patch("rul.rul_explainer.anthropic.Anthropic")
    def test_returns_non_empty_string(self, mock_cls):
        mock_client = mock_cls.return_value
        mock_client.messages.create.return_value = _make_mock_response(
            "  This pump has a low RUL due to bearing wear.  "
        )
        result = explain(SAMPLE_PUMP, WEIGHTS, SCORES, RISK_FACTOR, PREDICTED_RUL, CI_LOW, CI_HIGH)
        assert isinstance(result, str)
        assert len(result) > 0
        assert result == "This pump has a low RUL due to bearing wear."

    @mock.patch("rul.rul_explainer.anthropic.Anthropic")
    def test_raises_runtime_error_on_api_failure(self, mock_cls):
        mock_client = mock_cls.return_value
        mock_client.messages.create.side_effect = Exception("connection timeout")
        with pytest.raises(RuntimeError, match="Anthropic API call failed.*connection timeout"):
            explain(SAMPLE_PUMP, WEIGHTS, SCORES, RISK_FACTOR, PREDICTED_RUL, CI_LOW, CI_HIGH)

    @mock.patch("rul.rul_explainer.anthropic.Anthropic")
    def test_prompt_contains_asset_id(self, mock_cls):
        mock_client = mock_cls.return_value
        mock_client.messages.create.return_value = _make_mock_response("Explanation.")
        explain(SAMPLE_PUMP, WEIGHTS, SCORES, RISK_FACTOR, PREDICTED_RUL, CI_LOW, CI_HIGH)
        prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "KSB-CALIO-3040-1000" in prompt

    @mock.patch("rul.rul_explainer.anthropic.Anthropic")
    def test_prompt_contains_predicted_rul(self, mock_cls):
        mock_client = mock_cls.return_value
        mock_client.messages.create.return_value = _make_mock_response("Explanation.")
        explain(SAMPLE_PUMP, WEIGHTS, SCORES, RISK_FACTOR, PREDICTED_RUL, CI_LOW, CI_HIGH)
        prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert str(PREDICTED_RUL) in prompt

    @mock.patch("rul.rul_explainer.anthropic.Anthropic")
    def test_prompt_contains_risk_factor(self, mock_cls):
        mock_client = mock_cls.return_value
        mock_client.messages.create.return_value = _make_mock_response("Explanation.")
        explain(SAMPLE_PUMP, WEIGHTS, SCORES, RISK_FACTOR, PREDICTED_RUL, CI_LOW, CI_HIGH)
        prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert str(RISK_FACTOR) in prompt

    @mock.patch("rul.rul_explainer.anthropic.Anthropic")
    def test_prompt_contains_failure_modes(self, mock_cls):
        mock_client = mock_cls.return_value
        mock_client.messages.create.return_value = _make_mock_response("Explanation.")
        explain(SAMPLE_PUMP, WEIGHTS, SCORES, RISK_FACTOR, PREDICTED_RUL, CI_LOW, CI_HIGH)
        prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "Bearings" in prompt
        assert "Electronics" in prompt
        assert "Motor windings" in prompt

    @mock.patch("rul.rul_explainer.anthropic.Anthropic")
    def test_prompt_contains_telemetry_indicators(self, mock_cls):
        mock_client = mock_cls.return_value
        mock_client.messages.create.return_value = _make_mock_response("Explanation.")
        explain(SAMPLE_PUMP, WEIGHTS, SCORES, RISK_FACTOR, PREDICTED_RUL, CI_LOW, CI_HIGH)
        prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "0.81" in prompt
        assert "48.7" in prompt
        assert "57.5" in prompt

    @mock.patch("rul.rul_explainer.anthropic.Anthropic")
    def test_uses_correct_model(self, mock_cls):
        mock_client = mock_cls.return_value
        mock_client.messages.create.return_value = _make_mock_response("Explanation.")
        explain(SAMPLE_PUMP, WEIGHTS, SCORES, RISK_FACTOR, PREDICTED_RUL, CI_LOW, CI_HIGH)
        assert mock_client.messages.create.call_args.kwargs["model"] == "claude-sonnet-4-6"
