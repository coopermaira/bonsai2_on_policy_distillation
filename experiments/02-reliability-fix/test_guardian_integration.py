"""Kill/freeze a fake scheduler and verify real descendant processes stop."""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time


def main():
    results=[]
    root=pathlib.Path(__file__).parent
    for mode in ("exit", "stale_heartbeat"):
        with tempfile.TemporaryDirectory(prefix="guardian-fault-") as td:
            td=pathlib.Path(td)
            shutil.copy(root/"guardian.py",td/"guardian.py")
            (td/"supervisor.py").write_text('''import json, pathlib, subprocess, sys, time
run=pathlib.Path(sys.argv[1]); mode=run.name
children=[subprocess.Popen([sys.executable,"-c","import time; time.sleep(90)",str(run)],start_new_session=True) for _ in range(2)]
(run/"status.json").write_text(json.dumps(dict(heartbeat=0 if mode=="stale_heartbeat" else time.time(),lanes=[dict(worker_pid=children[0].pid,proxy_pid=children[1].pid)])))
if mode=="exit": raise SystemExit(1)
time.sleep(90)
''')
            run=td/mode
            proc=subprocess.run([sys.executable,str(td/"guardian.py"),str(run)],capture_output=True,text=True,timeout=40)
            assert proc.returncode==1, proc.stdout+proc.stderr
            status=json.loads((run/"status.json").read_text())
            assert (run/"ALERTS.jsonl").exists()
            for key in ("worker_pid","proxy_pid"):
                pid=status["lanes"][0][key]
                stat=pathlib.Path(f"/proc/{pid}/stat")
                assert not stat.exists() or stat.read_text().split()[2]=="Z", (mode,key,pid)
            results.append(dict(fault=mode,descendants_stopped=True,alert_persisted=True))
    (root/"guardian-validation.json").write_text(json.dumps(results,indent=2))
    print(json.dumps(results,indent=2))


if __name__ == "__main__":
    main()
