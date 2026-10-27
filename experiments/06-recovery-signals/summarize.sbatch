#!/bin/bash
#SBATCH --job-name=bonsai-summary
#SBATCH --time=00:15:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --output=/mnt/data/private/cmaira/bonsai_perf/recovery-study-20261003/summary-%j.log
set -euo pipefail
ROOT=/mnt/data/private/cmaira/bonsai_perf
srun docker run --rm --cpus=2 --memory=6g -v "$ROOT:$ROOT" ml_benchmark:latest \
    python3 "$ROOT/recovery-study-20261003/summarize.py"
