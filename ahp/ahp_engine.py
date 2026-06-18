import numpy as np

from ahp.ahp_constants import CR_THRESHOLD, RI


def fill_reciprocals(matrix: list[list[float]]) -> np.ndarray:
    """Copy upper triangle into lower triangle as reciprocals."""
    m = np.array(matrix, dtype=float)
    n = m.shape[0]
    for i in range(n):
        for j in range(i + 1, n):
            m[j, i] = 1.0 / m[i, j]
    return m


def normalize_and_derive_weights(matrix: np.ndarray) -> np.ndarray:
    """Column-normalize then average each row to get the priority weight vector."""
    normalized = matrix / matrix.sum(axis=0)
    return normalized.mean(axis=1)


def compute_consistency(matrix: np.ndarray, weights: np.ndarray) -> tuple[float, float, float]:
    """Return (λ_max, CI, CR) for the completed pairwise matrix."""
    n = len(weights)
    weighted_sum_vector = matrix @ weights
    lambda_max = float(np.mean(weighted_sum_vector / weights))
    ci = (lambda_max - n) / (n - 1)
    cr = ci / RI[n]
    return lambda_max, ci, cr


def run_ahp(matrix: list[list[float]]) -> dict:
    """Full AHP pipeline for a 5×5 pairwise comparison matrix.

    Args:
        matrix: 5×5 list-of-lists with the upper triangle (and diagonal = 1)
                filled by the caller. Lower triangle is auto-completed here.

    Returns:
        weights    – list of 5 floats summing to 1.0
        lambda_max – principal eigenvalue approximation
        ci         – Consistency Index
        cr         – Consistency Ratio
        valid      – True when CR ≤ 0.10
    """
    m = fill_reciprocals(matrix)
    weights = normalize_and_derive_weights(m)
    lambda_max, ci, cr = compute_consistency(m, weights)

    return {
        "weights": [round(w, 6) for w in weights.tolist()],
        "lambda_max": round(lambda_max, 6),
        "ci": round(ci, 6),
        "cr": round(cr, 4),
        "valid": bool(cr <= CR_THRESHOLD),
    }
