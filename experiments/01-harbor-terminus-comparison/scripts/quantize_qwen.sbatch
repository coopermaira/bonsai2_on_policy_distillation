#!/bin/bash
#SBATCH --job-name=qwen38-quant
#SBATCH --output=/mnt/data/private/cmaira/bonsai_perf/logs/%x_%j.out
#SBATCH --error=/mnt/data/private/cmaira/bonsai_perf/logs/%x_%j.err
#SBATCH --time=01:30:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=150G
#SBATCH --gres=gpu:1
srun docker run --rm --cpus=32 --gpus "device=${CUDA_VISIBLE_DEVICES}" --user "$(id -u):$(id -g)" -e HOME=/tmp -e CUDA_VISIBLE_DEVICES=0 -v /mnt/data/private/cmaira/bonsai_perf:/work ml_benchmark:latest bash -c '
set -e
echo "=== build llama-quantize $(date +%T)"
cmake --build /work/src_stock/build -j 32 --target llama-quantize
Q=/work/src_stock/build/bin/llama-quantize
SRC=/work/models/Qwen3.8-27B-F16.gguf
for t in Q8_0 Q4_0 Q4_K_M; do
  echo "=== quantizing $t $(date +%T)"
  $Q $SRC /work/models/Qwen3.8-27B-$t.gguf $t 32
  echo "=== $t done $(date +%T)"
done
ls -la /work/models/Qwen3.8-27B-*.gguf'
