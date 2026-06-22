from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

_MODEL = "claude-sonnet-4-6"

_CRITERIA_NAMES = [
    "Criticality",
    "Condition",
    "Failure Probability",
    "Downtime Impact",
    "Maintenance Cost Trend",
]


def explain(
    pump: dict,
    weights: list[float],
    scores: list[float],
    risk_factor: float,
    predicted_rul: float,
    ci_low: float,
    ci_high: float,
) -> str:
    prompt = f"""You are an asset reliability engineer analyzing a centrifugal pump.

Asset: {pump["asset_name"]} ({pump["asset_id"]}) at {pump["location"]}

AHP Criteria Weights (expert judgment):
- Criticality:              {weights[0]}
- Condition:                {weights[1]}
- Failure Probability:      {weights[2]}
- Downtime Impact:          {weights[3]}
- Maintenance Cost Trend:   {weights[4]}

Per-Criterion Risk Scores (1-9 Saaty scale):
- Criticality score:             {scores[0]}
- Condition score:               {scores[1]}
- Failure Probability score:     {scores[2]}
- Downtime Impact score:         {scores[3]}
- Maintenance Cost Trend score:  {scores[4]}

Overall Risk Factor: {risk_factor} / 9
ML Predicted RUL:   {predicted_rul} years
Confidence Interval: {ci_low} to {ci_high} years

Raw condition indicators:
- Condition score:          {pump["condition_score"]} / 10
- Vibration level:          {pump["vibration_level"]}
- Seal condition:           {pump["seal_condition"]}
- Bearing condition:        {pump["bearing_condition"]}
- Failures last 3 years:    {pump["number_of_failures_last_3yr"]}
- Days since maintenance:   {pump["days_since_maintenance"]}

In 3-4 sentences explain why this pump has this RUL estimate, what the biggest risk drivers are given the AHP weights, and what maintenance action should be prioritized."""

    try:
        client = anthropic.Anthropic()
        message = client.messages.create(
            model=_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception as exc:
        raise RuntimeError(f"Anthropic API call failed: {exc}") from exc
