#!/bin/bash
#SBATCH --job-name=bonsai-counterfactual
#SBATCH --time=00:20:00
#SBATCH --signal=B:TERM@60
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=48G
#SBATCH --gres=gpu:1
set -euo pipefail
ROOT=/mnt/data/private/cmaira/bonsai_perf
WORK=$ROOT/trajectory-analysis-20260929
NAME="diverge-cf-${SLURM_JOB_ID}-server"
cleanup() {
    docker logs "$NAME" > "$WORK/counterfactual-server.log" 2>&1 || true
    docker rm -f "$NAME" "diverge-cf-${SLURM_JOB_ID}-setup" "diverge-cf-${SLURM_JOB_ID}-control" "diverge-cf-${SLURM_JOB_ID}-intervention" >/dev/null 2>&1 || true
    docker image rm "diverge-cf-${SLURM_JOB_ID}:checkpoint" >/dev/null 2>&1 || true
}
trap cleanup EXIT
trap 'exit 143' TERM INT
docker run -d --rm --name "$NAME" --network=host --cpus=14 --gpus "device=$CUDA_VISIBLE_DEVICES" \
  --user "$(id -u):$(id -g)" -e HOME=/tmp -e LD_LIBRARY_PATH=/work/src_p215/build/bin \
  -v "$ROOT:/work:ro" ml_benchmark:latest /work/src_p215/build/bin/llama-server \
  -m /work/models/Ternary-Bonsai-2-27B-PTQ1_0.gguf -ngl 99 -fa on -c 32768 \
  --parallel 1 --port 8203 --seed 1 --reasoning-preserve
for i in $(seq 1 120); do
    if curl -fsS http://127.0.0.1:8203/health >/dev/null 2>&1; then break; fi
    sleep 2
done
curl -fsS http://127.0.0.1:8203/health >/dev/null
python3 "$WORK/counterfactual.py" "$WORK"
