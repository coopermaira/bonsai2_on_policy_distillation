#!/bin/bash
#SBATCH --job-name=bonsai-score-build
#SBATCH --time=00:10:00
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --output=/mnt/data/private/cmaira/bonsai_perf/recovery-study-20261003/compile-%j.log
set -euo pipefail
ROOT=/mnt/data/private/cmaira/bonsai_perf
srun docker run --rm --cpus=2 --memory=6g -v "$ROOT:$ROOT" -e LD_LIBRARY_PATH="$ROOT/src_p215/build/bin" \
  ml_benchmark:latest bash -c 'set -euo pipefail
    ROOT=/mnt/data/private/cmaira/bonsai_perf
    WORK=$ROOT/recovery-study-20261003
    g++ -O2 -std=c++17 "$WORK/dense_score.cpp" -I"$ROOT/src_p215/include" -I"$ROOT/src_p215/ggml/include" \
      -L"$ROOT/src_p215/build/bin" -lllama -lggml -lggml-base -Wl,--allow-shlib-undefined -o "$WORK/dense_score"
    test -x "$WORK/dense_score"
  '
