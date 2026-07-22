import re
from datetime import datetime, timezone
from pathlib import Path

import joblib

_MODELS_DIR = Path("rul/models")


def sanitize_asset_type(asset_type: str) -> str:
    return asset_type.lower().replace(" ", "_").replace("/", "_")


def model_path_for_asset_type(asset_type: str) -> str:
    return str(_MODELS_DIR / f"{sanitize_asset_type(asset_type)}.pkl")


def list_models() -> list[dict]:
    if not _MODELS_DIR.exists():
        return []

    models = []
    for path in sorted(_MODELS_DIR.glob("*.pkl")):
        try:
            bundle = joblib.load(path)
        except Exception:
            continue

        asset_type = bundle.get("criteria_config", {}).get("asset_type", path.stem)
        trained_at = datetime.fromtimestamp(
            path.stat().st_mtime, tz=timezone.utc
        ).isoformat()

        models.append({
            "asset_type": asset_type,
            "filename": path.name,
            "model_path": str(path),
            "trained_at": trained_at,
            "feature_count": len(bundle.get("feature_names", [])),
        })

    return models


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def find_model(asset_type: str) -> str | None:
    """Finds the best matching pre-trained model for a given asset type.

    1. Exact match on asset_type (case-insensitive)
    2. Partial match -- most word overlap between the two asset_type strings
    3. None if nothing overlaps
    """
    models = list_models()
    if not models:
        return None

    target_lower = asset_type.strip().lower()
    for m in models:
        if m["asset_type"].strip().lower() == target_lower:
            return m["model_path"]

    target_words = _tokenize(asset_type)
    best_path, best_overlap = None, 0
    for m in models:
        overlap = len(target_words & _tokenize(m["asset_type"]))
        if overlap > best_overlap:
            best_path, best_overlap = m["model_path"], overlap

    return best_path


def get_model_bundle(model_path: str) -> dict:
    path = Path(model_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Model not found at '{model_path}'. Train a model first using: "
            "python -m rul.dynamic_train_cli --file <historical_data.xlsx>"
        )
    return joblib.load(path)
