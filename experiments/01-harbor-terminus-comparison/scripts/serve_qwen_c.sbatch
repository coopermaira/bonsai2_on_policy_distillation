#!/bin/bash
#SBATCH --job-name=serve-qwen_c
#SBATCH --output=/mnt/data/private/cmaira/bonsai_perf/logs/%x_%j.out
#SBATCH --error=/mnt/data/private/cmaira/bonsai_perf/logs/%x_%j.err
#SBATCH --time=24:00:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=32G
#SBATCH --gres=gpu:1
srun docker run --rm --network=host --cpus=16 --gpus '"device=3"' --user "$(id -u):$(id -g)" -e HOME=/tmp -e CUDA_VISIBLE_DEVICES=0 -e NVIDIA_VISIBLE_DEVICES=3 \
  -v /mnt/data/private/cmaira/bonsai_perf:/work ml_benchmark:latest bash -c '
set -e
B=/work/mainline_src/build/bin
M=/work/models/Qwen3.8-27B-F16.gguf
echo "assigned CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES"; nvidia-smi -L
echo "backend: $B  model: $M"
LD_LIBRARY_PATH=$B $B/llama-server -m $M -ngl 99 -fa on -c 262144 --parallel 1 --port 8104 --seed 1 --reasoning-preserve > /tmp/backend_qwen_c.log 2>&1 &
BPID=$!
echo "waiting for backend on :8104"
for i in $(seq 1 180); do
  curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8104/health 2>/dev/null | grep -q 200 && break
  sleep 3
done
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8104/health 2>/dev/null | grep -q 200 || { echo BACKEND_FAILED; cat /tmp/backend_qwen_c.log; exit 1; }
echo "backend ready, starting proxy on :9104 -> :8104"
python3 /work/logging_proxy.py 9104 http://127.0.0.1:8104 /work/logs_reasoning/qwen-c.jsonl qwen-c > /tmp/proxy_qwen_c.log 2>&1 &
PXPID=$!
echo "READY qwen-c backend=:8104 proxy=:9104"
wait $BPID $PXPID
'
