#!/bin/bash
#SBATCH --job-name=tbv2-build
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=/mnt/data/private/cmaira/bonsai_perf/harness-v2/build-%j.log
set -euo pipefail
ROOT=/mnt/data/private/cmaira/bonsai_perf/harness-v2
cleanup() { docker rm -f "tbv2-build-$SLURM_JOB_ID" >/dev/null 2>&1 || true; }
trap cleanup EXIT
trap 'exit 143' TERM INT
srun docker run --rm --name "tbv2-build-$SLURM_JOB_ID" --cpus=2 --memory=4g \
 -v "$ROOT:$ROOT" -v /var/run/docker.sock:/var/run/docker.sock -v /usr/bin/docker:/usr/bin/docker:ro \
 ml_benchmark:latest python3 "$ROOT/build.py"
