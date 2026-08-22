#!/usr/bin/env bash
# Create the Frontier Python environment for E3SM–ERA5 diagnostics.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if ! command -v module >/dev/null 2>&1; then
  echo "This setup script expects the Frontier environment-modules command." >&2
  echo "On a Frontier login node run:  module load cray-python/3.11.7" >&2
  exit 1
fi

module load cray-python/3.11.7

if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r "$ROOT/requirements.txt"
.venv/bin/python - <<'PY'
mods = ["cartopy", "matplotlib", "numpy", "scipy", "shapely", "xarray", "netCDF4"]
for name in mods:
    mod = __import__(name)
    print(f"{name}: {getattr(mod, '__version__', '?')}")
print("venv OK")
PY

echo
echo "Frontier venv is ready: $ROOT/.venv"
echo "Next:  ./run_frontier.sh"
