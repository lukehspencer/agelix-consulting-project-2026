from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

_MODEL = "claude-sonnet-4-6"


def explain(
    pump: dict,
    weights: list[float],
    scores: list[float],
    risk_factor: float,
    predicted_rul: float,
    ci_low: float,
    ci_high: float,
) -> str:
    prompt = f"""You are an asset reliability engineer analyzing a KSB Calio 30-40 glandless circulator pump.

Asset: {pump["asset_id"]} (KSB Calio 30-40)

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
ML Predicted RUL: {predicted_rul} years
Confidence Interval: {ci_low} to {ci_high} years

Key Telemetry Indicators:
- Rolling vibration mean:       {pump.get("rolling_vibration_mean", "N/A")} (normal range: below 0.5)
- Rolling winding temp mean:    {pump.get("rolling_winding_temp_mean", "N/A")} C (max safe: 110C)
- Rolling SPM temp mean:        {pump.get("rolling_spm_temp_mean", "N/A")} C (max safe: 105C)
- Voltage anomaly count:        {pump.get("voltage_anomaly_count", "N/A")} days outside 207-253V
- Days since maintenance:       {pump.get("days_since_maintenance", "N/A")}

Known Failure Modes for KSB Calio 30-40:
- Bearings (ceramic/carbon): risk from dry running, cavitation, abrasive wear. Key signal: vibration spikes.
- Electronics (SPM control module): risk from thermal stress and voltage surges. Key signal: SPM temp and mains voltage anomalies.
- Motor windings (Class F insulation): risk from sustained temperature above 110C. Key signal: winding temp.

In 3-4 sentences explain why this pump has this RUL estimate, what the biggest risk drivers are given the AHP weights, and what maintenance action should be prioritized immediately."""

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
