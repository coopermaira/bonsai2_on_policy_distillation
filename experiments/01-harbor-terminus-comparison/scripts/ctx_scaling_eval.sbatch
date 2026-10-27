#!/bin/bash
#SBATCH --job-name=ctx-scaling
#SBATCH --output=/mnt/data/private/cmaira/bonsai_perf/logs/%x_%j.out
#SBATCH --error=/mnt/data/private/cmaira/bonsai_perf/logs/%x_%j.err
#SBATCH --time=02:00:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --gres=gpu:1
srun docker run --rm --cpus=16 --gpus "device=${CUDA_VISIBLE_DEVICES}" --ipc=host --user "$(id -u):$(id -g)" -e HOME=/tmp -e CUDA_VISIBLE_DEVICES=0 \
  -v /mnt/data/private/cmaira/bonsai_perf:/work ml_benchmark:latest bash /work/context_scaling_test.sh
