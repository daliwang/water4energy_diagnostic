"""Resolve Dataset 1 / Dataset 2 locations without hard-coding a site."""
from __future__ import annotations

import os
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
DIAGNOSTIC_ROOT = PACKAGE.parent
WORKSPACE = DIAGNOSTIC_ROOT.parent

DEFAULT_DATA = WORKSPACE / "data"
DEFAULT_TRAINING = WORKSPACE / "trainingData"
DEFAULT_CACHE = PACKAGE / "_inputs"
DEFAULT_OUTPUT = PACKAGE / "outputs"
TVA_GEOJSON = DIAGNOSTIC_ROOT / "tva_power_service_area.geojson"

ERA5_TP = "era5_daily_sum_total_precipitation_{ym}_1deg_na_pac_atl.nc"
ERA5_T2M = "era5_daily_mean_2m_temperature_{ym}_1deg_na_pac_atl.nc"
ERA5_MSL = "era5_daily_mean_mean_sea_level_pressure_{ym}_1deg_na_pac_atl.nc"

# Band-M TVA bbox used by trainingData builders (40 ERA5 1° cells).
TVA_WEST, TVA_EAST = -90.5, -81.0
TVA_SOUTH, TVA_NORTH = 34.0, 37.8

INDEX_VARS = ("oni", "nino34", "nao", "ao", "pna", "pdo", "amo", "soi")
SST_VARS = ("nino34_box", "natl_box", "epac_box")
Y_VARS = ("t2m", "tp", "msl")
LEADS = (1, 2, 3)
LOOKBACK = 12
LOOKBACK = LOOKBACK


def _existing(*candidates: Path | None) -> Path | None:
    for path in candidates:
        if path is not None and path.exists():
            return path.resolve()
    return None


def data_root(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("W4E_ROOT")
    found = _existing(Path(env) if env else None, DEFAULT_DATA)
    return found or DEFAULT_DATA


def training_root(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("W4E_TRAINING_DATA")
    found = _existing(Path(env) if env else None, DEFAULT_TRAINING)
    return found or DEFAULT_TRAINING


def pack_dir(explicit: str | Path | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("W4E_DATASET2")
    found = _existing(
        Path(env) if env else None,
        DEFAULT_CACHE,
        DEFAULT_TRAINING / "processed" / "monthly",
    )
    return found or DEFAULT_CACHE
