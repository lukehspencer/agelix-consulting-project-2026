import json
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 2500


def _build_prompt(s: dict, retrieved_context: dict = None) -> str:
    sensor_lines = []
    for col in s["sensor_columns"]:
        st = s["sensor_stats"][col]
        sensor_lines.append(
            f'  "{col}": min={st["min"]:.3f}, max={st["max"]:.3f}, '
            f'mean={st["mean"]:.3f}, std={st["std"]:.3f}, '
            f'p25={st["p25"]:.3f}, p75={st["p75"]:.3f}'
        )
    sensor_block = "\n".join(sensor_lines)

    extra_samples = json.dumps(s.get("log_extra_column_samples", {}), indent=2)

    rag_block = ""
    if retrieved_context and retrieved_context.get("retrieval_available"):
        rag_parts = []
        if retrieved_context.get("standards_chunks"):
            rag_parts.append("Engineering Standards and Manuals:")
            for chunk in retrieved_context["standards_chunks"]:
                rag_parts.append(f"  - {chunk}")
        if retrieved_context.get("similar_configs"):
            rag_parts.append("Similar Past CriteriaConfigs:")
            for chunk in retrieved_context["similar_configs"]:
                rag_parts.append(f"  - {chunk}")
        if retrieved_context.get("failure_case_chunks"):
            rag_parts.append("Known Failure Cases:")
            for chunk in retrieved_context["failure_case_chunks"]:
                rag_parts.append(f"  - {chunk}")
        if rag_parts:
            rag_block = "\nRETRIEVED DOMAIN KNOWLEDGE:\n" + "\n".join(rag_parts) + "\n"

    return f"""You are an asset reliability engineer designing an AHP (Analytic Hierarchy
Process) risk scoring system for an uploaded asset dataset.

DATASET OVERVIEW:
- Asset IDs (sample): {s["asset_ids"][:5]}
- Date range: {s["date_range"]["min"]} to {s["date_range"]["max"]}
- Total rows: {s["row_count"]}
- Asset ID column name: {s["asset_id_column"]}
- Date column name: {s["date_column"]}
- RUL target column name: {s["rul_column"]}
- Operating hours column name: {s["operating_hours_column"]}

SENSOR COLUMNS AND STATISTICS:
{sensor_block}

FAILURE & MAINTENANCE LOG:
- Event type column name: {s.get("log_event_type_column", "unknown")}
- Unique event type values found: {s.get("log_event_type_values", [])}
- Additional log columns and sample values: {extra_samples}
- Available log sheet column names (use ONLY these exact names): {list((s.get("log_extra_columns") or []) + [c for c in [s.get("log_asset_id_column"), s.get("log_date_column"), s.get("log_event_type_column")] if c])}
{rag_block}
TASK:
Design between 5 and 7 AHP criteria, choosing the number that best represents
the distinct risk dimensions present in the data. Use exactly 5 if the data
supports it, more only if genuinely distinct additional risk dimensions exist.
Rules:
1. At least 1 and at most 2 criteria must be marked manual_input: true.
   The rest must be derived from the sensor columns listed above.
2. For each sensor-derived criterion, use only column names that appear
   exactly in the sensor columns list above. Do not invent column names.
3. Set scoring thresholds based on the actual min/max/p25/p75 statistics
   provided -- not generic defaults. Higher score = higher risk (1-10).
4. In column_roles, reproduce the exact column names as given to you above.
   Do not rename, normalize, or guess at column names.
5. In failure_event_values, list the exact string values from the
   unique event type values that indicate a failure event (not maintenance).
6. Infer the asset type from column names and data statistics.

Respond with ONLY a valid JSON object. No preamble, no markdown fences,
no trailing text. The JSON must conform exactly to this structure:

{{
  "asset_type": "<inferred asset type string>",
  "failure_modes": ["<mode 1>", "<mode 2>", "<mode 3>"],

  "column_roles": {{
    "asset_id": "<exact column name from dataset>",
    "date": "<exact column name from dataset>",
    "rul_target": "<exact column name from dataset>",
    "operating_hours": "<exact column name from dataset>",
    "log_asset_id": "<exact column name from log sheet>",
    "log_date": "<exact column name from log sheet>",
    "log_event_type": "<exact column name from log sheet>",
    "log_component": "<exact column name from log sheet, or null if absent>"
  }},

  "failure_event_values": ["<exact string value(s) that mean Failure in log_event_type column>"],

  "criteria": [
    {{
      "id": "C1",
      "name": "<criterion name>",
      "description": "<one sentence>",
      "manual_input": true,
      "default_score": 7,
      "ui_label": "<label for the input in the dashboard>"
    }},
    {{
      "id": "C2",
      "name": "<criterion name>",
      "description": "<one sentence>",
      "manual_input": false,
      "primary_column": "<exact sensor column name>",
      "secondary_columns": ["<exact sensor column name or empty list>"],
      "thresholds": [
        {{"max": 1.0, "score": 2}},
        {{"max": 3.0, "score": 5}},
        {{"score": 9}}
      ],
      "penalties": [
        {{
          "column": "<exact sensor column name>",
          "description": "<what this penalizes>",
          "bands": [
            {{"max": 50.0, "penalty": 0}},
            {{"max": 80.0, "penalty": -1}},
            {{"penalty": -2}}
          ]
        }}
      ]
    }}
  ]
}}"""


