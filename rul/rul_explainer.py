from pathlib import Path

import anthropic
from dotenv import load_dotenv

from ahp.ahp_constants import CRITERIA

load_dotenv(Path(__file__).parent.parent / ".env")

_MODEL = "claude-sonnet-4-6"

_DEFAULT_FAILURE_MODES = [
    "Bearings (ceramic/carbon): risk from dry running, cavitation, abrasive wear. Key signal: vibration spikes.",
    "Electronics (SPM control module): risk from thermal stress and voltage surges. Key signal: SPM temp and mains voltage anomalies.",
    "Motor windings (Class F insulation): risk from sustained temperature above 110C. Key signal: winding temp.",
]

# Default-fleet sensor warning/critical bands, sourced from the KSB Calio
# engineering specs and C2 condition-scoring penalty bands (see CLAUDE.md).
# Only used to backfill CURRENT SENSOR READINGS when a caller supplies a raw
# `pump` dict instead of a pre-built asset_context -- i.e. the frozen
# rul/api.py default-fleet endpoint, which has no threshold data of its own.
_DEFAULT_FLEET_SENSOR_SPECS = [
    ("Vibration Score (rolling mean)", "rolling_vibration_mean", 1.0, 2.5),
    ("Winding Temp (rolling mean, C)", "rolling_winding_temp_mean", 77.0, 99.0),
    ("SPM Temp (rolling mean, C)", "rolling_spm_temp_mean", 73.0, 94.0),
    ("Current (rolling mean, A)", "rolling_current_mean", 0.6825, 0.819),
]

_SYSTEM_PROMPT = (
    "You are a senior reliability engineer providing a maintenance assessment "
    "for an industrial asset. You have access to real sensor data, risk "
    "scores, and predictive model outputs. Your assessment must be specific, "
    "data-driven, and actionable. Never give generic advice. Every statement "
    "must reference actual numbers from the data provided."
)


def _fmt(value, spec="{:.3f}", default="N/A"):
    """Defensive numeric formatting -- a missing/None value never crashes
    prompt building, it just renders as `default`."""
    if value is None:
        return default
    try:
        return spec.format(value)
    except (TypeError, ValueError):
        return str(value)


def _build_context_from_legacy_args(
    pump, weights, scores, risk_factor, predicted_rul, ci_low, ci_high,
    asset_type, failure_modes, sensor_context,
) -> dict:
    """Builds an asset_context dict from the pre-rewrite call shape (pump,
    weights, scores, risk_factor, predicted_rul, ci_low, ci_high, ...).

    This is what keeps the frozen rul/api.py default-fleet endpoint working
    unmodified -- it still calls explain() with these individual keyword
    arguments, never an asset_context dict. Fields the legacy shape can't
    supply (breaches, per-sensor thresholds, physics projection, model
    consensus, next PM date) fall back to empty/unknown defaults so the new
    prompt still renders a coherent assessment rather than crashing.
    """
    pump = pump or {}
    weights = weights or []
    scores = scores or []
    names = CRITERIA if len(weights) == len(CRITERIA) else [f"C{i + 1}" for i in range(len(weights))]

    predicted_rul_days = round(predicted_rul * 365) if predicted_rul is not None else None
    ci_low_days = round(ci_low * 365) if ci_low is not None else None
    ci_high_days = round(ci_high * 365) if ci_high is not None else None

    if sensor_context is not None:
        # Plain {sensor: value} dict, no threshold data available.
        sensor_readings = [(name, value, None, None) for name, value in sensor_context.items()]
    else:
        sensor_readings = [
            (label, pump.get(key), warn, crit)
            for label, key, warn, crit in _DEFAULT_FLEET_SENSOR_SPECS
            if pump.get(key) is not None
        ]

    return {
        "asset_id": pump.get("asset_id", "unknown"),
        "asset_type": asset_type,
        "snapshot_date": pump.get("snapshot_date", "unknown"),
        "days_since_last_event": pump.get(
            "days_since_maintenance", pump.get("days_since_last_event", "unknown")
        ),
        "predicted_rul_days": predicted_rul_days,
        "predicted_rul_years": predicted_rul,
        "primary_source": "ml",
        "ml_rul_days": predicted_rul_days,
        "physics_rul_days": None,
        "ci_low_days": ci_low_days,
        "ci_high_days": ci_high_days,
        "consensus": "unknown",
        "risk_factor": risk_factor,
        "criterion_scores": dict(zip(names, scores)),
        "criterion_weights": dict(zip(names, weights)),
        "sensor_readings": sensor_readings,
        "breaches": [],
        "failure_modes": failure_modes if failure_modes is not None else list(_DEFAULT_FAILURE_MODES),
        "next_pm_date": None,
    }


