#!/bin/bash
#SBATCH --job-name=bonsai-judge-smoke
#SBATCH --time=00:30:00
#SBATCH --signal=B:TERM@60
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=110G
#SBATCH --gres=gpu:1
#SBATCH --output=/mnt/data/private/cmaira/bonsai_perf/recovery-study-20261003/judge-smoke-%j.log
set -euo pipefail
ROOT=/mnt/data/private/cmaira/bonsai_perf
WORK=$ROOT/recovery-study-20261003
cleanup() {
    docker logs "judge-$SLURM_JOB_ID-server" > "$WORK/judge-smoke-server-$SLURM_JOB_ID.log" 2>&1 || true
    docker ps -aq --filter "label=study.job=$SLURM_JOB_ID" | xargs -r docker rm -f >/dev/null 2>&1 || true
}
trap cleanup EXIT
trap 'exit 143' TERM INT
printf 'SLURM_JOB_GPUS=%s CUDA_VISIBLE_DEVICES=%s\n' "${SLURM_JOB_GPUS:-}" "$CUDA_VISIBLE_DEVICES"
docker run -d --name "judge-$SLURM_JOB_ID-server" --label "study.job=$SLURM_JOB_ID" \
  --network=host --cpus=12 --memory=85g --gpus "device=${SLURM_JOB_GPUS:-$CUDA_VISIBLE_DEVICES}" --user "$(id -u):$(id -g)" \
  -e HOME=/tmp -e LD_LIBRARY_PATH=/work/src_p215/build/bin -v "$ROOT:/work:ro" ml_benchmark:latest \
  /work/src_p215/build/bin/llama-server -m /work/models/Qwen3.8-27B-F16.gguf \
  -ngl 99 -fa on -c 49152 --parallel 1 --port 8240 --reasoning-preserve
srun docker run --rm --name "judge-$SLURM_JOB_ID-client" --label "study.job=$SLURM_JOB_ID" \
  --network=host --cpus=2 --memory=8g -e STUDY_JOB_ID="$SLURM_JOB_ID" \
  -v "$ROOT:$ROOT" ml_benchmark:latest python3 "$WORK/judge_smoke.py"
