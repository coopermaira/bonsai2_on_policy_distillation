#!/bin/bash
#SBATCH --job-name=tb-review-index
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --output=/mnt/data/private/cmaira/bonsai_perf/harness-v2/review-index-%j.log
set -euo pipefail
ROOT=/mnt/data/private/cmaira/bonsai_perf/harness-v2
trap 'docker rm -f tb-review-index-$SLURM_JOB_ID >/dev/null 2>&1 || true' EXIT
trap 'exit 143' TERM INT
srun docker run --rm --name tb-review-index-$SLURM_JOB_ID --cpus=2 --memory=4g -v "$ROOT:$ROOT" ml_benchmark:latest python3 "$ROOT/prepare_independent.py" &
wait $!
