"""Five real model/Harbor/Docker/tmux/verifier probes, outside benchmark scores."""
import concurrent.futures
import json
import os
import pathlib
import sys
import time

from supervisor import BASE, ROOT, ENDPOINTS, spawn, stop, get_json


def main():
    task=ROOT/"smoke-task"
    (task/"environment").mkdir(parents=True,exist_ok=True)
    (task/"tests").mkdir(exist_ok=True)
    (task/"task.toml").write_text('''schema_version = "1.0"
artifacts = ["/app/reliability_probe.txt"]
[task]
name = "local/reliability-smoke"
[agent]
timeout_sec = 300.0
[verifier]
timeout_sec = 60.0
[environment]
build_timeout_sec = 300.0
cpus = 1
memory_mb = 1024
storage_mb = 1024
gpus = 0
''')
    (task/"instruction.md").write_text("Write exactly ready followed by a newline into /app/reliability_probe.txt. Read the file to check it, then finish.\n")
    (task/"environment/Dockerfile").write_text("FROM ubuntu:24.04\nRUN apt-get update && apt-get install -y tmux python3 && rm -rf /var/lib/apt/lists/*\nWORKDIR /app\n")
    (task/"tests/test.sh").write_text('#!/bin/bash\nmkdir -p /logs/verifier\nif test "$(cat /app/reliability_probe.txt)" = ready; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi\n')
    run=ROOT/("smoke-"+time.strftime("%Y%m%d-%H%M%S",time.gmtime()))
    run.mkdir()
    def lane(endpoint):
        label,_,backend,port,_=endpoint
        port+=100
        proxy=spawn([sys.executable,str(ROOT/"reliable_proxy.py"),str(port),f"http://127.0.0.1:{backend}",str(run/(label+".jsonl")),label],run/(label+"-proxy.log"))
        worker=None
        try:
            for _ in range(30):
                try:
                    get_json(port,"/proxy-health")
                    break
                except Exception:
                    time.sleep(.2)
            job=run.name+"-"+label
            args=[str(pathlib.Path.home()/".local/bin/harbor"),"run","-a","reliable_terminus:ReliableTerminus",
                  "-m","openai/"+label,"--ak",f"api_base=http://127.0.0.1:{port}/v1",
                  "--ak",'llm_kwargs={"api_key":"not-needed-local-server"}',
                  "--ak",'llm_call_kwargs={"max_tokens":2048,"extra_body":{"chat_template_kwargs":{"enable_thinking":false}}}',
                  "--ak","session_id="+job,"--ak","store_all_messages=true",
                  "--yes","-n","1","-p",str(task),"--job-name",job,"--jobs-dir",str(run/"jobs")]
            worker=spawn(args,run/(label+"-harbor.log"),dict(os.environ,PYTHONPATH=str(ROOT)))
            code=worker.wait(timeout=450)
            results=[json.loads(p.read_text()) for p in (run/"jobs"/job).glob("*/result.json")]
            assert code == 0 and len(results)==1, (label,code,results)
            r=results[0]
            assert not r.get("exception_info"), (label,r.get("exception_info"))
            assert r["verifier_result"]["rewards"]["reward"]==1, (label,r["verifier_result"])
            return dict(label=label,passed=True,result=str(run/"jobs"/job/"result.json"))
        finally:
            stop(worker)
            stop(proxy)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results=list(pool.map(lane,ENDPOINTS))
    (ROOT/"smoke-validation.json").write_text(json.dumps(results,indent=2))
    print(json.dumps(results,indent=2),flush=True)


if __name__ == "__main__":
    main()
