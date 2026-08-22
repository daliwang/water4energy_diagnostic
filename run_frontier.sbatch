#!/bin/bash
# Optional Frontier batch wrapper. Replace the account before submitting:
#   sbatch --account=YOUR_PROJECT run_frontier.sbatch
#SBATCH -J e3sm_era5_diag
#SBATCH -p batch
#SBATCH -t 00:20:00
#SBATCH -N 1
#SBATCH --ntasks=1
#SBATCH -c 4
#SBATCH -o e3sm_era5_diag.%j.out
#SBATCH -e e3sm_era5_diag.%j.err

set -euo pipefail
cd "$(dirname "$0")"
module load cray-python/3.11.7
./run_frontier.sh
