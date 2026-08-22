#!/usr/bin/env bash
# Build share tarballs for external Frontier users.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAMP="$(date +%Y%m%d)"
DIST="$ROOT/dist"
NAME="water4energy_diagnostic"
STAGE="$DIST/$NAME"
mkdir -p "$DIST"
rm -rf "$STAGE"
mkdir -p "$STAGE"

# Copy the shareable tree: scripts, docs, TVA polygon, Cartopy cache, example plots.
# Skip venv, runtime caches, previous plots, and NetCDFs (NetCDFs go only in the full tarball).
rsync -a \
  --exclude '.venv/' \
  --exclude '.mplconfig/' \
  --exclude 'plots/' \
  --exclude 'plots_frontier_test/' \
  --exclude 'dist/' \
  --exclude '*.nc' \
  --exclude '__pycache__/' \
  "$ROOT/" "$STAGE/"

chmod +x "$STAGE"/*.sh "$STAGE"/*.sbatch 2>/dev/null || true

CODE="$DIST/${NAME}_frontier_code_${STAMP}.tar.gz"
FULL="$DIST/${NAME}_frontier_full_${STAMP}.tar.gz"

tar -C "$DIST" -czf "$CODE" "$NAME"

# Full bundle: add climatology NetCDFs that sit next to this script.
shopt -s nullglob
nc_files=("$ROOT"/*.nc)
if [[ ${#nc_files[@]} -lt 2 ]]; then
  echo "pack_share_bundle.sh: expected two climatology .nc files in $ROOT" >&2
  exit 1
fi
cp -a "${nc_files[@]}" "$STAGE/"
tar -C "$DIST" -czf "$FULL" "$NAME"
rm -rf "$STAGE"

echo "Wrote:"
ls -lh "$CODE" "$FULL"
echo
echo "Share the full tarball with Frontier users who should be able to run the diagnostic."
echo "The code tarball is GitHub-sized and expects the two .nc files to be supplied separately."