def _validate_config(config: dict, schema_summary: dict) -> None:
    required_roles = [
        "asset_id", "date", "rul_target", "operating_hours",
        "log_asset_id", "log_date", "log_event_type", "log_component",
    ]
    cr = config.get("column_roles", {})
    for role in required_roles:
        if role not in cr:
            raise RuntimeError(
                f"Schema inferrer: column_roles missing key '{role}'. "
                f"Got keys: {list(cr.keys())}"
            )

    all_tel_cols = (
        [schema_summary["asset_id_column"], schema_summary["date_column"],
         schema_summary["rul_column"], schema_summary["operating_hours_column"]]
        + schema_summary["sensor_columns"]
    )
    all_tel_lower = {c.lower(): c for c in all_tel_cols}

    tel_roles = ["asset_id", "date", "rul_target", "operating_hours"]
    for role in tel_roles:
        val = cr[role]
        if val and val.lower() not in all_tel_lower:
            raise RuntimeError(
                f"Schema inferrer: Claude returned unknown column '{val}' "
                f"for role '{role}'. Valid columns: {all_tel_cols}"
            )

    all_log_columns = (
        [schema_summary["log_asset_id_column"]] +
        [schema_summary["log_date_column"]] +
        [schema_summary["log_event_type_column"]] +
        schema_summary.get("log_extra_columns", [])
    )
    all_log_columns = [c for c in all_log_columns if c]
    all_log_lower = {c.lower(): c for c in all_log_columns}

    log_roles = ["log_asset_id", "log_date", "log_event_type", "log_component"]
    for role in log_roles:
        val = cr[role]
        if val is None:
            continue
        if val.lower() not in all_log_lower:
            raise RuntimeError(
                f"Schema inferrer: Claude returned unknown log column '{val}' "
                f"for role '{role}'. Valid log columns: {all_log_columns}"
            )

    criteria = config.get("criteria", [])
    if len(criteria) < 3 or len(criteria) > 7:
        raise RuntimeError(
            f"Schema inferrer: expected 3-7 criteria, got {len(criteria)}."
        )

    expected_ids = [f"C{i+1}" for i in range(len(criteria))]
    actual_ids = [c.get("id") for c in criteria]
    if actual_ids != expected_ids:
        raise RuntimeError(
            f"Schema inferrer: criteria IDs must be {expected_ids}, got {actual_ids}."
        )

    manual_count = sum(1 for c in criteria if c.get("manual_input"))
    if not (1 <= manual_count <= 2):
        raise RuntimeError(
            f"Schema inferrer: expected 1-2 manual_input criteria, got {manual_count}."
        )

    sensor_lower = {c.lower(): c for c in schema_summary["sensor_columns"]}
    for crit in criteria:
        if crit.get("manual_input"):
            continue

        primary = crit.get("primary_column")
        if primary and primary.lower() not in sensor_lower:
            raise RuntimeError(
                f"Schema inferrer: Claude returned unknown column '{primary}' "
                f"as primary_column for {crit['id']}. "
                f"Valid sensor columns: {schema_summary['sensor_columns']}"
            )

        for sc in crit.get("secondary_columns", []):
            if sc.lower() not in sensor_lower:
                raise RuntimeError(
                    f"Schema inferrer: Claude returned unknown column '{sc}' "
                    f"in secondary_columns for {crit['id']}. "
                    f"Valid sensor columns: {schema_summary['sensor_columns']}"
                )

        for pen in crit.get("penalties", []):
            pc = pen.get("column")
            if pc and pc.lower() not in sensor_lower:
                raise RuntimeError(
                    f"Schema inferrer: Claude returned unknown column '{pc}' "
                    f"in penalty for {crit['id']}. "
                    f"Valid sensor columns: {schema_summary['sensor_columns']}"
                )

    fev = config.get("failure_event_values", [])
    if not fev:
        log_event_values = schema_summary.get("log_event_type_values", [])
        if not log_event_values:
            print(f"[DEBUG] log_event_type_values: {log_event_values!r}")
            print(f"[DEBUG] failure_event_values: {config.get('failure_event_values')!r}")
            raise RuntimeError(
                "Schema inferrer: failure_event_values must be a non-empty list."
            )
        _FAILURE_KEYWORDS = ("fail", "fault", "error", "breakdown")
        matched = [
            v for v in log_event_values
            if any(kw in v.lower() for kw in _FAILURE_KEYWORDS)
        ]
        config["failure_event_values"] = matched if matched else [log_event_values[0]]


def infer_criteria_config(schema_summary: dict, retrieved_context: dict = None) -> dict:
    prompt = _build_prompt(schema_summary, retrieved_context)

    try:
        client = anthropic.Anthropic()
        message = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = message.content[0].text.strip()
    except Exception as exc:
        raise RuntimeError(f"Anthropic API call failed: {exc}") from exc

    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
    raw_text = raw_text.strip()

    try:
        config = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Schema inferrer: Claude returned invalid JSON. "
            f"Parse error: {exc}. Raw response (first 500 chars): {raw_text[:500]}"
        ) from exc

    _validate_config(config, schema_summary)

    return config
