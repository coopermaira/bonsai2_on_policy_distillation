#!/bin/bash
#SBATCH --job-name=retrospective-grade
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:05:00
#SBATCH --output=/mnt/data/private/cmaira/bonsai_perf/retrospective-20261003/grade-%j.log
set -euo pipefail
ROOT=/mnt/data/private/cmaira/bonsai_perf
cleanup() { docker rm -f "retro-grade-$SLURM_JOB_ID" >/dev/null 2>&1 || true; }
trap cleanup EXIT
trap 'exit 143' TERM INT
srun docker run --rm --name "retro-grade-$SLURM_JOB_ID" --cpus=2 --memory=3g \
  -v "$ROOT:$ROOT" ml_benchmark:latest python3 "$ROOT/retrospective-20261003/grade_review.py"
