"""Independent guard: kill experiment clients if the scheduler dies or freezes."""
import json
import os
import pathlib
import signal
import subprocess
import sys
import time


def terminate_owned(pid, marker):
    try:
        for _ in range(10):
            cmd=pathlib.Path(f"/proc/{pid}/cmdline").read_bytes().decode().replace("\0"," ")
            if cmd:
                break
            time.sleep(.05)  # /proc can briefly be empty while a new child execs.
        if marker not in cmd:
            return
        os.killpg(pid,signal.SIGTERM)
    except (FileNotFoundError, ProcessLookupError):
        pass


def main():
    root=pathlib.Path(__file__).resolve().parent
    run=pathlib.Path(sys.argv[1]).resolve()
    run.mkdir(parents=True,exist_ok=True)
    with (run/"supervisor.log").open("ab") as log:
        child=subprocess.Popen([sys.executable,str(root/"supervisor.py"),str(run),*sys.argv[2:]],
            stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True,
            env=dict(os.environ,RELIABILITY_GUARDIAN_PID=str(os.getpid())))
    (run/"guardian.pid").write_text(str(os.getpid()))
    started=time.time()
    last={}
    while True:
        status=run/"status.json"
        if status.exists():
            last=json.loads(status.read_text())
        heartbeat=last.get("heartbeat",started)
        code=child.poll()
        if code == 0 and last.get("finished"):
            break
        if code is not None or time.time()-heartbeat>120:
            alert=dict(ts=time.time(),event="ALERT",reason="supervisor_exited_or_heartbeat_stale",
                       returncode=code,heartbeat_age=time.time()-heartbeat,
                       action="stop all owned workers and proxies; manual review required")
            with (run/"ALERTS.jsonl").open("a") as f:
                f.write(json.dumps(alert)+"\n")
            print(json.dumps(alert),flush=True)
            terminate_owned(child.pid,"supervisor.py")
            for lane in last.get("lanes",[]):
                for key in ("worker_pid","proxy_pid"):
                    if lane.get(key):
                        terminate_owned(lane[key],run.name)
            # Leave no hung monitored process consuming inference after grace period.
            time.sleep(10)
            for pid in [child.pid]+[l[k] for l in last.get("lanes",[]) for k in ("worker_pid","proxy_pid") if l.get(k)]:
                try:
                    cmd=pathlib.Path(f"/proc/{pid}/cmdline").read_bytes().decode()
                    if run.name in cmd:
                        os.killpg(pid,signal.SIGKILL)
                except (FileNotFoundError,ProcessLookupError):
                    pass
            raise SystemExit(1)
        time.sleep(10)


if __name__ == "__main__":
    main()
