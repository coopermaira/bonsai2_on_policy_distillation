#!/bin/bash
#SBATCH --job-name=tbv2-eight-paired
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --mem=384G
#SBATCH --gres=gpu:4
#SBATCH --signal=B:USR1@120
#SBATCH --output=/mnt/data/private/cmaira/bonsai_perf/harness-v2/run-%j.log
set -euo pipefail
ROOT=/mnt/data/private/cmaira/bonsai_perf/harness-v2
cleanup() { docker ps -aq --filter "label=tbv2.job=$SLURM_JOB_ID" | xargs -r docker rm -f >/dev/null 2>&1 || true; }
trap cleanup EXIT
trap 'cleanup; exit 143' TERM INT USR1
REMAINING=$(( $(date -u -d '2026-10-05 14:00:00' +%s) - $(date -u +%s) ))
if [ "$REMAINING" -le 0 ]; then exit 0; fi
timeout --signal=TERM --kill-after=30s "${REMAINING}s" srun docker run --rm --name "tbv2-controller-$SLURM_JOB_ID" --label "tbv2.job=$SLURM_JOB_ID" --cpus=4 --memory=12g --network=host -e SLURM_JOB_ID -e SLURM_JOB_GPUS \
 -v "$ROOT:$ROOT" -w "$ROOT" -v /var/run/docker.sock:/var/run/docker.sock -v /usr/bin/docker:/usr/bin/docker:ro \
 ml_benchmark:latest python3 -u controller.py &
STEP_PID=$!
wait "$STEP_PID"
