# water4energy_diagnostic

**Repo:** `daliwang/water4energy_diagnostic` (`git@github.com:daliwang/water4energy_diagnostic.git`)  
**Frontier path:** `/lustre/orion/lrn105/proj-shared/wangd/water4energy/Diagnostics`  
**Sibling of:** `daliwang/water4energy` (`../data`)

Self-contained comparison of **1985–2014 annual-mean** surface temperature and precipitation from **ERA5** and **E3SMv3**, including a **TVA Power Service Area** overlay.

This repository is independent of the observation-staging tree. Collaborators can clone or unpack it on Frontier without the rest of Water4Energy.

Verified on Frontier `login04` on **2026-08-22**. Details: [`FRONTIER_TEST_REPORT.md`](FRONTIER_TEST_REPORT.md). Scientific method: [`README_WORKFLOW.md`](README_WORKFLOW.md).

## What is in this package

| Item | Role | In git? | In full tarball? |
|---|---|---|---|
| `plot_e3sm_era5.py` | Plot / metrics program | yes | yes |
| `requirements.txt` | Pinned Python packages | yes | yes |
| `tva_power_service_area.geojson` | TVA Power Service Area polygon | yes | yes |
| `cartopy_data/` | Natural Earth 110 m coastline cache | yes | yes |
| `setup_frontier_venv.sh` | Create `.venv` on Frontier | yes | yes |
| `run_frontier.sh` | Run the diagnostic | yes | yes |
| `run_frontier.sbatch` | Optional Slurm wrapper | yes | yes |
| `example_plots/` | Frontier-generated PNG/PDF examples | yes | yes |
| `ERA5_ANN_198501_201412_climo.nc` | ERA5 climatology (~1.1 GB) | no (too large) | yes |
| `v3.LR.historical_0101_ANN_198501_201412_climo.nc` | E3SM climatology (~153 MB) | no | yes |

The TVA file is the public **TVA Power Service Area** layer (ArcGIS item `87cdc9128b6f4afaa7f3428fc43bb899`). It is the electric service area, not the Tennessee River watershed. Bounds are about 90.3°W–81.6°W and 32.3°N–37.6°N.

Do **not** copy `.venv` between machines. Recreate it on Frontier with `./setup_frontier_venv.sh`.

## Frontier quick start

On a Frontier login node:

```bash
cd /lustre/orion/lrn105/proj-shared/wangd/water4energy/Diagnostics
./setup_frontier_venv.sh
./run_frontier.sh
```

The first command loads `cray-python/3.11.7`, creates `./.venv`, and installs the pinned wheels. The second command writes:

```text
plots/precipitation_comparison.png
plots/precipitation_comparison.pdf
plots/surface_temperature_comparison.png
plots/surface_temperature_comparison.pdf
```

Runtime on a login node was about **40 seconds** after the venv existed. For a compute-node run:

```bash
sbatch --account=YOUR_PROJECT run_frontier.sbatch
```

## Share with external Frontier users

```bash
./pack_share_bundle.sh
```

That writes:

- `dist/water4energy_diagnostic_frontier_full_YYYYMMDD.tar.gz` — **give this to users who should run the diagnostic** (includes NetCDFs)
- `dist/water4energy_diagnostic_frontier_code_YYYYMMDD.tar.gz` — code/docs only

Users unpack and run:

```bash
tar -xzf water4energy_diagnostic_frontier_full_YYYYMMDD.tar.gz
cd water4energy_diagnostic
./setup_frontier_venv.sh
./run_frontier.sh
```

They need a Frontier account, `cray-python/3.11.7`, and outbound HTTPS on the first `pip install`. After the venv exists, the plot step can run offline because `cartopy_data/` already contains the coastline shapefile.

## Expected Frontier results

From the 2026-08-22 login-node run (`cray-python/3.11.7`, packages in `requirements.txt`):

```text
Surface temperature:
  global: r=0.9937, RMSE=1.685 °C, bias=+0.324 °C
  TVA:    r=0.9519, RMSE=0.565 °C, bias=-0.371 °C
Precipitation:
  global: r=0.8879, RMSE=1.047 mm/day, bias=+0.083 mm/day
  TVA:    r=0.5299, RMSE=0.250 mm/day, bias=+0.215 mm/day
```

Small differences across library versions are normal. Large differences are not.

## TVA overlay

The magenta outline on the global maps is the TVA service area over Tennessee and adjacent parts of Alabama, Mississippi, Kentucky, Georgia, North Carolina, and Virginia. The printed `TVA` label is drawn 3° north of the polygon centroid, so the text sits slightly north of the outline.

## Workspace layout

```text
/lustre/orion/lrn105/proj-shared/wangd/water4energy/
  data/            # git: daliwang/water4energy
  Diagnostics/     # this repo (water4energy_diagnostic)
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `No module named 'cartopy'` | Default Frontier Python is not enough. Run `./setup_frontier_venv.sh`. |
| `Missing input: ...climo.nc` | You unpacked the code-only tarball. Use the full tarball, or copy the two `.nc` files into this folder. |
| Cartopy download / coastline error | The run script already passes `--cartopy-data cartopy_data`. |
| Matplotlib cache / display errors | The run script sets `MPLBACKEND=Agg` and `MPLCONFIGDIR` inside the package. |
| `sbatch` account error | Replace `YOUR_PROJECT` with your OLCF project, or just use `./run_frontier.sh` on a login node. |
