#!/bin/bash
W=/work; M=$W/models/Ternary-Bonsai-2-27B-PTQ1_0.gguf
FORK=$W/src_stock/build/bin
wait_ready() {
  local LOG=$1 PORT=$2
  for i in $(seq 1 90); do
    curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT/health 2>/dev/null | grep -q 200 && return 0
    sleep 2
  done
  echo "TIMEOUT waiting for port $PORT"; cat $LOG; return 1
}

echo "##### starting real backend server (port 9001)"
LD_LIBRARY_PATH=$FORK $FORK/llama-server -m $M -ngl 99 -fa on -c 4096 --parallel 1 --port 9001 --seed 1 > /tmp/backend.log 2>&1 &
BPID=$!
wait_ready /tmp/backend.log 9001 || exit 1

echo "##### starting proxy (port 9000 -> 9001)"
rm -f /tmp/proxy_test.jsonl
python3 $W/logging_proxy.py 9000 http://127.0.0.1:9001 /tmp/proxy_test.jsonl bonsai-test &
PPID=$!
sleep 2

REQ='{"messages":[{"role":"user","content":"What is 17 times 23? Think briefly, then answer."}],"temperature":0,"seed":1,"max_tokens":150}'
HANDOFF_REQ='{"messages":[{"role":"user","content":"You are about to hand off your work to another AI agent. Please summarize."}],"temperature":0,"seed":1,"max_tokens":50}'

echo "##### request DIRECT to backend"
curl -s http://127.0.0.1:9001/v1/chat/completions -H "Content-Type: application/json" -d "$REQ" > /tmp/direct_resp.json

echo "##### identical request THROUGH proxy"
curl -s http://127.0.0.1:9000/v1/chat/completions -H "Content-Type: application/json" -d "$REQ" > /tmp/proxy_resp.json

echo "##### handoff-signature request THROUGH proxy"
curl -s http://127.0.0.1:9000/v1/chat/completions -H "Content-Type: application/json" -d "$HANDOFF_REQ" > /tmp/proxy_resp2.json

echo "##### comparing direct vs proxied response (should be byte-identical)"
python3 -c "
import json
a=json.load(open('/tmp/direct_resp.json'))
b=json.load(open('/tmp/proxy_resp.json'))
ma=a['choices'][0]['message']; mb=b['choices'][0]['message']
print('content match:', ma.get('content')==mb.get('content'))
print('reasoning match:', ma.get('reasoning_content')==mb.get('reasoning_content'))
print('usage match:', a.get('usage')==b.get('usage'))
"

echo "##### proxy log contents"
cat /tmp/proxy_test.jsonl | python3 -c "
import json,sys
for line in sys.stdin:
    r=json.loads(line)
    print(f\"n_msgs_in={r['n_messages_in']} handoff_sigs={r['handoff_signatures_in_request']} finish={r.get('finish_reason')} reasoning_len={len(r.get('reasoning_content') or '')} content={repr((r.get('content') or '')[:50])}\")
"

echo "##### also test a non-chat path passthrough (e.g. /health)"
curl -s -o /dev/null -w "direct /health: %{http_code}\n" http://127.0.0.1:9001/health
curl -s -o /dev/null -w "proxy  /health: %{http_code}\n" http://127.0.0.1:9000/health

kill $PPID $BPID 2>/dev/null
echo "##### done"
