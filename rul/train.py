import random
from pathlib import Path

import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import root_mean_squared_error
from xgboost import XGBRegressor
import joblib

from rul.feature_engineering import build_feature_vector, get_feature_names

_MODEL_PATH = Path(__file__).parent / "model.pkl"
_N_SAMPLES = 500
_EXPECTED_LIFESPAN = 20
_SEED = 42


def _generate_synthetic_dataset(n: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)

    X_rows = []
    y_labels = []

    for _ in range(n):
        age_years = rng.uniform(0, 25)
        usage_intensity_pct = rng.uniform(40, 110)
        total_runtime_hours = rng.uniform(0, 100_000)
        operating_hours_per_day = rng.uniform(8, 24)
        condition_score = rng.uniform(1, 10)
        number_of_failures_last_3yr = rng.integers(0, 6)
        days_since_maintenance = rng.uniform(0, 365)
        maintenance_cost_last_year = rng.uniform(500, 15_000)

        pump = {
            "age_years": age_years,
            "usage_intensity_pct": usage_intensity_pct,
            "total_runtime_hours": total_runtime_hours,
            "operating_hours_per_day": operating_hours_per_day,
            "condition_score": condition_score,
            "number_of_failures_last_3yr": int(number_of_failures_last_3yr),
            "days_since_maintenance": days_since_maintenance,
            "maintenance_cost_last_year": maintenance_cost_last_year,
        }

        raw_weights = rng.uniform(0.01, 1.0, size=5)
        weights = (raw_weights / raw_weights.sum()).tolist()

        scores = rng.uniform(1, 9, size=5).tolist()

        vector = build_feature_vector(pump, weights, scores)
        X_rows.append(vector)

        risk_factor = vector[-1]
        degradation = (
            (10 - condition_score) * 0.4
            + usage_intensity_pct / 100 * 0.3
            + number_of_failures_last_3yr * 0.5
            + risk_factor * 0.3
        )
        noise = rng.normal(0, 0.5)
        rul = max(0.0, _EXPECTED_LIFESPAN - age_years - degradation + noise)
        y_labels.append(rul)

    return np.array(X_rows), np.array(y_labels)


def train_and_save() -> None:
    print(f"Generating {_N_SAMPLES} synthetic pump records...")
    X, y = _generate_synthetic_dataset(_N_SAMPLES, _SEED)
    print(f"  Feature matrix shape: {X.shape}")
    print(f"  RUL label range: {y.min():.2f} - {y.max():.2f} years")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=_SEED,
    )

    model = XGBRegressor(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="reg:squarederror",
        random_state=_SEED,
    )

    print("Training XGBoost Regressor...")
    model.fit(X_train, y_train)

    train_rmse = root_mean_squared_error(y_train, model.predict(X_train))
    test_rmse = root_mean_squared_error(y_test, model.predict(X_test))

    print(f"\n  Train RMSE: {train_rmse:.4f} years")
    print(f"  Test  RMSE: {test_rmse:.4f} years")

    feature_names = get_feature_names()
    importances = model.feature_importances_
    ranked = sorted(zip(feature_names, importances), key=lambda x: x[1], reverse=True)

    print("\n  Feature Importances:")
    for name, imp in ranked:
        print(f"    {name:<40s} {imp:.4f}")

    joblib.dump(model, _MODEL_PATH)
    print(f"\nModel saved to {_MODEL_PATH}")


if __name__ == "__main__":
    train_and_save()
