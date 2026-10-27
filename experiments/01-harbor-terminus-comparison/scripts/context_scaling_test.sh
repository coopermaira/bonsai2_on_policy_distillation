#!/bin/bash
W=/work; FORK=$W/src_stock/build/bin
QW=$W/models/Qwen3.8-27B-F16.gguf
PT=$W/models/Ternary-Bonsai-2-27B-PTQ1_0.gguf
wait_ready() { for i in $(seq 1 120); do curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$2/health 2>/dev/null | grep -q 200 && return 0; sleep 2; done; return 1; }

test_ctx() {
  local B=$1 M=$2 CTX=$3 PORT=$4 LABEL=$5
  LD_LIBRARY_PATH=$B $B/llama-server -m $M -ngl 99 -fa on -c $CTX --parallel 1 --port $PORT --seed 1 > /tmp/ctxtest_${LABEL}_${CTX}.log 2>&1 &
  local PID=$!
  if wait_ready /tmp/ctxtest_${LABEL}_${CTX}.log $PORT; then
    USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits)
    echo "$LABEL ctx=$CTX -> VRAM used: ${USED} MiB"
  else
    echo "$LABEL ctx=$CTX -> FAILED TO START"
    tail -20 /tmp/ctxtest_${LABEL}_${CTX}.log
  fi
  kill $PID 2>/dev/null; wait $PID 2>/dev/null; sleep 3
}

echo "##### Qwen FP16: VRAM at increasing context sizes"
for CTX in 8192 32768 131072 262144; do
  test_ctx $FORK $QW $CTX 8097 qwen
done

echo "##### Bonsai2 PTQ1_0: same test"
for CTX in 8192 131072 262144; do
  test_ctx $FORK $PT $CTX 8098 bonsai
done
echo "##### done"
