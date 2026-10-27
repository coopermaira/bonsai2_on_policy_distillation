#!/bin/bash
#SBATCH --job-name=serve-bonsai
#SBATCH --output=/mnt/data/private/cmaira/bonsai_perf/logs/%x_%j.out
#SBATCH --error=/mnt/data/private/cmaira/bonsai_perf/logs/%x_%j.err
#SBATCH --time=24:00:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --gres=gpu:1
srun docker run --rm --network=host --cpus=16 --gpus '"device=2"' --user "$(id -u):$(id -g)" -e HOME=/tmp -e CUDA_VISIBLE_DEVICES=0 -e NVIDIA_VISIBLE_DEVICES=2 \
  -v /mnt/data/private/cmaira/bonsai_perf:/work ml_benchmark:latest bash -c '
set -e
B=/work/src_p215/build/bin
M=/work/models/Ternary-Bonsai-2-27B-PTQ1_0.gguf
echo "assigned CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES"; nvidia-smi -L
echo "backend: $B  model: $M"
LD_LIBRARY_PATH=$B $B/llama-server -m $M -ngl 99 -fa on -c 262144 --parallel 1 --port 8103 --seed 1 --reasoning-preserve > /tmp/backend_bonsai.log 2>&1 &
BPID=$!
echo "waiting for backend on :8103"
for i in $(seq 1 180); do
  curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8103/health 2>/dev/null | grep -q 200 && break
  sleep 3
done
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8103/health 2>/dev/null | grep -q 200 || { echo BACKEND_FAILED; cat /tmp/backend_bonsai.log; exit 1; }
echo "backend ready, starting proxy on :9103 -> :8103"
python3 /work/logging_proxy.py 9103 http://127.0.0.1:8103 /work/logs_reasoning/bonsai.jsonl bonsai > /tmp/proxy_bonsai.log 2>&1 &
PXPID=$!
echo "READY bonsai backend=:8103 proxy=:9103"
wait $BPID $PXPID
'
