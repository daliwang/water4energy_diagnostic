"""Dataset 1 (Tier-1 lean raw) inventory, domain maps, TVA mask comparison."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

from . import geo, metrics
from .paths import TVA_EAST, TVA_NORTH, TVA_SOUTH, TVA_WEST


def era5_tree(data_root: Path) -> Path:
    return (
        Path(data_root)
        / "01_global_predictors"
        / "reanalysis"
        / "era5"
        / "daily_1deg_from_hourly"
    )


def inventory_dataset1(data_root: Path) -> dict:
    root = Path(data_root)
    era5 = era5_tree(root)
    files = list(era5.rglob("*.nc")) if era5.is_dir() else []
    by_var = Counter()
    months = set()
    for p in files:
        name = p.name
        if "_2m_temperature_" in name:
            by_var["t2m"] += 1
        elif "total_precipitation" in name:
            by_var["tp"] += 1
        elif "sea_level_pressure" in name:
            by_var["msl"] += 1
        parts = p.parts
        if len(parts) >= 2 and parts[-3].isdigit() and parts[-2].isdigit():
            months.add((int(parts[-3]), int(parts[-2])))

    indices = root / "01_global_predictors" / "indices" / "cpc_psl"
    oisst = root / "01_global_predictors" / "sst" / "oisst"
    ersst = root / "01_global_predictors" / "sst" / "ersst"
    cfsv2 = root / "03_seasonal_products" / "cfsv2"
    masks = root / "00_masks"

    expected_months = 540
    expected_files = expected_months * 3
    return {
        "data_root": str(root),
        "era5_present_files": len(files),
        "era5_expected_files": expected_files,
        "era5_present_months": len(months),
        "era5_expected_months": expected_months,
        "era5_by_var": dict(by_var),
        "era5_complete_months": sorted(f"{y:04d}-{m:02d}" for y, m in months),
        "era5_fraction": round(len(files) / expected_files, 4) if expected_files else 0.0,
        "indices_files": len(list(indices.rglob("*"))) if indices.is_dir() else 0,
        "oisst_nc": len(list(oisst.rglob("*.nc"))) if oisst.is_dir() else 0,
        "ersst_nc": len(list(ersst.rglob("*.nc"))) if ersst.is_dir() else 0,
        "cfsv2_nc": len(list(cfsv2.rglob("*.nc"))) if cfsv2.is_dir() else 0,
        "tva_shp": (masks / "tva_boundary.shp").is_file(),
        "note": (
            "This laptop checkout is a slice of Dataset 1. The Pathfinder / "
            "Constellation lean pack is ~5.6 GB (1620 ERA5 files)."
        ),
    }


def find_local_tp_files(data_root: Path) -> dict[str, Path]:
    era5 = era5_tree(data_root)
    found: dict[str, Path] = {}
    if not era5.is_dir():
        return found
    for p in sorted(era5.rglob("*total_precipitation*.nc")):
        parts = p.parts
        if parts[-3].isdigit() and parts[-2].isdigit():
            found[f"{parts[-3]}-{parts[-2]}"] = p
    return found


def open_era5(path: Path) -> xr.Dataset:
    ds = xr.open_dataset(path)
    lat_name = "latitude" if "latitude" in ds.coords else "lat"
    lon_name = "longitude" if "longitude" in ds.coords else "lon"
    if ds[lat_name].values[0] > ds[lat_name].values[-1]:
        ds = ds.reindex({lat_name: ds[lat_name][::-1]})
    return ds.rename({lat_name: "lat", lon_name: "lon"})


def monthly_mean_mm_day(ds: xr.Dataset, var: str) -> xr.DataArray:
    da = ds[var]
    time_dim = "valid_time" if "valid_time" in da.dims else da.dims[0]
    mean = da.mean(time_dim)
    vmax = float(np.nanmax(da.values))
    if var == "tp" and vmax < 1.5:
        mean = mean * 1000.0
        mean.attrs["units"] = "mm/day"
    return mean


def compare_tva_masks(era5_tp_path: Path, shapefile: Path | None) -> dict:
    ds = open_era5(era5_tp_path)
    field = monthly_mean_mm_day(ds, "tp").values
    lat = ds["lat"].values
    lon = ds["lon"].values
    bbox = geo.bbox_mask(lat, lon)
    service = geo.load_service_area()
    poly = geo.polygon_mask(lat, lon, service)
    out = {
        "file": str(era5_tp_path),
        "grid": {
            "nlat": int(lat.size),
            "nlon": int(lon.size),
            "lat": [float(lat.min()), float(lat.max())],
            "lon": [float(lon.min()), float(lon.max())],
        },
        "bbox": {
            "cells": int(bbox.sum()),
            "west": TVA_WEST,
            "east": TVA_EAST,
            "south": TVA_SOUTH,
            "north": TVA_NORTH,
            "tp_mm_day": geo.cell_mean(field, bbox, lat),
        },
        "service_area_geojson": {
            "cells": int(poly.sum()),
            "tp_mm_day": geo.cell_mean(field, poly, lat),
            "overlap_with_bbox": int((bbox & poly).sum()),
            "bbox_only": int((bbox & ~poly).sum()),
            "polygon_only": int((poly & ~bbox).sum()),
        },
    }
    if shapefile and Path(shapefile).is_file():
        try:
            shp_geom = geo.load_shapefile_lonlat(shapefile)
            shp_mask = geo.polygon_mask(lat, lon, shp_geom)
            out["dataset1_shapefile"] = {
                "path": str(shapefile),
                "cells": int(shp_mask.sum()),
                "tp_mm_day": geo.cell_mean(field, shp_mask, lat),
                "overlap_with_bbox": int((bbox & shp_mask).sum()),
                "overlap_with_service_area": int((poly & shp_mask).sum()),
            }
        except Exception as exc:  # noqa: BLE001
            out["dataset1_shapefile"] = {"error": str(exc)}
    ds.close()
    return out


def plot_era5_domain(files: dict[str, Path], shapefile: Path | None, out_png: Path) -> None:
    months = sorted(files)
    fig, axes = plt.subplots(2, 2, figsize=(12.4, 8.0))
    service = geo.load_service_area()
    sx, sy = geo.exterior_xy(service)
    shp_xy = None
    if shapefile and Path(shapefile).is_file():
        try:
            shp_xy = geo.exterior_xy(geo.load_shapefile_lonlat(shapefile))
        except Exception:
            shp_xy = None

    for ax, key in zip(axes.ravel(), months + [None] * 4):
        if key is None:
            ax.axis("off")
            continue
        ds = open_era5(files[key])
        field = monthly_mean_mm_day(ds, "tp")
        lat, lon = ds["lat"].values, ds["lon"].values
        pcm = ax.pcolormesh(lon, lat, field.values, cmap="viridis", shading="auto", vmin=0)
        fig.colorbar(pcm, ax=ax, fraction=0.046, pad=0.02, label="mm/day")
        ax.add_patch(
            plt.Rectangle(
                (TVA_WEST, TVA_SOUTH),
                TVA_EAST - TVA_WEST,
                TVA_NORTH - TVA_SOUTH,
                fill=False,
                edgecolor="#E63946",
                lw=1.6,
                label="band-M bbox",
            )
        )
        ax.plot(sx, sy, color="#00E5FF", lw=1.3, label="TVA service area")
        if shp_xy is not None:
            ax.plot(shp_xy[0], shp_xy[1], color="#F4A261", lw=1.0, ls="--", label="Dataset 1 shapefile")
        ax.set_xlim(-180, 0)
        ax.set_ylim(0, 70)
        ax.set_title(f"{key} monthly mean tp")
        ax.set_xlabel("lon")
        ax.set_ylabel("lat")
        ds.close()
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False)
    fig.suptitle(
        "Dataset 1 ERA5 daily 1° NA/Pac/Atl — local files only\n"
        "Red = band-M TVA bbox (40 cells) · Cyan = diagnostic service-area polygon",
        fontsize=12,
    )
    fig.tight_layout(rect=(0, 0.06, 1, 0.93))
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=160, facecolor="white")
    plt.close(fig)


def plot_mask_zoom(era5_tp_path: Path, shapefile: Path | None, out_png: Path) -> None:
    ds = open_era5(era5_tp_path)
    field = monthly_mean_mm_day(ds, "tp")
    lat, lon = ds["lat"].values, ds["lon"].values
    bbox = geo.bbox_mask(lat, lon)
    poly = geo.polygon_mask(lat, lon, geo.load_service_area())
    lon2d, lat2d = np.meshgrid(lon, lat)

    fig, ax = plt.subplots(figsize=(8.2, 6.4))
    ax.pcolormesh(lon, lat, field.values, cmap="Greys", shading="auto", vmin=0, alpha=0.85)
    ax.scatter(
        lon2d[bbox],
        lat2d[bbox],
        s=28,
        c="#E63946",
        marker="s",
        label=f"bbox n={int(bbox.sum())}",
        zorder=4,
    )
    ax.scatter(
        lon2d[poly],
        lat2d[poly],
        s=18,
        facecolors="none",
        edgecolors="#00E5FF",
        linewidths=1.2,
        marker="o",
        label=f"service area n={int(poly.sum())}",
        zorder=5,
    )
    ax.set_xlim(-95, -78)
    ax.set_ylim(31, 40)
    ax.set_aspect("equal")
    ax.set_xlabel("lon")
    ax.set_ylabel("lat")
    ax.set_title("ERA5 1° cell centres: band-M bbox vs TVA service-area polygon")
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=160, facecolor="white")
    plt.close(fig)
    ds.close()


def compare_qc_csv_to_panel(csv_path: Path, panel_nc: Path) -> dict:
    if not csv_path.is_file() or not Path(panel_nc).is_file():
        return {"skipped": True, "csv": str(csv_path), "panel": str(panel_nc)}
    csv = pd.read_csv(csv_path)
    panel = xr.open_dataset(panel_nc, decode_times=False)
    t2m_c = panel["t2m"].values - 273.15
    tp = panel["tp"].values
    msl_hpa = panel["msl"].values / 100.0

    def mid_to_stamp(mid: int) -> str:
        year = 1800 + int(mid) // 12
        month = int(mid) % 12 + 1
        return f"{year:04d}-{month:02d}"

    stamps = [mid_to_stamp(int(t)) for t in panel["time"].values]
    csv = csv.set_index("month")
    aligned = [s for s in stamps if s in csv.index]
    order = [stamps.index(s) for s in aligned]
    result = {
        "n": len(aligned),
        "t2m_C": metrics.pair_stats(csv.loc[aligned, "t2m_C"].to_numpy(), t2m_c[order]),
        "tp_mm_day": metrics.pair_stats(csv.loc[aligned, "tp_mm_day"].to_numpy(), tp[order]),
        "msl_hPa": metrics.pair_stats(csv.loc[aligned, "msl_hPa"].to_numpy(), msl_hpa[order]),
        "note": "Dataset 1 QC CSV (TVA bbox means) vs Dataset 2 era5_tva_monthly.nc",
    }
    panel.close()
    return result
