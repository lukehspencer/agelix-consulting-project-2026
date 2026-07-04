from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

_MODEL = "claude-sonnet-4-6"

_DEFAULT_FAILURE_MODES = [
    "Bearings (ceramic/carbon): risk from dry running, cavitation, abrasive wear. Key signal: vibration spikes.",
    "Electronics (SPM control module): risk from thermal stress and voltage surges. Key signal: SPM temp and mains voltage anomalies.",
    "Motor windings (Class F insulation): risk from sustained temperature above 110C. Key signal: winding temp.",
]


def explain(
    pump: dict,
    weights: list[float],
    scores: list[float],
    risk_factor: float,
    predicted_rul: float,
    ci_low: float,
    ci_high: float,
    asset_type: str = "KSB Calio 30-40",
    failure_modes: list = None,
    sensor_context: dict = None,
    retrieved_context: dict = None,
) -> str:
    if sensor_context is not None:
        telemetry_lines = "\n".join(
            f"- {key}: {value:.2f}" for key, value in sensor_context.items()
        )
        telemetry_block = f"Key Telemetry Indicators:\n{telemetry_lines}"
    else:
        telemetry_block = f"""Key Telemetry Indicators:
- Rolling vibration mean:       {pump.get("rolling_vibration_mean", "N/A")} (normal range: below 0.5)
- Rolling winding temp mean:    {pump.get("rolling_winding_temp_mean", "N/A")} C (max safe: 110C)
- Rolling SPM temp mean:        {pump.get("rolling_spm_temp_mean", "N/A")} C (max safe: 105C)
- Voltage anomaly count:        {pump.get("voltage_anomaly_count", "N/A")} days outside 207-253V
- Days since maintenance:       {pump.get("days_since_maintenance", "N/A")}"""

    if failure_modes is not None:
        fm_lines = "\n".join(f"- {m}" for m in failure_modes)
        failure_block = f"Known Failure Modes for {asset_type}:\n{fm_lines}"
    else:
        fm_lines = "\n".join(f"- {m}" for m in _DEFAULT_FAILURE_MODES)
        failure_block = f"Known Failure Modes for KSB Calio 30-40:\n{fm_lines}"

    asset_id = pump.get("asset_id", "unknown")

    correlation_block = ""
    correlation_instruction = ""
    correlation_summary = pump.get("correlation_summary")
    if correlation_summary:
        stress_idx = correlation_summary.get("composite_stress_index", 0.0)
        top_pairs = correlation_summary.get("top_correlated_pairs", [])[:3]
        pair_lines = "\n".join(
            f"{p.get('col_a')} x {p.get('col_b')}: correlation = {p.get('correlation', 0.0):.2f} "
            f"({'co-degrading' if p.get('correlation', 0.0) > 0 else 'inverse'})"
            for p in top_pairs
        )
        correlation_block = f"""
MULTI-SENSOR CORRELATION ANALYSIS:
Composite stress index: {stress_idx:.3f}
(0 = no sensors degrading, 1 = all sensors degrading simultaneously)
Strongest correlated sensor pairs:
{pair_lines}
"""
        correlation_instruction = (
            " If the composite stress index is above 0.3 or any sensor pair shows "
            "correlation above 0.6, mention the multi-sensor degradation pattern in "
            "your explanation as it is a stronger failure indicator than any single "
            "sensor alone."
        )

    rag_block = ""
    cite_instruction = ""
    if retrieved_context and retrieved_context.get("retrieval_available"):
        rag_parts = []
        if retrieved_context.get("failure_precedents"):
            rag_parts.append("Failure Precedents:")
            for chunk in retrieved_context["failure_precedents"]:
                rag_parts.append(f"  - {chunk}")
        if retrieved_context.get("maintenance_guidance"):
            rag_parts.append("Maintenance Standards:")
            for chunk in retrieved_context["maintenance_guidance"]:
                rag_parts.append(f"  - {chunk}")
        if rag_parts:
            rag_block = "\nRETRIEVED MAINTENANCE KNOWLEDGE:\n" + "\n".join(rag_parts) + "\n"
            cite_instruction = " If relevant, cite the most relevant precedent by describing the case (do not quote verbatim)."

    prompt = f"""You are an asset reliability engineer analyzing a {asset_type}.

Asset: {asset_id} ({asset_type})

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

{telemetry_block}
{correlation_block}
{failure_block}
{rag_block}
In 3-4 sentences explain why this pump has this RUL estimate, what the biggest risk drivers are given the AHP weights, and what maintenance action should be prioritized immediately.{cite_instruction}{correlation_instruction}"""

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
