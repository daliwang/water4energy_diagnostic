#!/usr/bin/env bash
# Run the E3SM–ERA5 diagnostic on Frontier (login node or compute node).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  echo "No .venv found. Run ./setup_frontier_venv.sh first." >&2
  exit 1
fi

for f in ERA5_ANN_198501_201412_climo.nc \
         v3.LR.historical_0101_ANN_198501_201412_climo.nc \
         tva_power_service_area.geojson; do
  if [[ ! -f "$ROOT/$f" ]]; then
    echo "Missing input: $ROOT/$f" >&2
    echo "The full share tarball includes the NetCDF climatology files." >&2
    exit 1
  fi
done

mkdir -p .mplconfig plots
export MPLBACKEND=Agg
export MPLCONFIGDIR="$ROOT/.mplconfig"

.venv/bin/python plot_e3sm_era5.py \
  --era5 "$ROOT/ERA5_ANN_198501_201412_climo.nc" \
  --e3sm "$ROOT/v3.LR.historical_0101_ANN_198501_201412_climo.nc" \
  --tva-boundary "$ROOT/tva_power_service_area.geojson" \
  --cartopy-data "$ROOT/cartopy_data" \
  --resolution 1.0 \
  --output-dir "$ROOT/plots" \
  --dpi 200
