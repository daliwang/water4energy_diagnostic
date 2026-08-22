#!/usr/bin/env python3
"""Compare E3SMv3 and ERA5 annual climatologies for TS and precipitation.

For each variable this script creates a four-panel figure containing:
  1. ERA5 annual climatology
  2. E3SMv3 annual climatology
  3. E3SMv3 minus ERA5 bias
  4. Grid-cell comparison with area-weighted spatial correlation

E3SM's native unstructured ncol field is linearly interpolated to a regular
grid. ERA5 is interpolated to the same grid before the comparison.

The default TVA polygon is the public "TVA_Power_Service_Area" feature layer
published by TVA GIS & Mapping (ArcGIS item 87cdc9128b6f4afaa7f3428fc43bb899).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import warnings

import cartopy
import cartopy.crs as ccrs
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
from matplotlib.colors import BoundaryNorm
import numpy as np
from scipy.interpolate import griddata
from shapely import contains_xy
from shapely.geometry import shape
import xarray as xr


PACKAGE_DIR = Path(__file__).resolve().parent
ERA_DEFAULT = "ERA5_ANN_198501_201412_climo.nc"
E3SM_DEFAULT = "v3.LR.historical_0101_ANN_198501_201412_climo.nc"
TVA_DEFAULT = "tva_power_service_area.geojson"
CARTOPY_BUNDLED = PACKAGE_DIR / "cartopy_data"


def resolve_input(path: str) -> Path:
    """Prefer an existing path; otherwise look next to this script."""
    candidate = Path(path).expanduser()
    if candidate.is_file():
        return candidate
    bundled = PACKAGE_DIR / path
    if bundled.is_file():
        return bundled
    return candidate


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--era5", default=ERA_DEFAULT, help="ERA5 NetCDF file")
    parser.add_argument("--e3sm", default=E3SM_DEFAULT, help="E3SM NetCDF file")
    parser.add_argument(
        "--tva-boundary",
        default=TVA_DEFAULT,
        help="TVA Power Service Area boundary in GeoJSON format",
    )
    parser.add_argument(
        "--resolution",
        type=float,
        default=1.0,
        help="Comparison-grid spacing in degrees (default: 1.0)",
    )
    parser.add_argument(
        "--output-dir", default="plots", help="Directory for PNG and PDF output"
    )
    parser.add_argument("--dpi", type=int, default=200, help="PNG resolution")
    parser.add_argument(
        "--cartopy-data",
        default="",
        help="Cartopy Natural Earth data directory "
        f"(default: {CARTOPY_BUNDLED} if present)",
    )
    return parser.parse_args()


def configure_cartopy(output_dir: Path, cartopy_data: str) -> Path:
    """Use the bundled coastline cache when present; keep a writable fallback."""
    if cartopy_data:
        bundled = Path(cartopy_data).expanduser().resolve()
    elif CARTOPY_BUNDLED.exists():
        bundled = CARTOPY_BUNDLED
    else:
        bundled = None
    writable = output_dir / ".cartopy"
    writable.mkdir(parents=True, exist_ok=True)
    if bundled is not None:
        cartopy.config["pre_existing_data_dir"] = str(bundled)
    cartopy.config["data_dir"] = str(writable)
    return Path(cartopy.config["data_dir"])


def regular_grid(resolution: float) -> tuple[np.ndarray, np.ndarray]:
    """Return cell-center latitude and longitude coordinates."""
    if not 0.1 <= resolution <= 10:
        raise ValueError("--resolution must be between 0.1 and 10 degrees")
    lat = np.arange(-90.0 + resolution / 2, 90.0, resolution)
    lon = np.arange(0.0 + resolution / 2, 360.0, resolution)
    return lat, lon


def first_time(da: xr.DataArray) -> xr.DataArray:
    """Remove singleton dimensions, including the one-point climatology time."""
    return da.squeeze(drop=True)


def era_on_grid(
    ds: xr.Dataset, variable: str, target_lat: np.ndarray, target_lon: np.ndarray
) -> np.ndarray:
    """Interpolate a regular ERA5 field to the common comparison grid."""
    da = first_time(ds[variable])
    if "lat" not in da.dims or "lon" not in da.dims:
        raise ValueError(f"ERA5 variable {variable!r} is not on a lat/lon grid")

    # xarray interpolation requires monotonic coordinates. ERA5 latitude may
    # run north-to-south, and longitude may use either [-180, 180) or [0, 360).
    da = da.assign_coords(lon=np.mod(da.lon, 360.0)).sortby("lat").sortby("lon")
    _, unique_lon_indices = np.unique(da.lon.values, return_index=True)
    da = da.isel(lon=np.sort(unique_lon_indices))
    return da.interp(lat=target_lat, lon=target_lon).values


def e3sm_on_grid(
    ds: xr.Dataset,
    field: xr.DataArray,
    target_lat: np.ndarray,
    target_lon: np.ndarray,
) -> np.ndarray:
    """Linearly interpolate an E3SM ncol field, with longitude wraparound."""
    values = np.asarray(first_time(field).values, dtype=float)
    lat = np.asarray(ds["lat"].values, dtype=float).squeeze()
    lon = np.mod(np.asarray(ds["lon"].values, dtype=float).squeeze(), 360.0)

    valid = np.isfinite(lat) & np.isfinite(lon) & np.isfinite(values)
    lat, lon, values = lat[valid], lon[valid], values[valid]

    # Duplicate points across the dateline so interpolation is cyclic in lon.
    points = np.column_stack(
        [np.concatenate((lon - 360.0, lon, lon + 360.0)), np.tile(lat, 3)]
    )
    wrapped_values = np.tile(values, 3)
    lon2d, lat2d = np.meshgrid(target_lon, target_lat)
    result = griddata(points, wrapped_values, (lon2d, lat2d), method="linear")

    # Very small gaps can occur near the poles; fill only those with nearest.
    missing = ~np.isfinite(result)
    if missing.any():
        result[missing] = griddata(
            points, wrapped_values, (lon2d[missing], lat2d[missing]), method="nearest"
        )
    return result


def temperature_celsius(da: xr.DataArray) -> xr.DataArray:
    units = str(da.attrs.get("units", "")).strip().lower()
    if units in {"k", "kelvin", "degrees_k", "degree_k"}:
        return da - 273.15
    if units in {"c", "degc", "degree_celsius", "degrees_celsius"}:
        return da
    raise ValueError(f"Unrecognized temperature units {units!r} for {da.name}")


def precipitation_mm_day(da: xr.DataArray) -> xr.DataArray:
    """Convert precipitation flux/rate to mm day-1."""
    units = str(da.attrs.get("units", "")).strip().lower().replace(" ", "")
    if units in {"kgm-2s-1", "kg/m2/s", "mm/s"}:
        factor = 86400.0
    elif units in {"m/s", "ms-1"}:
        factor = 1000.0 * 86400.0
    elif units in {"mm/day", "mmd-1", "mmday-1"}:
        factor = 1.0
    else:
        raise ValueError(f"Unrecognized precipitation units {units!r} for {da.name}")
    return da * factor


def weighted_spatial_correlation(
    reference: np.ndarray, model: np.ndarray, lat: np.ndarray
) -> float:
    """Cos(latitude)-weighted Pearson pattern correlation."""
    weights = np.cos(np.deg2rad(lat))[:, None] * np.ones_like(reference)
    valid = np.isfinite(reference) & np.isfinite(model) & np.isfinite(weights)
    x, y, w = reference[valid], model[valid], weights[valid]
    w = w / w.sum()
    x_anom = x - np.sum(w * x)
    y_anom = y - np.sum(w * y)
    covariance = np.sum(w * x_anom * y_anom)
    variance_product = np.sum(w * x_anom**2) * np.sum(w * y_anom**2)
    return float(covariance / np.sqrt(variance_product))


def weighted_performance_metrics(
    reference: np.ndarray, model: np.ndarray, lat: np.ndarray
) -> dict[str, float]:
    """Return area-weighted pattern correlation, RMSE, and model bias."""
    weights = np.cos(np.deg2rad(lat))[:, None] * np.ones_like(reference)
    valid = np.isfinite(reference) & np.isfinite(model) & np.isfinite(weights)
    difference = model[valid] - reference[valid]
    reference_values = reference[valid]
    model_values = model[valid]
    valid_weights = weights[valid]
    valid_weights = valid_weights / valid_weights.sum()
    reference_mean = float(np.sum(valid_weights * reference_values))
    model_mean = float(np.sum(valid_weights * model_values))
    reference_std = float(
        np.sqrt(np.sum(valid_weights * (reference_values - reference_mean) ** 2))
    )
    model_std = float(
        np.sqrt(np.sum(valid_weights * (model_values - model_mean) ** 2))
    )
    rmse = float(np.sqrt(np.sum(valid_weights * difference**2)))
    bias = float(np.sum(valid_weights * difference))
    return {
        "correlation": weighted_spatial_correlation(reference, model, lat),
        "rmse": rmse,
        "bias": bias,
        "reference_mean": reference_mean,
        "model_mean": model_mean,
        "relative_bias": 100.0 * bias / reference_mean,
        "normalized_rmse": 100.0 * rmse / abs(reference_mean),
        "std_ratio": model_std / reference_std,
    }


def load_tva_boundary(path: str | Path):
    """Load the TVA Power Service Area polygon from a GeoJSON file."""
    with Path(path).open(encoding="utf-8") as stream:
        geojson = json.load(stream)
    features = geojson.get("features", [])
    if not features:
        raise ValueError(f"No polygon features found in {path}")
    return shape(features[0]["geometry"])


def region_mask(geometry, lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Return grid cells whose centers fall inside a lon/lat polygon."""
    lon2d, lat2d = np.meshgrid(((lon + 180.0) % 360.0) - 180.0, lat)
    return contains_xy(geometry, lon2d, lat2d)


