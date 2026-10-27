#!/bin/bash
#SBATCH --job-name=retrospective-review
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:10:00
#SBATCH --output=/mnt/data/private/cmaira/bonsai_perf/retrospective-20261003/prepare-%j.log
set -euo pipefail
ROOT=/mnt/data/private/cmaira/bonsai_perf
cleanup() { docker rm -f "retro-prepare-$SLURM_JOB_ID" >/dev/null 2>&1 || true; }
trap cleanup EXIT
trap 'exit 143' TERM INT
srun docker run --rm --name "retro-prepare-$SLURM_JOB_ID" --cpus=2 --memory=6g \
  -v "$ROOT:$ROOT" ml_benchmark:latest python3 "$ROOT/retrospective-20261003/prepare_review.py"
