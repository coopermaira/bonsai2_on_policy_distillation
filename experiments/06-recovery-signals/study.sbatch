#!/bin/bash
#SBATCH --job-name=bonsai-recovery
#SBATCH --time=04:00:00
#SBATCH --signal=B:TERM@60
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=40
#SBATCH --mem=220G
#SBATCH --gres=gpu:2
#SBATCH --output=/mnt/data/private/cmaira/bonsai_perf/recovery-study-20261003/study-%j.log
set -euo pipefail
ROOT=/mnt/data/private/cmaira/bonsai_perf
WORK=$ROOT/recovery-study-20261003
cleanup() {
    for model in fp16 bonsai; do
        docker logs "study-$SLURM_JOB_ID-$model" > "$WORK/$model-server-$SLURM_JOB_ID.log" 2>&1 || true
    done
    docker ps -aq --filter "label=study.job=$SLURM_JOB_ID" | xargs -r docker rm -f >/dev/null 2>&1 || true
}
trap cleanup EXIT
trap 'exit 143' TERM INT
IFS=',' read -r -a GPUS <<< "${SLURM_JOB_GPUS:-$CUDA_VISIBLE_DEVICES}"
test "${#GPUS[@]}" -eq 2
for i in 0 1; do
    if [ "$i" -eq 0 ]; then NAME=fp16; MODEL=Qwen3.8-27B-F16.gguf; PORT=8231; else NAME=bonsai; MODEL=Ternary-Bonsai-2-27B-PTQ1_0.gguf; PORT=8232; fi
    docker run -d --rm --name "study-$SLURM_JOB_ID-$NAME" --label "study.job=$SLURM_JOB_ID" \
      --network=host --cpus=12 --memory=85g --gpus "device=${GPUS[$i]}" --user "$(id -u):$(id -g)" \
      -e HOME=/tmp -e LD_LIBRARY_PATH=/work/src_p215/build/bin -v "$ROOT:/work:ro" ml_benchmark:latest \
      /work/src_p215/build/bin/llama-server -m "/work/models/$MODEL" \
      -ngl 99 -fa on -c 196608 --parallel 4 --port "$PORT" --seed 1 --reasoning-preserve
done
srun docker run --rm --name "study-$SLURM_JOB_ID-controller" --label "study.job=$SLURM_JOB_ID" \
  --cpus=4 --memory=12g --network=host -e STUDY_JOB_ID="$SLURM_JOB_ID" -e STUDY_SMOKE="${STUDY_SMOKE:-0}" \
  -v "$ROOT:$ROOT" -v /var/run/docker.sock:/var/run/docker.sock -v /usr/bin/docker:/usr/bin/docker:ro \
  ml_benchmark:latest python3 "$WORK/study.py"
if [ "${STUDY_SMOKE:-0}" != 1 ]; then
    srun docker run --rm --name "study-$SLURM_JOB_ID-signals" --label "study.job=$SLURM_JOB_ID" \
      --cpus=4 --memory=16g --network=host -e STUDY_JOB_ID="$SLURM_JOB_ID" \
      -v "$ROOT:$ROOT" ml_benchmark:latest python3 "$WORK/signals.py"
fi
