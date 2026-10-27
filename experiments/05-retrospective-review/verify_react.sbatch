#!/bin/bash
#SBATCH --job-name=retro-react-verify
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=12G
#SBATCH --time=00:30:00
#SBATCH --signal=B:TERM@60
#SBATCH --output=/mnt/data/private/cmaira/bonsai_perf/retrospective-20261003/react-%j.log
set -euo pipefail
ROOT=/mnt/data/private/cmaira/bonsai_perf
cleanup() {
  docker ps -aq --filter "label=retro.job=$SLURM_JOB_ID" | xargs -r docker rm -f >/dev/null 2>&1 || true
}
trap cleanup EXIT
trap 'exit 143' TERM INT
srun docker run --rm --name "retro-controller-$SLURM_JOB_ID" --label "retro.job=$SLURM_JOB_ID" \
 --cpus=1 --memory=3g -e SLURM_JOB_ID="$SLURM_JOB_ID" \
 -v "$ROOT:$ROOT" -v /var/run/docker.sock:/var/run/docker.sock -v /usr/bin/docker:/usr/bin/docker:ro \
 ml_benchmark:latest python3 "$ROOT/retrospective-20261003/verify_react.py"
