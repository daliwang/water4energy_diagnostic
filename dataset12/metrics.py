"""Small metric helpers shared by Dataset 1 and Dataset 2 checks."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


def pearson(x: np.ndarray, y: np.ndarray) -> float:
    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 3:
        return float("nan")
    return float(np.corrcoef(x[ok], y[ok])[0, 1])


def rmse(x: np.ndarray, y: np.ndarray) -> float:
    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    ok = np.isfinite(x) & np.isfinite(y)
    if not ok.any():
        return float("nan")
    return float(np.sqrt(np.mean((y[ok] - x[ok]) ** 2)))


def bias(x: np.ndarray, y: np.ndarray) -> float:
    """Mean of (y - x)."""
    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    ok = np.isfinite(x) & np.isfinite(y)
    if not ok.any():
        return float("nan")
    return float(np.mean(y[ok] - x[ok]))


def max_abs(x: np.ndarray, y: np.ndarray) -> float:
    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    ok = np.isfinite(x) & np.isfinite(y)
    if not ok.any():
        return float("nan")
    return float(np.max(np.abs(y[ok] - x[ok])))


def pair_stats(reference: np.ndarray, other: np.ndarray) -> dict[str, float]:
    return {
        "n": int((np.isfinite(reference).ravel() & np.isfinite(other).ravel()).sum()),
        "r": pearson(reference, other),
        "rmse": rmse(reference, other),
        "bias": bias(reference, other),
        "max_abs": max_abs(reference, other),
    }


def json_ready(obj: Any) -> Any:
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        val = float(obj)
        return None if not np.isfinite(val) else val
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {str(k): json_ready(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_ready(v) for v in obj]
    if isinstance(obj, float) and not np.isfinite(obj):
        return None
    return obj


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_ready(payload), indent=2) + "\n")
