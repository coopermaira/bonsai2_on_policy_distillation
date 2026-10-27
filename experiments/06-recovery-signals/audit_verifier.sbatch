#!/bin/bash
#SBATCH --job-name=bonsai-verifier-audit
#SBATCH --time=00:10:00
#SBATCH --signal=B:TERM@60
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=12G
#SBATCH --output=/mnt/data/private/cmaira/bonsai_perf/recovery-study-20261003/verifier-audit-%j.log
set -euo pipefail
ROOT=/mnt/data/private/cmaira/bonsai_perf
cleanup() { docker ps -aq --filter "label=study.job=$SLURM_JOB_ID" | xargs -r docker rm -f >/dev/null 2>&1 || true; }
trap cleanup EXIT
trap 'exit 143' TERM INT
srun docker run --rm --name "verifier-controller-$SLURM_JOB_ID" --label "study.job=$SLURM_JOB_ID" \
  --cpus=2 --memory=6g -e STUDY_JOB_ID="$SLURM_JOB_ID" -v "$ROOT:$ROOT" \
  -v /var/run/docker.sock:/var/run/docker.sock -v /usr/bin/docker:/usr/bin/docker:ro \
  ml_benchmark:latest python3 "$ROOT/recovery-study-20261003/audit_verifier.py"
