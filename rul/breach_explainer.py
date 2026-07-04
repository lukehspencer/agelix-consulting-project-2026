from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

_MODEL = "claude-sonnet-4-6"


def _fallback_text(breach: dict) -> str:
    return (
        f"{breach['column']} has exceeded its threshold by "
        f"{breach['exceeded_pct'] * 100:.0f}%. Immediate inspection recommended."
    )


def explain_breach(asset_snapshot: dict, breach: dict, criteria_config: dict,
                    retrieved_context: dict = None) -> str:
    asset_id = asset_snapshot.get("asset_id", "unknown")
    asset_type = criteria_config.get("asset_type", "unknown asset")

    criterion = next(
        (c for c in criteria_config.get("criteria", []) if c.get("id") == breach.get("criterion_id")),
        None,
    )
    criterion_name = criterion.get("name") if criterion else breach.get("criterion_name", breach.get("criterion_id"))
    criterion_desc = criterion.get("description", "") if criterion else ""

    failure_modes = criteria_config.get("failure_modes", [])
    fm_block = "\n".join(f"- {m}" for m in failure_modes) if failure_modes else "- Not specified"

    rag_block = ""
    if retrieved_context and retrieved_context.get("retrieval_available"):
        guidance = retrieved_context.get("maintenance_guidance", [])
        if guidance:
            rag_block = "\nRETRIEVED STANDARD: " + "\n".join(guidance) + "\n"

    try:
        exceeded_pct = breach["exceeded_pct"] * 100
    except (KeyError, TypeError):
        return _fallback_text(breach)

    prompt = f"""You are an asset reliability engineer reviewing a threshold breach alert.

Asset: {asset_id} ({asset_type})

Breached Criterion: {criterion_name}
Description: {criterion_desc}

Sensor: {breach.get('column')}
Current Value: {breach.get('current_value')}
Threshold: {breach.get('threshold_max')}
Exceeded By: {exceeded_pct:.0f}%
Severity: {breach.get('severity')}

Known Failure Modes for {asset_type}:
{fm_block}
{rag_block}
In 2-3 sentences, describe what this threshold breach means for this asset, which failure mode it indicates, and what immediate action the technician should take. Be specific — name the sensor, the value, and the recommended action. If a retrieved standard is provided, cite it by describing the relevant limit."""

    try:
        client = anthropic.Anthropic()
        message = client.messages.create(
            model=_MODEL,
            max_tokens=350,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception:
        return _fallback_text(breach)


def explain_all_breaches(asset_snapshot: dict, breaches: list[dict],
                          criteria_config: dict,
                          retrieved_context: dict = None) -> list[dict]:
    results = []

    for breach in breaches:
        if breach.get("severity") not in ("high", "medium"):
            continue

        alert_text = explain_breach(asset_snapshot, breach, criteria_config, retrieved_context)
        results.append({
            "criterion_id": breach.get("criterion_id"),
            "criterion_name": breach.get("criterion_name"),
            "column": breach.get("column"),
            "severity": breach.get("severity"),
            "alert_text": alert_text,
        })

    return results
