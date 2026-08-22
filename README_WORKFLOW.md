# ERA5–E3SMv3 climatology comparison workflow

This repository is `daliwang/water4energy_diagnostics`, a sibling of `../data`.
Frontier users: start with [`README.md`](README.md). This file is the scientific method note.

This package creates publication-ready comparisons of 1985–2014 annual-mean
surface temperature and precipitation from ERA5 and E3SMv3. It generates one
four-panel PNG and PDF for each variable.

## Package contents

The workflow expects these files:

| File | Purpose |
|---|---|
| `plot_e3sm_era5.py` | Main command-line program |
| `requirements.txt` | Required Python packages |
| `ERA5_ANN_198501_201412_climo.nc` | ERA5 annual climatology |
| `v3.LR.historical_0101_ANN_198501_201412_climo.nc` | E3SMv3 annual climatology |
| `tva_power_service_area.geojson` | TVA Power Service Area boundary |

The supplied TVA polygon is the public `TVA_Power_Service_Area` feature layer
published by TVA GIS & Mapping (ArcGIS item
[`87cdc9128b6f4afaa7f3428fc43bb899`](https://www.arcgis.com/home/item.html?id=87cdc9128b6f4afaa7f3428fc43bb899&sublayer=0)).
It represents the power service area, not the Tennessee River watershed.

## Runtime requirements

- Python 3.9 or newer
- Approximately 4 GB of memory recommended
- A writable output directory
- Network access on the first run for Cartopy's Natural Earth 110 m coastline,
  unless that coastline cache is supplied in advance

Install the dependencies in an isolated environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

For Conda-based or containerized execution, install the same packages listed in
`requirements.txt`. Cartopy may be easier to install from `conda-forge` on
systems without compatible binary wheels.

## Basic execution

Run from the directory containing the inputs:

```bash
mkdir -p .mplconfig
MPLBACKEND=Agg MPLCONFIGDIR=.mplconfig \
  .venv/bin/python plot_e3sm_era5.py
```

The default command is equivalent to:

```bash
MPLBACKEND=Agg MPLCONFIGDIR=.mplconfig \
  .venv/bin/python plot_e3sm_era5.py \
  --era5 ERA5_ANN_198501_201412_climo.nc \
  --e3sm v3.LR.historical_0101_ANN_198501_201412_climo.nc \
  --tva-boundary tva_power_service_area.geojson \
  --resolution 1.0 \
  --output-dir plots \
  --dpi 200
```

Use absolute paths in a managed cloud workflow:

```bash
MPLBACKEND=Agg MPLCONFIGDIR=/workflow/output/.matplotlib \
  python plot_e3sm_era5.py \
  --era5 /workflow/input/ERA5_ANN_198501_201412_climo.nc \
  --e3sm /workflow/input/v3.LR.historical_0101_ANN_198501_201412_climo.nc \
  --tva-boundary /workflow/input/tva_power_service_area.geojson \
  --output-dir /workflow/output/plots
```

The script returns a nonzero exit status if required variables, units, or input
geometry are missing or invalid. Summary metrics are also written to standard
output so they are available in workflow logs.

## Command-line options

| Option | Default | Description |
|---|---|---|
| `--era5` | `ERA5_ANN_198501_201412_climo.nc` | ERA5 NetCDF input |
| `--e3sm` | `v3.LR.historical_0101_ANN_198501_201412_climo.nc` | E3SMv3 NetCDF input |
| `--tva-boundary` | `tva_power_service_area.geojson` | TVA polygon in GeoJSON format |
| `--resolution` | `1.0` | Common comparison-grid spacing in degrees |
| `--output-dir` | `plots` | Writable output directory |
| `--dpi` | `200` | PNG resolution |

Display the built-in help with:

```bash
python plot_e3sm_era5.py --help
```

## Required NetCDF variables

| Dataset | Variables | Expected structure |
|---|---|---|
| ERA5 | `lat`, `lon`, `ts`, `pr` | Regular latitude–longitude grid; singleton climatology `time` is accepted |
| E3SMv3 | `lat`, `lon`, `TS`, `PRECC`, `PRECL` | Native unstructured `ncol` grid; singleton climatology `time` is accepted |

Temperature units must be Kelvin or degrees Celsius. Precipitation units must
be one of the forms recognized by the script for `kg m-2 s-1`, `m s-1`,
`mm s-1`, or `mm day-1`.

## Processing method

1. Build a regular global cell-center grid. The default spacing is 1 degree.
2. Convert ERA5 `ts` and E3SM `TS` to degrees Celsius.
3. Convert ERA5 `pr` and E3SM `PRECC + PRECL` to millimetres per day.
4. Interpolate both datasets to the common grid:
   - ERA5 uses linear latitude–longitude interpolation.
   - E3SM uses linear interpolation from native `ncol` centers, with cyclic
     longitude handling and nearest-neighbor filling only for small polar gaps.
5. Calculate the bias as `E3SM − ERA5`.
6. Select TVA grid cells by testing whether their centers fall inside the TVA
   polygon. At the default 1-degree resolution, 20 grid-cell centers are used.
7. Calculate area-weighted statistics using `cos(latitude)` weights.

The default 1-degree grid is recommended for this E3SM file. Its native
nearest-neighbor spacing is approximately 1.1–1.5 degrees (median 1.33
degrees). A 0.5- or 0.25-degree target is permitted, but it oversamples the
model and does not create independent model information.

Linear interpolation can smooth localized fields, especially precipitation.
For a production evaluation requiring strict conservation, replace the
precipitation interpolation with conservative remapping using the E3SM source
cell mesh/bounds. The current climatology file provides cell centers and area,
but not the complete mesh geometry required by conservative remappers.

## Figure organization

Each output has four main panels:

1. ERA5 annual climatology
2. E3SMv3 annual climatology
3. E3SMv3 minus ERA5 bias
4. Global and TVA scatter comparisons plus a compact metrics table

Global scatter colors show logarithmic grid-cell density. The TVA scatter
shows individual comparison-grid cells. Dashed lines show perfect 1:1
agreement. Maps use a Robinson projection centered at 0 degrees longitude, so
North America appears on the left. The TVA boundary is shown in magenta with a
white underlay.

Map color limits are percentile-based to prevent a small number of extremes
from hiding the principal spatial structure. Temperature climatology limits
use the combined ERA5/E3SM 1st and 99th percentiles; precipitation uses zero to
the combined 99th percentile. Bias limits are symmetric around zero using the
98th percentile of absolute bias.

## Reported metrics

All metrics are area weighted on the common regular grid.

| Metric | Definition and interpretation |
|---|---|
| Pattern correlation (`r`) | Weighted Pearson correlation of paired spatial grid cells |
| Mean | Weighted regional or global average for ERA5 and E3SM |
| Bias | Weighted mean of `E3SM − ERA5`; positive means E3SM is warmer or wetter |
| RMSE | Weighted root-mean-square grid-cell error; signed errors cannot cancel |
| nRMSE | Precipitation RMSE divided by the ERA5 mean, expressed as a percentage |
| Relative bias | Precipitation bias divided by the ERA5 mean, expressed as a percentage |
| Standard-deviation ratio | E3SM spatial standard deviation divided by ERA5 spatial standard deviation |

Mean-normalized RMSE is intentionally omitted for temperature. Normalizing by
a Celsius mean is not invariant to changing from Celsius to Kelvin because the
two scales have different zero points. Absolute temperature RMSE is reported
instead.

## Outputs

The output directory receives:

```text
plots/
├── precipitation_comparison.png
├── precipitation_comparison.pdf
├── surface_temperature_comparison.png
└── surface_temperature_comparison.pdf
```

Cartopy also places downloaded Natural Earth coastline data under
`<output-dir>/.cartopy/`. In an offline production environment, prepopulate
this directory with Cartopy's `110m_physical/ne_110m_coastline` dataset or run
one network-enabled cache-warming job before normal workflow execution.

The workflow overwrites figure files with the same names. Input files are
opened read-only and are never modified.

## Expected reference results

Using the supplied files and default 1-degree grid, the script prints values
close to:

```text
Surface temperature:
  global: r=0.9937, RMSE=1.685 °C, bias=+0.325 °C
  TVA:    r=0.9569, RMSE=0.542 °C, bias=-0.358 °C
Precipitation:
  global: r=0.8879, RMSE=1.047 mm/day, bias=+0.083 mm/day
  TVA:    r=0.5405, RMSE=0.249 mm/day, bias=+0.212 mm/day
```

Small numerical differences can occur across interpolation-library versions,
but material differences should be investigated.

## Suggested workflow checks

1. Confirm all three inputs exist and are readable.
2. Validate that the required variables and units are present.
3. Run with a noninteractive Matplotlib backend (`MPLBACKEND=Agg`) and set
   `MPLCONFIGDIR` to a writable cache directory.
4. Require a zero process exit status.
5. Capture standard output and error in the workflow log.
6. Confirm that all four PNG/PDF products exist and have nonzero size.
7. Compare printed metrics with the reference values above as a regression
   check when dependencies or source data change.