def _sensor_readings_block(sensor_readings) -> str:
    if not sensor_readings:
        return "  No sensor readings available."

    lines = []
    for sensor, value, warn, crit in sensor_readings:
        if value is None:
            lines.append(f"  {sensor}: N/A")
            continue
        if warn is not None and crit is not None:
            if value >= crit:
                status = "CRITICAL"
            elif value >= warn:
                status = "WARNING"
            else:
                status = "NORMAL"
            lines.append(
                f"  {sensor}: {value:.3f} (warning: {warn:.3f}, critical: {crit:.3f}, status: {status})"
            )
        else:
            lines.append(f"  {sensor}: {value:.3f} (warning: N/A, critical: N/A, status: UNKNOWN)")
    return "\n".join(lines)


def _breach_text(breaches) -> str:
    if breaches:
        return "\n".join(
            f"  BREACH: {b['column']} = {b['current_value']:.3f} "
            f"(limit: {b['threshold_max']:.3f}, "
            f"{b['exceeded_pct'] * 100:.0f}% over, "
            f"{b['severity'].upper()} severity)"
            for b in breaches
        )
    return "  No threshold breaches currently detected."


def _criterion_scores_block(criterion_scores) -> str:
    if not criterion_scores:
        return "  No criterion scores available."
    return "\n".join(f"  {name}: {score:.2f}/9.0" for name, score in criterion_scores.items())


def _criterion_weights_block(criterion_weights) -> str:
    if not criterion_weights:
        return "  No criterion weights available."
    return "\n".join(f"  {name}: {weight:.1%}" for name, weight in criterion_weights.items())


def _failure_modes_block(failure_modes) -> str:
    modes = failure_modes if failure_modes else _DEFAULT_FAILURE_MODES
    return "\n".join(f"  - {mode}" for mode in modes)


def _retrieved_context_block(retrieved_context) -> str:
    if not retrieved_context or not retrieved_context.get("retrieval_available"):
        return ""

    parts = []
    if retrieved_context.get("failure_precedents"):
        parts.append("Failure Precedents:")
        for chunk in retrieved_context["failure_precedents"]:
            parts.append(f"  - {chunk}")
    if retrieved_context.get("maintenance_guidance"):
        parts.append("Maintenance Standards:")
        for chunk in retrieved_context["maintenance_guidance"]:
            parts.append(f"  - {chunk}")
    if not parts:
        return ""

    return (
        "RETRIEVED MAINTENANCE KNOWLEDGE\n"
        "===============================\n"
        + "\n".join(parts)
        + "\n\nIf relevant, cite the most relevant precedent by describing the case "
        "(do not quote verbatim)."
    )


