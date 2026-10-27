#!/bin/bash
#SBATCH --job-name=bonsai-dense-score
#SBATCH --time=01:00:00
#SBATCH --signal=B:TERM@60
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=12
#SBATCH --mem=150G
#SBATCH --gres=gpu:1
#SBATCH --output=/mnt/data/private/cmaira/bonsai_perf/recovery-study-20261003/dense-%j.log
set -euo pipefail
ROOT=/mnt/data/private/cmaira/bonsai_perf
WORK=$ROOT/recovery-study-20261003
cleanup() { docker rm -f "dense-$SLURM_JOB_ID" >/dev/null 2>&1 || true; }
trap cleanup EXIT
trap 'exit 143' TERM INT
srun docker run --rm --name "dense-$SLURM_JOB_ID" --cpus=12 --memory=140g \
  --gpus "device=${SLURM_JOB_GPUS:-$CUDA_VISIBLE_DEVICES}" -v "$ROOT:$ROOT" -e LD_LIBRARY_PATH="$ROOT/src_p215/build/bin" \
  ml_benchmark:latest bash -c 'set -euo pipefail
    ROOT=/mnt/data/private/cmaira/bonsai_perf
    WORK=$ROOT/recovery-study-20261003
    g++ -O2 -std=c++17 "$WORK/dense_score.cpp" -I"$ROOT/src_p215/include" -I"$ROOT/src_p215/ggml/include" \
      -L"$ROOT/src_p215/build/bin" -lllama -lggml -lggml-base -Wl,--allow-shlib-undefined -o "$WORK/dense_score"
    "$WORK/dense_score" "$ROOT/models/Qwen3.8-27B-F16.gguf" "$ROOT/models/Ternary-Bonsai-2-27B-PTQ1_0.gguf" \
      "$WORK/dense-cases.tokens" > "$WORK/dense-scores.jsonl"
    python3 "$WORK/summarize_dense.py"
  '
