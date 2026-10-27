#!/bin/bash
#SBATCH --job-name=bonsai-divergence
#SBATCH --time=00:45:00
#SBATCH --signal=B:TERM@60
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=160G
#SBATCH --gres=gpu:2
set -euo pipefail
ROOT=/mnt/data/private/cmaira/bonsai_perf
WORK=$ROOT/trajectory-analysis-20260929
NAMES=("diverge-${SLURM_JOB_ID}-fp16" "diverge-${SLURM_JOB_ID}-bonsai")
cleanup() {
    docker logs "${NAMES[0]}" > "$WORK/fp16-server.log" 2>&1 || true
    docker logs "${NAMES[1]}" > "$WORK/bonsai-server.log" 2>&1 || true
    docker rm -f "${NAMES[@]}" >/dev/null 2>&1 || true
}
trap cleanup EXIT
trap 'exit 143' TERM INT
IFS=',' read -r -a GPUS <<< "$CUDA_VISIBLE_DEVICES"
test "${#GPUS[@]}" -eq 2
for i in 0 1; do
    if [ "$i" -eq 0 ]; then MODEL=Qwen3.8-27B-F16.gguf; PORT=8201; else MODEL=Ternary-Bonsai-2-27B-PTQ1_0.gguf; PORT=8202; fi
    docker run -d --rm --name "${NAMES[$i]}" --label "bonsai.divergence.job=$SLURM_JOB_ID" \
      --network=host --cpus=16 --gpus "device=${GPUS[$i]}" --user "$(id -u):$(id -g)" \
      -e HOME=/tmp -e LD_LIBRARY_PATH=/work/src_p215/build/bin \
      -v "$ROOT:/work:ro" ml_benchmark:latest \
      /work/src_p215/build/bin/llama-server -m "/work/models/$MODEL" \
      -ngl 99 -fa on -c 196608 --parallel 1 --port "$PORT" --seed 1 --reasoning-preserve
done
python3 "$WORK/probe.py" "$WORK"
