import json
from datetime import datetime, timezone
from pathlib import Path

_AUDIT_LOG_PATH = Path("docs/audit_log.jsonl")

_DIFF_FIELDS = ("name", "thresholds", "default_score", "penalties")


def _criterion_summary(crit: dict) -> dict:
    return {
        "id": crit.get("id"),
        "name": crit.get("name"),
        "thresholds": crit.get("thresholds"),
        "default_score": crit.get("default_score"),
    }


def _build_diff(original_config: dict, approved_config: dict) -> list[dict]:
    orig_by_id = {c.get("id"): c for c in original_config.get("criteria", [])}
    diff = []

    for crit in approved_config.get("criteria", []):
        cid = crit.get("id")
        orig = orig_by_id.get(cid, {})
        for field in _DIFF_FIELDS:
            claude_value = orig.get(field)
            approved_value = crit.get(field)
            if claude_value != approved_value:
                diff.append({
                    "criterion_id": cid,
                    "field": field,
                    "claude_value": claude_value,
                    "approved_value": approved_value,
                })

    return diff


def log_approval(file_path: str, asset_type: str, original_config: dict,
                  approved_config: dict, changes_count: int,
                  config_filename: str = None) -> str:
    try:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        entry = {
            "timestamp": timestamp,
            "config_filename": config_filename,
            "file_path": file_path,
            "asset_type": asset_type,
            "changes_from_claude": changes_count,
            "original_criteria": [
                _criterion_summary(c) for c in original_config.get("criteria", [])
            ],
            "approved_criteria": [
                _criterion_summary(c) for c in approved_config.get("criteria", [])
            ],
            "diff": _build_diff(original_config, approved_config),
        }

        _AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        return timestamp
    except Exception as exc:
        print(f"Warning: failed to write audit log entry: {exc}")
        return ""


def get_audit_log() -> list[dict]:
    if not _AUDIT_LOG_PATH.exists():
        return []

    entries = []
    with _AUDIT_LOG_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return entries
