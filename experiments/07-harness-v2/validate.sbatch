#!/bin/bash
#SBATCH --job-name=tbv2-validate
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=/mnt/data/private/cmaira/bonsai_perf/harness-v2/validate-%j.log
set -euo pipefail
ROOT=/mnt/data/private/cmaira/bonsai_perf/harness-v2
cleanup() { docker ps -aq --filter "label=tbv2.job=$SLURM_JOB_ID" | xargs -r docker rm -f >/dev/null 2>&1 || true; }
trap cleanup EXIT
trap 'exit 143' TERM INT
srun docker run --rm --name "tbv2-validator-$SLURM_JOB_ID" --label "tbv2.job=$SLURM_JOB_ID" --cpus=2 --memory=4g -e SLURM_JOB_ID \
 -v "$ROOT:$ROOT" -w "$ROOT" -v /var/run/docker.sock:/var/run/docker.sock -v /usr/bin/docker:/usr/bin/docker:ro \
 ml_benchmark:latest bash -c 'python3 -m unittest -v test_harness && python3 integration.py && python3 verify.py'
