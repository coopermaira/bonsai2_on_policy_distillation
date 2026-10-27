"""One-time controller handoff; existing workers/proxies are never signalled."""
import json
import os
import pathlib
import signal
import subprocess
import sys
import time

from supervisor import atomic, get_json, process_identity, restore_lanes


def main():
    root=pathlib.Path(__file__).resolve().parent
    run=pathlib.Path((root/"CURRENT_RUN").read_text().strip())
    smoke=json.loads((root/"bonsai3-smoke-validation.json").read_text())
    assert len(smoke)==1 and smoke[0]["passed"]
    (root/"smoke-validation.json").write_bytes((root/"original-smoke-validation.json").read_bytes())
    assert get_json(8106,"/health")["status"]=="ok"
    assert not any(s["is_processing"] for s in get_json(8106,"/slots"))
    saved=json.loads((run/"status.json").read_text())
    guardian=int((run/"guardian.pid").read_text())
    supervisor=saved["supervisor_pid"]
    assert time.time()-saved["heartbeat"]<45
    for pid,marker in [(guardian,"guardian.py"),(supervisor,"supervisor.py")]:
        cmd=pathlib.Path(f"/proc/{pid}/cmdline").read_bytes().decode()
        assert marker in cmd and run.name in cmd
    paused=[]
    committed=False
    try:
        for pid in [guardian,supervisor]:
            os.kill(pid,signal.SIGSTOP)
            paused.append(pid)
        saved=json.loads((run/"status.json").read_text())
        assert "mvcc-lsm-compaction" in saved["queue"]["bonsai"]
        lanes=restore_lanes(run,saved)
        known={p.pid for l in lanes for p in [l["proxy"],l.get("worker")] if p}
        children=pathlib.Path(f"/proc/{supervisor}/task/{supervisor}/children").read_text().split()
        unexpected=[int(p) for p in children if int(p) not in known
                    and process_identity(int(p)) and process_identity(int(p))[0]!="Z"]
        assert not unexpected, f"Unrecorded live children: {unexpected}"
        for lane in lanes:
            assert not lane.get("quarantined")
            assert get_json(lane["port"],"/proxy-health")["status"]=="ok"
        identities={str(p):process_identity(p) for p in known}
        atomic(run/"handoff-before-bonsai3.json",dict(ts=time.time(),status=saved,
              process_identities=identities,old_guardian=guardian,old_supervisor=supervisor))
        atomic(run/"add-endpoints.json",[dict(endpoint=["bonsai3","bonsai",8106,9106,2],task="mvcc-lsm-compaction")])
        # These controllers own separate process groups. SIGKILL prevents the old
        # supervisor's finally block from terminating the adopted live children.
        os.kill(supervisor,signal.SIGKILL)
        os.kill(guardian,signal.SIGKILL)
        committed=True
        for _ in range(100):
            identity=process_identity(supervisor)
            if identity is None or identity[0]=="Z":break
            time.sleep(.05)
        with (run/"guardian.log").open("ab") as log:
            new=subprocess.Popen([sys.executable,str(root/"guardian.py"),str(run),"--resume"],
                stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True,cwd=root)
        print("NEW_GUARDIAN",new.pid,flush=True)
        for _ in range(40):
            time.sleep(.5)
            current=json.loads((run/"status.json").read_text())
            if current["supervisor_pid"]!=supervisor and len(current["lanes"])==6:
                for pid,before in identities.items():
                    after=process_identity(int(pid))
                    assert after is not None and after[1]==before[1], f"Worker identity changed: {pid}"
                atomic(run/"handoff-after-bonsai3.json",dict(ts=time.time(),status=current,
                      existing_processes_preserved=True,new_guardian=new.pid))
                print("HANDOFF_OK existing worker/proxy processes preserved",flush=True)
                return
        raise RuntimeError("New controller not ready; guardian owns fail-closed cleanup")
    finally:
        if not committed:
            for pid in reversed(paused):
                os.kill(pid,signal.SIGCONT)


if __name__=="__main__":
    main()
