#!/bin/bash
#SBATCH --job-name=qwen38-convert
#SBATCH --output=/mnt/data/private/cmaira/bonsai_perf/logs/%x_%j.out
#SBATCH --error=/mnt/data/private/cmaira/bonsai_perf/logs/%x_%j.err
#SBATCH --time=02:00:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=200G
srun docker run --rm --cpus=32 --user "$(id -u):$(id -g)" -e HOME=/tmp -v /mnt/data/private/cmaira/bonsai_perf:/work ml_benchmark:latest bash -c '
set -e
echo "== container torch check"
python3 -c "import torch; print(torch.__version__)"
echo "== installing conversion deps WITHOUT touching torch (container CUDA torch works fine for CPU-side conversion)"
pip install -q --user "sentencepiece>=0.1.98,<0.3.0" "transformers==4.57.6" "protobuf>=4.21.0,<5.0.0" "numpy~=1.26.4" 2>&1 | tail -15
python3 -c "import torch; print(\"torch still ok:\", torch.__version__)"
echo "=== converting $(date +%T)"
python3 /work/src_stock/convert_hf_to_gguf.py /work/qwen38-27b-src \
  --outfile /work/models/Qwen3.8-27B-F16.gguf --outtype f16
echo "=== done $(date +%T)"
ls -la /work/models/Qwen3.8-27B-F16.gguf'
