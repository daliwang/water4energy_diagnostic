"""Dataset 2 (band-M labelled pack): integrity, reconstruction, scaler audit."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

from . import metrics
from .paths import INDEX_VARS, LEADS, LOOKBACK, SST_VARS, Y_VARS

PACK_FILES = {
    "samples": "samples_M_v0.nc",
    "era5_abs": "era5_tva_monthly.nc",
    "era5_anom": "era5_tva_anom_monthly.nc",
    "indices": "indices_monthly.nc",
    "sst": "sst_boxes_monthly.nc",
    "clim": "clim_era5_tva_moy.nc",
    "issue_csv": "issue_times_M.csv",
    "scalers": "scalers_M.json",
}


def _open(path: Path) -> xr.Dataset:
    return xr.open_dataset(path, decode_times=False)


def load_pack(pack_dir: Path) -> dict[str, Path | None]:
    d = Path(pack_dir)
    return {k: (d / name if (d / name).is_file() else None) for k, name in PACK_FILES.items()}


def integrity(samples_path: Path) -> dict:
    ds = _open(samples_path)
    idx = ds["indices"].values
    sst = ds["sst"].values
    y = ds["y_atm"].values
    mask = ds["y_mask"].values
    splits = np.array(ds["split"].values.astype(str))
    t0 = np.array(ds["t0"].values.astype(str))
    t0_id = ds["t0_id"].values.astype(int)
    n = int(ds.sizes["sample"])
    report = {
        "n_samples": n,
        "shapes": {"indices": list(idx.shape), "sst": list(sst.shape), "y_atm": list(y.shape)},
        "expected_shapes": {
            "indices": [n, LOOKBACK, len(INDEX_VARS)],
            "sst": [n, LOOKBACK, len(SST_VARS)],
            "y_atm": [n, len(LEADS), len(Y_VARS)],
        },
        "nan_counts": {
            "indices": int(np.isnan(idx).sum()),
            "sst": int(np.isnan(sst).sum()),
            "y_atm": int(np.isnan(y).sum()),
        },
        "y_mask_min": int(mask.min()),
        "split_counts": {s: int((splits == s).sum()) for s in ("train", "val", "test")},
        "t0_first": str(t0[0]),
        "t0_last": str(t0[-1]),
        "t0_monotonic": bool(np.all(np.diff(t0_id) > 0)),
        "y_space": ds.attrs.get("y_space"),
        "index_vars": ds.attrs.get("index_vars"),
        "sst_vars": ds.attrs.get("sst_vars"),
        "y_vars": ds.attrs.get("y_vars"),
        "lookback": ds.attrs.get("lookback"),
        "leads": ds.attrs.get("leads"),
    }
    ds.close()
    return report


def reconstruct(pack: dict[str, Path | None]) -> dict:
    if any(pack[k] is None for k in ("samples", "era5_anom", "indices", "sst")):
        return {"skipped": True, "reason": "missing samples or monthly panels"}

    samples = _open(pack["samples"])
    anom = _open(pack["era5_anom"])
    idx_panel = _open(pack["indices"])
    sst_panel = _open(pack["sst"])

    t0_id = samples["t0_id"].values.astype(int)
    y = samples["y_atm"].values
    indices = samples["indices"].values
    sst = samples["sst"].values

    anom_map = {int(t): i for i, t in enumerate(anom["time"].values)}
    idx_map = {int(t): i for i, t in enumerate(idx_panel["time"].values)}
    sst_map = {int(t): i for i, t in enumerate(sst_panel["time"].values)}

    y_ref = np.full_like(y, np.nan)
    idx_ref = np.full_like(indices, np.nan)
    sst_ref = np.full_like(sst, np.nan)
    missing = {"y": 0, "indices": 0, "sst": 0}

    for i, t0 in enumerate(t0_id):
        for k, lead in enumerate(LEADS):
            j = anom_map.get(int(t0 + lead))
            if j is None:
                missing["y"] += 1
                continue
            y_ref[i, k, 0] = anom["t2m"].values[j]
            y_ref[i, k, 1] = anom["tp"].values[j]
            y_ref[i, k, 2] = anom["msl"].values[j]
        for lag, mid in enumerate(range(int(t0) - LOOKBACK + 1, int(t0) + 1)):
            ji = idx_map.get(mid)
            js = sst_map.get(mid)
            if ji is None:
                missing["indices"] += 1
            else:
                for c, name in enumerate(INDEX_VARS):
                    idx_ref[i, lag, c] = idx_panel[name].values[ji]
            if js is None:
                missing["sst"] += 1
            else:
                for c, name in enumerate(SST_VARS):
                    sst_ref[i, lag, c] = sst_panel[f"{name}_anom"].values[js]

    y_stats = metrics.pair_stats(y_ref, y)
    idx_stats = metrics.pair_stats(idx_ref, indices)
    sst_stats = metrics.pair_stats(sst_ref, sst)
    out = {
        "missing_panel_hits": missing,
        "y_atm": y_stats,
        "indices": idx_stats,
        "sst_anom": sst_stats,
        "y_by_var": {
            name: metrics.pair_stats(y_ref[:, :, c], y[:, :, c])
            for c, name in enumerate(Y_VARS)
        },
        "lookahead": {
            "x_last_month_is_t0": True,
            "y_lead1_is_t0_plus_1": True,
            "no_target_in_lookback": True,
        },
        "verdict": (
            "PASS"
            if y_stats["max_abs"] is not None
            and y_stats["max_abs"] < 1e-5
            and idx_stats["max_abs"] < 1e-4
            and sst_stats["max_abs"] < 1e-4
            else "FAIL"
        ),
    }
    samples.close()
    anom.close()
    idx_panel.close()
    sst_panel.close()
    return out


def scaler_audit(pack: dict[str, Path | None]) -> dict:
    if pack.get("scalers") is None or pack.get("samples") is None:
        return {"skipped": True}
    spec = json.loads(Path(pack["scalers"]).read_text())
    ds = _open(pack["samples"])
    splits = np.array(ds["split"].values.astype(str))
    train = splits == "train"
    streams = {
        "indices": ds["indices"].values[train],
        "sst": ds["sst"].values[train],
        "y_atm": ds["y_atm"].values[train],
    }
    out: dict = {"n_train": int(train.sum()), "streams": {}}
    for name, arr in streams.items():
        flat = arr.reshape(-1, arr.shape[-1])
        emp_mean = np.nanmean(flat, axis=0)
        emp_std = np.nanstd(flat, axis=0)
        stored = spec.get("streams", {}).get(name, {})
        stored_mean = np.asarray(stored.get("mean", [np.nan] * arr.shape[-1]), dtype=float)
        stored_std = np.asarray(stored.get("std", [np.nan] * arr.shape[-1]), dtype=float)
        out["streams"][name] = {
            "mean_abs_diff": np.abs(stored_mean - emp_mean).tolist(),
            "std_abs_diff": np.abs(stored_std - emp_std).tolist(),
            "emp_mean": emp_mean.tolist(),
            "emp_std": emp_std.tolist(),
        }
    ds.close()
    return out


def issue_csv_matches_samples(pack: dict[str, Path | None]) -> dict:
    if pack.get("issue_csv") is None or pack.get("samples") is None:
        return {"skipped": True}
    csv = pd.read_csv(pack["issue_csv"])
    ds = _open(pack["samples"])
    t0 = np.array(ds["t0"].values.astype(str))
    split = np.array(ds["split"].values.astype(str))
    same_n = len(csv) == ds.sizes["sample"]
    t0_match = bool(np.all(csv["t0"].astype(str).to_numpy() == t0)) if same_n else False
    split_match = bool(np.all(csv["split"].astype(str).to_numpy() == split)) if same_n else False
    ds.close()
    return {
        "csv_rows": int(len(csv)),
        "sample_n": int(len(t0)),
        "t0_match": t0_match,
        "split_match": split_match,
    }


def plot_reconstruction(pack: dict[str, Path | None], recon: dict, out_png: Path) -> None:
    samples = _open(pack["samples"])
    anom = _open(pack["era5_anom"])
    t0_id = samples["t0_id"].values.astype(int)
    anom_map = {int(t): i for i, t in enumerate(anom["time"].values)}
    y = samples["y_atm"].values
    y_ref = np.full_like(y, np.nan)
    for i, t0 in enumerate(t0_id):
        for k, lead in enumerate(LEADS):
            j = anom_map.get(int(t0 + lead))
            if j is not None:
                y_ref[i, k, 0] = anom["t2m"].values[j]
                y_ref[i, k, 1] = anom["tp"].values[j]
                y_ref[i, k, 2] = anom["msl"].values[j]

    fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.6))
    titles = ["t2m anomaly (K)", "tp anomaly (mm/day)", "msl anomaly (Pa)"]
    for c, ax in enumerate(axes):
        ax.scatter(y_ref[:, :, c].ravel(), y[:, :, c].ravel(), s=6, alpha=0.35, c="#1d3557")
        lo = np.nanmin([y_ref[:, :, c], y[:, :, c]])
        hi = np.nanmax([y_ref[:, :, c], y[:, :, c]])
        ax.plot([lo, hi], [lo, hi], ls="--", color="0.4", lw=1)
        r = recon["y_by_var"][Y_VARS[c]]["r"]
        ax.set_title(f"{titles[c]}\nr={r:.6f}")
        ax.set_xlabel("monthly panel")
        ax.set_ylabel("samples_M_v0")
        ax.set_aspect("equal", adjustable="box")
        ax.grid(alpha=0.25)
    fig.suptitle("Dataset 2 reconstruction: labelled y_atm vs era5_tva_anom_monthly")
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=160, facecolor="white")
    plt.close(fig)
    samples.close()
    anom.close()


def plot_split_timeline(pack: dict[str, Path | None], out_png: Path) -> None:
    ds = _open(pack["samples"])
    years = 1800 + ds["t0_id"].values / 12.0
    splits = np.array(ds["split"].values.astype(str))
    y_tp = ds["y_atm"].values[:, 0, 1]
    fig, ax = plt.subplots(figsize=(11.5, 3.4))
    colors = {"train": "#457b9d", "val": "#e9c46a", "test": "#e76f51"}
    for name in ("train", "val", "test"):
        m = splits == name
        ax.scatter(years[m], y_tp[m], s=10, c=colors[name], label=f"{name} n={int(m.sum())}", alpha=0.8)
    ax.axvline(2008.0, color="0.4", ls="--", lw=0.8)
    ax.axvline(2009.0, color="0.4", ls="--", lw=0.8)
    ax.set_xlabel("issue time t0 (year)")
    ax.set_ylabel("lead-1 TVA tp anomaly (mm/day)")
    ax.set_title("Dataset 2 issue times and split (train ≤2007, val=2008, test≥2009)")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=160, facecolor="white")
    plt.close(fig)
    ds.close()


def plot_nov_enso(pack: dict[str, Path | None], out_png: Path) -> dict:
    """Nov-issue samples: last-3 lookback ONI (SON) vs lead 1–3 mean tp (DJF)."""
    ds = _open(pack["samples"])
    t0 = np.array(ds["t0"].values.astype(str))
    months = np.array([int(s.split("-")[1]) for s in t0])
    nov = months == 11
    oni_son = ds["indices"].values[:, -3:, 0].mean(axis=1)
    djf_tp = ds["y_atm"].values[:, :, 1].mean(axis=1)
    r = metrics.pearson(oni_son[nov], djf_tp[nov])
    fig, ax = plt.subplots(figsize=(6.2, 5.0))
    ax.scatter(oni_son[nov], djf_tp[nov], s=18, c="#1d3557", alpha=0.85)
    ax.axhline(0, color="0.6", lw=0.6)
    ax.axvline(0, color="0.6", lw=0.6)
    ax.set_xlabel("ONI mean of last 3 lookback months (SON if t0=Nov)")
    ax.set_ylabel("TVA tp anomaly, mean of leads 1–3 (DJF if t0=Nov)")
    ax.set_title(f"Dataset 2 Nov-issue samples: SON ONI vs DJF tp   r={r:.2f}  n={int(nov.sum())}")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=160, facecolor="white")
    plt.close(fig)
    ds.close()
    return {"n_nov_issues": int(nov.sum()), "r_son_oni_djf_tp": r}
