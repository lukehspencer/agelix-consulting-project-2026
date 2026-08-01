import re
from datetime import datetime, timezone
from pathlib import Path

import joblib

_MODELS_DIR = Path("rul/models")


def sanitize_asset_type(asset_type: str) -> str:
    return asset_type.lower().replace(" ", "_").replace("/", "_")


def model_path_for_asset_type(asset_type: str) -> str:
    return str(_MODELS_DIR / f"{sanitize_asset_type(asset_type)}.pkl")


def _load_model_entries(paths) -> list[dict]:
    models = []
    for path in paths:
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


def list_models() -> list[dict]:
    if not _MODELS_DIR.exists():
        return []

    # RUL 2 (decommissioning) bundles live alongside RUL 1 bundles in the
    # same directory but are trained with a different (age-inclusive)
    # feature vector -- excluded here so find_model() never hands a RUL 2
    # bundle to a RUL 1 prediction call, which would fail feature-length
    # validation or silently score against a mismatched model.
    paths = [p for p in sorted(_MODELS_DIR.glob("*.pkl")) if not p.name.endswith("_rul2.pkl")]
    return _load_model_entries(paths)


def list_rul2_models() -> list[dict]:
    if not _MODELS_DIR.exists():
        return []

    paths = sorted(_MODELS_DIR.glob("*_rul2.pkl"))
    return _load_model_entries(paths)


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _match_asset_type(models: list[dict], asset_type: str) -> str | None:
    """Finds the best matching model for a given asset type among `models`.

    1. Exact match on asset_type (case-insensitive)
    2. Partial match -- most word overlap between the two asset_type strings
    3. None if nothing overlaps
    """
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

    if best_overlap > 0:
        return best_path

    if len(models) == 1:
        return models[0]["model_path"]

    return None


def find_model(asset_type: str) -> str | None:
    return _match_asset_type(list_models(), asset_type)


def find_rul2_model(asset_type: str) -> str | None:
    """Same matching strategy as find_model(), scoped to *_rul2.pkl bundles."""
    return _match_asset_type(list_rul2_models(), asset_type)


def get_model_bundle(model_path: str) -> dict:
    path = Path(model_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Model not found at '{model_path}'. Train a model first using: "
            "python -m rul.dynamic_train_cli --file <historical_data.xlsx>"
        )
    return joblib.load(path)
