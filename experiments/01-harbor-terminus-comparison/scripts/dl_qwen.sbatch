#!/bin/bash
#SBATCH --job-name=qwen38-dl
#SBATCH --output=/mnt/data/private/cmaira/bonsai_perf/logs/%x_%j.out
#SBATCH --error=/mnt/data/private/cmaira/bonsai_perf/logs/%x_%j.err
#SBATCH --time=02:00:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
srun docker run --rm --network=host --cpus=8 --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v /mnt/data/private/cmaira/bonsai_perf:/work ml_benchmark:latest python3 /work/dl_qwen.py
