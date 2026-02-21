from __future__ import annotations

import numpy as np


def load_csv(path: str, target_col: int = -1):
    data = np.genfromtxt(path, delimiter=",", dtype=float)
    if data.ndim == 1:
        data = data.reshape(1, -1)

    n_cols = data.shape[1]
    idx = target_col if target_col >= 0 else n_cols + target_col
    if idx < 0 or idx >= n_cols:
        raise ValueError(f"target_col out of range: {target_col}")

    y = data[:, idx]
    x = np.delete(data, idx, axis=1)
    return x, y


def save_vector(path: str, values):
    np.savetxt(path, np.asarray(values), delimiter=",", fmt="%.10g")