def explain(
    asset_context: dict = None,
    retrieved_context: dict = None,
    *,
    pump: dict = None,
    weights: list = None,
    scores: list = None,
    risk_factor: float = None,
    predicted_rul: float = None,
    ci_low: float = None,
    ci_high: float = None,
    asset_type: str = "KSB Calio 30-40",
    failure_modes: list = None,
    sensor_context: dict = None,
) -> str:
    """Generates a Claude-written maintenance assessment for one asset.

    Callers should pass a pre-built `asset_context` dict (see upload/api.py's
    POST /upload/explain, which assembles the dynamic-asset shape from the
    latest /upload/predict-all result). The legacy individual keyword fields
    (`pump`, `weights`, `scores`, `risk_factor`, `predicted_rul`, `ci_low`,
    `ci_high`, `asset_type`, `failure_modes`, `sensor_context`) remain
    accepted so the frozen rul/api.py default-fleet endpoint keeps working
    unmodified -- when `asset_context` is omitted, it's built from those
    fields via `_build_context_from_legacy_args()` instead.
    """
    ctx = (
        asset_context
        if asset_context is not None
        else _build_context_from_legacy_args(
            pump, weights, scores, risk_factor, predicted_rul, ci_low, ci_high,
            asset_type, failure_modes, sensor_context,
        )
    )

    predicted_rul_days = ctx.get("predicted_rul_days")
    predicted_rul_years = ctx.get("predicted_rul_years")
    if predicted_rul_years is None and predicted_rul_days is not None:
        predicted_rul_years = predicted_rul_days / 365

    retrieved_block = _retrieved_context_block(retrieved_context)

    user_prompt = f"""
ASSET ASSESSMENT REQUEST
========================
Asset ID: {ctx.get("asset_id", "unknown")}
Asset Type: {ctx.get("asset_type") or "unknown"}
Assessment Date: {ctx.get("snapshot_date", "unknown")}
Days Since Last Maintenance: {ctx.get("days_since_last_event", "unknown")}

PREDICTED REMAINING USEFUL LIFE
================================
Primary RUL Estimate: {_fmt(predicted_rul_days, "{:.0f}")} days ({_fmt(predicted_rul_years, "{:.1f}")} years)
Source: {ctx.get("primary_source") or "unknown"} model
ML Model Estimate: {_fmt(ctx.get("ml_rul_days"), "{:.0f}")} days
Physics Projection: {_fmt(ctx.get("physics_rul_days"), "{:.0f}")} days
Confidence Interval: {_fmt(ctx.get("ci_low_days"), "{:.0f}")} -- {_fmt(ctx.get("ci_high_days"), "{:.0f}")} days
Model Consensus: {ctx.get("consensus") or "unknown"}
Next Recommended PM Date: {ctx.get("next_pm_date") or "unknown"}

AHP RISK ASSESSMENT
====================
Overall Risk Factor: {_fmt(ctx.get("risk_factor"), "{:.2f}")} / 9.0
  (1=lowest risk, 9=highest risk)

Criterion Scores (higher = more risk):
{_criterion_scores_block(ctx.get("criterion_scores"))}

AHP Weights (user-defined priorities):
{_criterion_weights_block(ctx.get("criterion_weights"))}

CURRENT SENSOR READINGS
========================
{_sensor_readings_block(ctx.get("sensor_readings"))}

THRESHOLD BREACHES DETECTED
============================
{_breach_text(ctx.get("breaches"))}

KNOWN FAILURE MODES FOR THIS ASSET TYPE
=========================================
{_failure_modes_block(ctx.get("failure_modes"))}

{retrieved_block}

ASSESSMENT INSTRUCTIONS
========================
Write a 5-sentence maintenance assessment following this exact structure:

Sentence 1 -- CURRENT CONDITION:
State the overall health status using the risk factor and the single most concerning sensor reading with its exact value and how far it is from the critical threshold.

Sentence 2 -- ROOT CAUSE ANALYSIS:
Identify which specific criterion score is highest and explain what physical failure mode it indicates, referencing the exact criterion score and the sensors driving it.

Sentence 3 -- BREACH DETAILS (if any breaches exist):
Name each breached sensor by name, state the exact current value and threshold, and state the severity. If no breaches, describe which sensors are trending toward their thresholds.

Sentence 4 -- RUL INTERPRETATION:
State the predicted RUL in days, which model produced it and why, and what the confidence interval means for maintenance planning. If models diverge, explain what each model is seeing differently.

Sentence 5 -- SPECIFIC ACTION:
Give one specific maintenance action tied to the identified failure mode, state exactly when it should occur (use the actual date not just "X days"), and reference the next PM date from the MTBM calculation.

DO NOT:
- Use phrases like "it is recommended" or "should consider"
- Give generic pump maintenance advice
- Repeat the same information twice
- Use vague timeframes like "soon" or "in the near future"
- Write more than 5 sentences
"""

    try:
        client = anthropic.Anthropic()
        message = client.messages.create(
            model=_MODEL,
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return message.content[0].text.strip()
    except Exception as exc:
        raise RuntimeError(f"Anthropic API call failed: {exc}") from exc