def nice_levels(low: float, high: float, n: int = 15) -> np.ndarray:
    """Return stable, evenly spaced levels even for a nearly constant field."""
    if not np.isfinite(low + high) or np.isclose(low, high):
        low, high = low - 1.0, high + 1.0
    return np.linspace(low, high, n)


def add_map(
    ax: plt.Axes,
    lon: np.ndarray,
    lat: np.ndarray,
    values: np.ndarray,
    title: str,
    levels: np.ndarray,
    cmap: str,
    label: str,
    tva_boundary,
) -> None:
    # Cartopy expects coordinates to be ordered around the chosen central
    # longitude. Reorder 0..360 data to -180..180 for a Greenwich-centered map.
    plot_lon = ((lon + 180.0) % 360.0) - 180.0
    lon_order = np.argsort(plot_lon)
    plot_lon = plot_lon[lon_order]
    plot_values = values[:, lon_order]
    norm = BoundaryNorm(levels, ncolors=256, clip=False)
    image = ax.contourf(
        plot_lon,
        lat,
        plot_values,
        levels=levels,
        cmap=cmap,
        norm=norm,
        extend="both",
        transform=ccrs.PlateCarree(),
    )
    ax.coastlines(linewidth=0.45, color="0.15")
    # A white underlay keeps the small TVA outline visible over any colormap.
    ax.add_geometries(
        [tva_boundary],
        crs=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor="white",
        linewidth=2.4,
        zorder=5,
    )
    ax.add_geometries(
        [tva_boundary],
        crs=ccrs.PlateCarree(),
        facecolor="none",
        edgecolor="#d01c8b",
        linewidth=1.2,
        zorder=6,
    )
    center = tva_boundary.centroid
    tva_label = ax.text(
        center.x,
        center.y + 3.0,
        "TVA",
        transform=ccrs.PlateCarree(),
        color="#d01c8b",
        fontsize=7,
        fontweight="bold",
        ha="center",
        va="bottom",
        zorder=7,
    )
    tva_label.set_path_effects(
        [path_effects.Stroke(linewidth=2.0, foreground="white"), path_effects.Normal()]
    )
    ax.set_global()
    ax.set_title(title, fontsize=10, loc="left")
    colorbar = plt.colorbar(
        image,
        ax=ax,
        orientation="horizontal",
        pad=0.055,
        shrink=0.78,
        format="%.1f",
    )
    colorbar.set_label(label, fontsize=11)
    colorbar.ax.tick_params(labelsize=10)


