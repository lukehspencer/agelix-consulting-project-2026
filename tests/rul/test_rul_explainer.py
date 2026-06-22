from unittest import mock

import anthropic
import pytest

from rul.rul_explainer import explain

SAMPLE_PUMP = {
    "asset_id": "PUMP-001",
    "asset_name": "Primary Cooling Feed Pump",
    "location": "Plant A / Line 1",
    "condition_score": 3,
    "vibration_level": "Critical",
    "seal_condition": "Leaking",
    "bearing_condition": "Failed",
    "number_of_failures_last_3yr": 5,
    "days_since_maintenance": 185,
}

WEIGHTS = [0.35, 0.25, 0.20, 0.12, 0.08]
SCORES = [8.11, 9.0, 9.0, 7.22, 9.0]
RISK_FACTOR = 8.55
PREDICTED_RUL = 2.3
CI_LOW = 0.8
CI_HIGH = 3.8


def _make_mock_response(text):
    content_block = mock.MagicMock()
    content_block.text = text
    response = mock.MagicMock()
    response.content = [content_block]
    return response


class TestExplain:
    @mock.patch("rul.rul_explainer.anthropic.Anthropic")
    def test_returns_stripped_string(self, mock_cls):
        mock_client = mock_cls.return_value
        mock_client.messages.create.return_value = _make_mock_response(
            "  This pump is in critical condition.  "
        )

        result = explain(
            SAMPLE_PUMP, WEIGHTS, SCORES, RISK_FACTOR, PREDICTED_RUL, CI_LOW, CI_HIGH
        )

        assert result == "This pump is in critical condition."
        assert isinstance(result, str)

    @mock.patch("rul.rul_explainer.anthropic.Anthropic")
    def test_passes_correct_model(self, mock_cls):
        mock_client = mock_cls.return_value
        mock_client.messages.create.return_value = _make_mock_response("Explanation.")

        explain(SAMPLE_PUMP, WEIGHTS, SCORES, RISK_FACTOR, PREDICTED_RUL, CI_LOW, CI_HIGH)

        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["model"] == "claude-sonnet-4-6"

    @mock.patch("rul.rul_explainer.anthropic.Anthropic")
    def test_prompt_contains_asset_identity(self, mock_cls):
        mock_client = mock_cls.return_value
        mock_client.messages.create.return_value = _make_mock_response("Explanation.")

        explain(SAMPLE_PUMP, WEIGHTS, SCORES, RISK_FACTOR, PREDICTED_RUL, CI_LOW, CI_HIGH)

        prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "PUMP-001" in prompt
        assert "Primary Cooling Feed Pump" in prompt
        assert "Plant A / Line 1" in prompt

    @mock.patch("rul.rul_explainer.anthropic.Anthropic")
    def test_prompt_contains_all_weights(self, mock_cls):
        mock_client = mock_cls.return_value
        mock_client.messages.create.return_value = _make_mock_response("Explanation.")

        explain(SAMPLE_PUMP, WEIGHTS, SCORES, RISK_FACTOR, PREDICTED_RUL, CI_LOW, CI_HIGH)

        prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        for w in WEIGHTS:
            assert str(w) in prompt

    @mock.patch("rul.rul_explainer.anthropic.Anthropic")
    def test_prompt_contains_all_scores(self, mock_cls):
        mock_client = mock_cls.return_value
        mock_client.messages.create.return_value = _make_mock_response("Explanation.")

        explain(SAMPLE_PUMP, WEIGHTS, SCORES, RISK_FACTOR, PREDICTED_RUL, CI_LOW, CI_HIGH)

        prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        for s in SCORES:
            assert str(s) in prompt

    @mock.patch("rul.rul_explainer.anthropic.Anthropic")
    def test_prompt_contains_rul_and_ci(self, mock_cls):
        mock_client = mock_cls.return_value
        mock_client.messages.create.return_value = _make_mock_response("Explanation.")

        explain(SAMPLE_PUMP, WEIGHTS, SCORES, RISK_FACTOR, PREDICTED_RUL, CI_LOW, CI_HIGH)

        prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert str(PREDICTED_RUL) in prompt
        assert str(CI_LOW) in prompt
        assert str(CI_HIGH) in prompt
        assert str(RISK_FACTOR) in prompt

    @mock.patch("rul.rul_explainer.anthropic.Anthropic")
    def test_prompt_contains_raw_condition_indicators(self, mock_cls):
        mock_client = mock_cls.return_value
        mock_client.messages.create.return_value = _make_mock_response("Explanation.")

        explain(SAMPLE_PUMP, WEIGHTS, SCORES, RISK_FACTOR, PREDICTED_RUL, CI_LOW, CI_HIGH)

        prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "Critical" in prompt
        assert "Leaking" in prompt
        assert "Failed" in prompt
        assert "185" in prompt
        assert "5" in prompt

    @mock.patch("rul.rul_explainer.anthropic.Anthropic")
    def test_prompt_contains_criteria_labels(self, mock_cls):
        mock_client = mock_cls.return_value
        mock_client.messages.create.return_value = _make_mock_response("Explanation.")

        explain(SAMPLE_PUMP, WEIGHTS, SCORES, RISK_FACTOR, PREDICTED_RUL, CI_LOW, CI_HIGH)

        prompt = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "Criticality" in prompt
        assert "Failure Probability" in prompt
        assert "Downtime Impact" in prompt
        assert "Maintenance Cost Trend" in prompt

    @mock.patch("rul.rul_explainer.anthropic.Anthropic")
    def test_api_failure_raises_runtime_error(self, mock_cls):
        mock_client = mock_cls.return_value
        mock_client.messages.create.side_effect = Exception("connection refused")

        with pytest.raises(RuntimeError, match="Anthropic API call failed.*connection refused"):
            explain(SAMPLE_PUMP, WEIGHTS, SCORES, RISK_FACTOR, PREDICTED_RUL, CI_LOW, CI_HIGH)

    @mock.patch("rul.rul_explainer.anthropic.Anthropic")
    def test_api_auth_error_raises_runtime_error(self, mock_cls):
        mock_client = mock_cls.return_value
        mock_client.messages.create.side_effect = anthropic.AuthenticationError(
            message="invalid api key",
            response=mock.MagicMock(status_code=401),
            body=None,
        )

        with pytest.raises(RuntimeError, match="Anthropic API call failed"):
            explain(SAMPLE_PUMP, WEIGHTS, SCORES, RISK_FACTOR, PREDICTED_RUL, CI_LOW, CI_HIGH)
