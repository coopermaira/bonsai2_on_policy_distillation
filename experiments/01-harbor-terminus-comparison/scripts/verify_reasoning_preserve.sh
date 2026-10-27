#!/bin/bash
W=/work; M=$W/models/Qwen3.8-27B-F16.gguf
FORK=$W/src_stock/build/bin; MAIN=$W/mainline_src/build/bin
wait_ready() { for i in $(seq 1 90); do grep -q "server is listening" $1 2>/dev/null && return 0; sleep 2; done; echo TIMEOUT; cat $1; return 1; }

two_turn_test() {
  local B=$1 PORT=$2 LOG=$3 FLAG=$4
  LD_LIBRARY_PATH=$B $B/llama-server -m $M -ngl 99 -fa on -c 8192 --parallel 1 --port $PORT --seed 1 $FLAG > $LOG 2>&1 &
  local PID=$!
  wait_ready $LOG || { kill $PID 2>/dev/null; return 1; }
  # turn 1
  R1='{"messages":[{"role":"user","content":"What is 17 * 23? Think briefly."}],"temperature":0,"seed":1,"max_tokens":150}'
  curl -s http://127.0.0.1:$PORT/v1/chat/completions -H "Content-Type: application/json" -d "$R1" > /tmp/t1_$PORT.json
  python3 -c "
import json
d=json.load(open('/tmp/t1_$PORT.json'))
m=d['choices'][0]['message']
print('  turn1 prompt_tokens=',d['usage']['prompt_tokens'],'reasoning_len=',len(m.get('reasoning_content') or ''),'content=',repr((m.get('content') or '')[:60]))
"
  # turn 2: continue the conversation, including assistant's turn-1 message with its own reasoning_content field, then ask a follow-up
  python3 -c "
import json
d=json.load(open('/tmp/t1_$PORT.json'))
m=d['choices'][0]['message']
req={'messages':[
    {'role':'user','content':'What is 17 * 23? Think briefly.'},
    {'role':'assistant','content':m.get('content') or '', 'reasoning_content': m.get('reasoning_content') or ''},
    {'role':'user','content':'Now multiply that result by 2. Think briefly.'}
],'temperature':0,'seed':1,'max_tokens':150}
open('/tmp/req2_$PORT.json','w').write(json.dumps(req))
"
  curl -s http://127.0.0.1:$PORT/v1/chat/completions -H "Content-Type: application/json" -d @/tmp/req2_$PORT.json > /tmp/t2_$PORT.json
  python3 -c "
import json
d=json.load(open('/tmp/t2_$PORT.json'))
m=d['choices'][0]['message']
print('  turn2 prompt_tokens=',d['usage']['prompt_tokens'],'reasoning_len=',len(m.get('reasoning_content') or ''),'content=',repr((m.get('content') or '')[:80]))
"
  kill $PID 2>/dev/null; sleep 3
}

echo "##### FORK, explicit --reasoning-preserve"
two_turn_test $FORK 8093 /tmp/fork_pres.log --reasoning-preserve
echo "##### FORK, explicit --no-reasoning-preserve (control)"
two_turn_test $FORK 8094 /tmp/fork_nopres.log --no-reasoning-preserve
echo "##### MAINLINE, explicit --reasoning-preserve"
two_turn_test $MAIN 8095 /tmp/main_pres.log --reasoning-preserve
echo "##### MAINLINE, explicit --no-reasoning-preserve (control)"
two_turn_test $MAIN 8096 /tmp/main_nopres.log --no-reasoning-preserve
echo "##### done"