def make_figure(
    era: np.ndarray,
    model: np.ndarray,
    lon: np.ndarray,
    lat: np.ndarray,
    name: str,
    unit: str,
    sequential_cmap: str,
    output_stem: Path,
    dpi: int,
    tva_boundary,
) -> tuple[dict[str, float], dict[str, float]]:
    """Create one 2x2 figure and return global and TVA performance metrics."""
    bias = model - era
    global_metrics = weighted_performance_metrics(era, model, lat)

    combined = np.concatenate((era[np.isfinite(era)], model[np.isfinite(model)]))
    if name == "Surface temperature":
        low, high = np.nanpercentile(combined, [1, 99])
    else:
        low, high = 0.0, np.nanpercentile(combined, 99)
    field_levels = nice_levels(float(low), float(high))
    bias_limit = float(np.nanpercentile(np.abs(bias), 98))
    bias_levels = nice_levels(-bias_limit, bias_limit)

    # Centering at Greenwich places North America on the left-hand side.
    projection = ccrs.Robinson(central_longitude=0)
    fig = plt.figure(figsize=(14.0, 9.0), constrained_layout=True)
    grid = fig.add_gridspec(2, 2, height_ratios=[1.0, 1.10])
    axes = [
        fig.add_subplot(grid[0, 0], projection=projection),
        fig.add_subplot(grid[0, 1], projection=projection),
        fig.add_subplot(grid[1, 0], projection=projection),
    ]
    scatter_grid = grid[1, 1].subgridspec(
        2, 2, height_ratios=[5.2, 0.85], hspace=0.04, wspace=0.04
    )
    global_ax = fig.add_subplot(scatter_grid[0, 0])
    tva_ax = fig.add_subplot(scatter_grid[0, 1])
    table_ax = fig.add_subplot(scatter_grid[1, :])
    # Equal x/y scaling leaves unused horizontal room. Anchor the two square
    # axes toward one another so panel (d) reads as a compact comparison.
    global_ax.set_anchor("E")
    tva_ax.set_anchor("W")

    add_map(
        axes[0], lon, lat, era, "(a) ERA5", field_levels, sequential_cmap, unit,
        tva_boundary,
    )
    add_map(
        axes[1], lon, lat, model, "(b) E3SM v3", field_levels, sequential_cmap, unit,
        tva_boundary,
    )
    add_map(
        axes[2],
        lon,
        lat,
        bias,
        "(c) E3SM v3 − ERA5",
        bias_levels,
        "RdBu_r",
        unit,
        tva_boundary,
    )

    valid = np.isfinite(era) & np.isfinite(model)
    x, y = era[valid], model[valid]
    global_ax.hexbin(x, y, gridsize=55, bins="log", mincnt=1, cmap="viridis")
    scatter_low = float(min(np.nanpercentile(x, 0.5), np.nanpercentile(y, 0.5)))
    scatter_high = float(max(np.nanpercentile(x, 99.5), np.nanpercentile(y, 99.5)))
    if np.nanmin(x) >= 0 and np.nanmin(y) >= 0:
        scatter_low = 0.0
    global_ax.plot(
        [scatter_low, scatter_high],
        [scatter_low, scatter_high],
        color="0.25",
        linestyle="--",
        linewidth=1,
        label="1:1",
    )
    global_ax.set_xlim(scatter_low, scatter_high)
    global_ax.set_ylim(scatter_low, scatter_high)
    global_ax.set_aspect("equal", adjustable="box")
    global_ax.grid(alpha=0.25, linewidth=0.5)
    global_ax.set_xlabel(f"ERA5 ({unit})", fontsize=10)
    global_ax.set_ylabel(f"E3SM v3 ({unit})", fontsize=10)
    global_ax.tick_params(labelsize=9)
    global_ax.set_title(
        f"(d1) Global: r = {global_metrics['correlation']:.3f}",
        fontsize=10.5,
        loc="left",
    )
    global_ax.legend(frameon=False, fontsize=9, loc="lower right")

    tva_cells = region_mask(tva_boundary, lon, lat) & valid
    if np.count_nonzero(tva_cells) < 3:
        raise ValueError(
            "Fewer than three comparison-grid cells fall inside the TVA boundary; "
            "use a finer --resolution."
        )
    tva_x, tva_y = era[tva_cells], model[tva_cells]
    tva_metrics = weighted_performance_metrics(
        np.where(tva_cells, era, np.nan), np.where(tva_cells, model, np.nan), lat
    )
    tva_ax.scatter(
        tva_x,
        tva_y,
        s=16,
        color="#d01c8b",
        edgecolor="white",
        linewidth=0.25,
        alpha=0.8,
    )
    tva_low = float(min(np.nanmin(tva_x), np.nanmin(tva_y)))
    tva_high = float(max(np.nanmax(tva_x), np.nanmax(tva_y)))
    padding = 0.04 * max(tva_high - tva_low, 1.0)
    if tva_low >= 0:
        tva_low = 0.0
    else:
        tva_low -= padding
    tva_high += padding
    tva_ax.plot(
        [tva_low, tva_high],
        [tva_low, tva_high],
        color="0.25",
        linestyle="--",
        linewidth=1,
    )
    tva_ax.set_xlim(tva_low, tva_high)
    tva_ax.set_ylim(tva_low, tva_high)
    tva_ax.set_aspect("equal", adjustable="box")
    tva_ax.grid(alpha=0.25, linewidth=0.5)
    tva_ax.set_xlabel(f"ERA5 ({unit})", fontsize=10)
    tva_ax.set_ylabel(f"E3SM v3 ({unit})", fontsize=10)
    tva_ax.tick_params(labelsize=9)
    tva_ax.set_title(
        f"(d2) TVA: r = {tva_metrics['correlation']:.3f} (n={tva_x.size})",
        fontsize=10.5,
        loc="left",
    )

    table_ax.axis("off")
    if name == "Precipitation":
        column_widths = [0.13, 0.25, 0.16, 0.13, 0.18, 0.13]
        column_labels = [
            "Region",
            "Mean: ERA5 / E3SM",
            "RMSE",
            "nRMSE",
            "Bias",
            "σ ratio",
        ]
        table_rows = [
            [
                "Global",
                f"{global_metrics['reference_mean']:.2f} / "
                f"{global_metrics['model_mean']:.2f} {unit}",
                f"{global_metrics['rmse']:.2f} {unit}",
                f"{global_metrics['normalized_rmse']:.1f}%",
                f"{global_metrics['bias']:+.2f} ({global_metrics['relative_bias']:+.1f}%)",
                f"{global_metrics['std_ratio']:.2f}",
            ],
            [
                "TVA",
                f"{tva_metrics['reference_mean']:.2f} / "
                f"{tva_metrics['model_mean']:.2f} {unit}",
                f"{tva_metrics['rmse']:.2f} {unit}",
                f"{tva_metrics['normalized_rmse']:.1f}%",
                f"{tva_metrics['bias']:+.2f} ({tva_metrics['relative_bias']:+.1f}%)",
                f"{tva_metrics['std_ratio']:.2f}",
            ],
        ]
    else:
        # Percent normalization in degrees Celsius depends on the arbitrary
        # zero point, so temperature uses absolute RMSE and bias only.
        column_widths = [0.15, 0.29, 0.18, 0.18, 0.15]
        column_labels = ["Region", "Mean: ERA5 / E3SM", "RMSE", "Bias", "σ ratio"]
        table_rows = [
            [
                "Global",
                f"{global_metrics['reference_mean']:.2f} / "
                f"{global_metrics['model_mean']:.2f} {unit}",
                f"{global_metrics['rmse']:.2f} {unit}",
                f"{global_metrics['bias']:+.2f} {unit}",
                f"{global_metrics['std_ratio']:.2f}",
            ],
            [
                "TVA",
                f"{tva_metrics['reference_mean']:.2f} / "
                f"{tva_metrics['model_mean']:.2f} {unit}",
                f"{tva_metrics['rmse']:.2f} {unit}",
                f"{tva_metrics['bias']:+.2f} {unit}",
                f"{tva_metrics['std_ratio']:.2f}",
            ],
        ]
    metric_table = table_ax.table(
        cellText=table_rows,
        colLabels=column_labels,
        cellLoc="center",
        colLoc="center",
        colWidths=column_widths,
        loc="center",
    )
    metric_table.auto_set_font_size(False)
    metric_table.set_fontsize(8.3)
    metric_table.scale(1.0, 1.0)
    for (row, _), cell in metric_table.get_celld().items():
        cell.set_linewidth(0.4)
        cell.set_edgecolor("0.65")
        if row == 0:
            cell.set_text_props(weight="bold")
            cell.set_facecolor("0.93")

    fig.suptitle(f"{name}: annual climatology (1985–2014)", fontsize=14)
    output_stem.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_stem.with_suffix(".png"), dpi=dpi, bbox_inches="tight")
    fig.savefig(output_stem.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    return global_metrics, tva_metrics


def main() -> None:
    args = parse_args()
    target_lat, target_lon = regular_grid(args.resolution)
    output_dir = Path(args.output_dir)
    era5_path = resolve_input(args.era5)
    e3sm_path = resolve_input(args.e3sm)
    tva_path = resolve_input(args.tva_boundary)
    tva_boundary = load_tva_boundary(tva_path)
    configure_cartopy(output_dir, args.cartopy_data)

    with xr.open_dataset(era5_path, decode_times=False) as era_ds, xr.open_dataset(
        e3sm_path, decode_times=False
    ) as e3sm_ds:
        required_era = {"ts", "pr"}
        required_e3sm = {"TS", "PRECC", "PRECL", "lat", "lon"}
        missing_era = required_era.difference(era_ds.variables)
        missing_e3sm = required_e3sm.difference(e3sm_ds.variables)
        if missing_era or missing_e3sm:
            raise KeyError(
                f"Missing variables: ERA5={sorted(missing_era)}, "
                f"E3SM={sorted(missing_e3sm)}"
            )

        era_temp = era_on_grid(
            era_ds.assign(ts=temperature_celsius(era_ds["ts"])),
            "ts",
            target_lat,
            target_lon,
        )
        model_temp = e3sm_on_grid(
            e3sm_ds, temperature_celsius(e3sm_ds["TS"]), target_lat, target_lon
        )

        era_precip = era_on_grid(
            era_ds.assign(pr=precipitation_mm_day(era_ds["pr"])),
            "pr",
            target_lat,
            target_lon,
        )
        model_precip_field = precipitation_mm_day(
            e3sm_ds["PRECC"]
        ) + precipitation_mm_day(e3sm_ds["PRECL"])
        # xarray drops attrs after arithmetic; restore them for documentation.
        model_precip_field.attrs["units"] = "mm/day"
        model_precip = e3sm_on_grid(
            e3sm_ds, model_precip_field, target_lat, target_lon
        )

    temp_global, temp_tva = make_figure(
        era_temp,
        model_temp,
        target_lon,
        target_lat,
        "Surface temperature",
        "°C",
        "coolwarm",
        output_dir / "surface_temperature_comparison",
        args.dpi,
        tva_boundary,
    )
    precip_global, precip_tva = make_figure(
        era_precip,
        model_precip,
        target_lon,
        target_lat,
        "Precipitation",
        "mm day⁻¹",
        "YlGnBu",
        output_dir / "precipitation_comparison",
        args.dpi,
        tva_boundary,
    )
    print(
        "Surface temperature:\n"
        f"  global: r={temp_global['correlation']:.4f}, "
        f"RMSE={temp_global['rmse']:.3f} °C, bias={temp_global['bias']:+.3f} °C\n"
        f"  TVA:    r={temp_tva['correlation']:.4f}, "
        f"RMSE={temp_tva['rmse']:.3f} °C, bias={temp_tva['bias']:+.3f} °C"
    )
    print(
        "Precipitation:\n"
        f"  global: r={precip_global['correlation']:.4f}, "
        f"RMSE={precip_global['rmse']:.3f} mm/day, "
        f"bias={precip_global['bias']:+.3f} mm/day\n"
        f"  TVA:    r={precip_tva['correlation']:.4f}, "
        f"RMSE={precip_tva['rmse']:.3f} mm/day, "
        f"bias={precip_tva['bias']:+.3f} mm/day"
    )
    print(f"Figures written to: {output_dir.resolve()}")


if __name__ == "__main__":
    # Cartopy/matplotlib can emit harmless warnings for masked contour cells.
    warnings.filterwarnings("ignore", message=".*converting a masked element.*")
    main()
