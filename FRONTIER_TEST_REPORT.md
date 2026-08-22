# Frontier launch report: water4energy_diagnostic

**Host:** Frontier `login04`  
**Date:** 2026-08-22  
**Package:** `daliwang/water4energy_diagnostic` at `/lustre/orion/lrn105/proj-shared/wangd/water4energy/Diagnostics`  
**Script:** `plot_e3sm_era5.py`

## Question

Can this diagnostic be launched on Frontier for collaborators who will also use Frontier?

## Answer

Yes, after a local virtual environment is created. It does **not** run with the default Frontier Python stack.

## What failed first

`module load cray-python/3.11.7` provides Python 3.11.7 with numpy and scipy, but not the plotting stack. The script stopped immediately:

```text
ModuleNotFoundError: No module named 'cartopy'
```

Also missing from cray-python: matplotlib, shapely, xarray, netCDF4.

System `/usr/bin/python3` is Python 3.6 and is not usable. Older conda environments under `~/.conda/envs/` from 2020 fail with `exec format error` on Frontier.

## What worked

1. `module load cray-python/3.11.7`
2. `python -m venv .venv` in this folder
3. `pip install -r requirements.txt` (manylinux wheels; no conda build required)
4. `MPLBACKEND=Agg` and a writable `MPLCONFIGDIR`
5. Bundled Natural Earth coastline under `cartopy_data/` so Cartopy does not need a download for the map outlines

Command used for the successful run:

```bash
cd /lustre/orion/lrn105/proj-shared/wangd/water4energy/Diagnostics
MPLBACKEND=Agg MPLCONFIGDIR="$PWD/.mplconfig" \
  .venv/bin/python plot_e3sm_era5.py \
  --era5 ERA5_ANN_198501_201412_climo.nc \
  --e3sm v3.LR.historical_0101_ANN_198501_201412_climo.nc \
  --tva-boundary tva_power_service_area.geojson \
  --resolution 1.0 \
  --output-dir plots_frontier_test \
  --dpi 200
```

**Wall time:** ~37 seconds after dependencies were installed.  
**Exit status:** 0  
**Login-node memory:** hundreds of GB available; the job is light.

Those steps are now `./setup_frontier_venv.sh` and `./run_frontier.sh`.

## Software versions (working set)

Pinned in `requirements.txt`:

| Package | Version |
|---|---|
| cartopy | 0.25.0 |
| matplotlib | 3.11.1 |
| netCDF4 | 1.7.4 |
| numpy | 2.4.6 |
| scipy | 1.17.1 |
| shapely | 2.1.2 |
| xarray | 2026.7.0 |

## Metrics from the Frontier run

```text
Surface temperature:
  global: r=0.9937, RMSE=1.685 °C, bias=+0.324 °C
  TVA:    r=0.9519, RMSE=0.565 °C, bias=-0.371 °C
Precipitation:
  global: r=0.8879, RMSE=1.047 mm/day, bias=+0.083 mm/day
  TVA:    r=0.5299, RMSE=0.250 mm/day, bias=+0.215 mm/day
```

Example figures from this run are stored in `example_plots/`.

## TVA location check

The GeoJSON is EPSG:4326 with longitude −90.35 to −81.65 and latitude 32.32 to 37.60. On the Robinson global maps the magenta outline sits over the southeastern United States (Tennessee and neighboring states). That is the correct TVA Power Service Area. The `TVA` text is offset about 3° north of the polygon.

## Input checksums

| File | Size | SHA256 |
|---|---|---|
| `ERA5_ANN_198501_201412_climo.nc` | 1.1 GB | `04489cbe1d16c888b1a96f9f2963c9f98172611c6d9fe49ec17d3533f04026ac` |
| `v3.LR.historical_0101_ANN_198501_201412_climo.nc` | 153 MB | `9d749b52eb07308566074c9a2b212f25eb4f14f9af8dbdf5c45db809d7216aa2` |

These NetCDF files stay on disk and in the **full** share tarball. They are gitignored.

## Recommendation for collaborators

Give them `water4energy_diagnostic_frontier_full_YYYYMMDD.tar.gz` (from `./pack_share_bundle.sh`). Ask them to run the two scripts above on a Frontier login node. A batch job is optional; this diagnostic is small enough for login-node use.
