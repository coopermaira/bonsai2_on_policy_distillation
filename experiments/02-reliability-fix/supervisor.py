"""Durable scheduler and watchdog. No automatic trial retries.

Start through guardian.py after validate.py and validate.py --long pass.
Every event and decision is persisted; aborted/errored trials remain unscored.
"""
import fcntl
import hashlib
import json
import os
import pathlib
import signal
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
BASE = ROOT.parent
TASKS = ["session-window-debug", "react-lead-form", "mvcc-lsm-compaction",
         "interleaved-vigenere", "music-harmony"]
ENDPOINTS = [("qwen-a", "qwen", 8101, 9101, 0), ("qwen-b", "qwen", 8102, 9102, 1),
             ("qwen-c", "qwen", 8104, 9104, 3), ("bonsai", "bonsai", 8103, 9103, 2),
             ("bonsai2", "bonsai", 8105, 9105, 2)]


def atomic(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2))
    temp.replace(path)


def get_json(port, route):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{route}", timeout=3) as r:
        return json.load(r)


class Progress:
    """Pure watchdog state machine, independently fault-injected in tests."""
    def __init__(self, now):
        self.pending = {}
        self.seen = set()
        self.last_signature = None
        self.last_progress = now
        self.health_failures = 0
        self.orphan_since = None

    def event(self, row):
        kind = row["event"]
        rid = row.get("request_id")
        if kind == "request_started":
            key = (row.get("session_id"), row["request_sha256"])
            if key in self.seen:
                return "duplicate_request_in_same_session"
            if self.pending:
                return "overlapping_requests"
            self.seen.add(key)
            self.pending[rid] = row
            self.last_progress = row["ts"]
            self.last_signature = None
        elif kind in ("response_sent", "client_cancelled", "proxy_error"):
            self.pending.pop(rid, None)
        if kind in ("rejected_overlap", "proxy_error"):
            return kind
        if kind == "backend_completed" and row.get("status", 200) != 200:
            return "backend_http_error_"+str(row["status"])
        return None

    def poll(self, now, slots, healthy=True):
        if not healthy:
            self.health_failures += 1
            return "three_failed_health_checks" if self.health_failures >= 3 else None
        self.health_failures = 0
        busy = [s for s in slots if s.get("is_processing")]
        if self.pending:
            self.orphan_since = None
            signature = [(s.get("id_task"), s.get("n_prompt_tokens_processed"),
                          [t.get("n_decoded") for t in s.get("next_token", [])]) for s in busy]
            if signature != self.last_signature:
                self.last_signature = signature
                self.last_progress = now
            if now-self.last_progress > 180:
                return "no_backend_token_progress_180s" if busy else "request_without_backend_work_180s"
        elif busy:
            self.orphan_since = self.orphan_since or now
            if now-self.orphan_since > 60:
                return "orphan_backend_generation_60s"
        else:
            self.orphan_since = None
        return None


def spawn(argv, logfile, env=None):
    with logfile.open("ab") as out:
        return subprocess.Popen(argv, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                start_new_session=True, env=env, cwd=BASE)


def stop(process):
    if process and process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)


def process_identity(pid):
    """Return state and start ticks; protect adopted handles against PID reuse."""
    try:
        fields = pathlib.Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return fields[0], fields[19]
    except FileNotFoundError:
        return None


class AdoptedProcess:
    """Popen-like handle for a worker left running across a controller handoff.

    Exit status is unavailable for a nonchild; Harbor's final result and exception
    checks remain authoritative, and missing results still quarantine the lane.
    """
    def __init__(self, pid, marker):
        self.pid = pid
        self.returncode = None
        self.identity = process_identity(pid)
        if self.identity and self.identity[0] != "Z":
            cmd = pathlib.Path(f"/proc/{pid}/cmdline").read_bytes().decode()
            if marker not in cmd:
                raise RuntimeError(f"Refusing to adopt unrelated PID {pid}")

    def poll(self):
        current = process_identity(self.pid)
        if (not current or current[0] == "Z" or not self.identity
                or current[1] != self.identity[1]):
            self.returncode = 0
        return self.returncode

    def wait(self, timeout):
        deadline = time.monotonic()+timeout
        while self.poll() is None:
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(str(self.pid), timeout)
            time.sleep(.1)
        return self.returncode


def restore_lanes(run, saved):
    endpoints = {e[0]:e for e in ENDPOINTS}
    manifest = json.loads((run/"manifest.json").read_text())
    for e in manifest.get("endpoints", []):
        endpoints[e[0]]=e
    starts = {}
    for line in (run/"events.jsonl").read_text().splitlines():
        row = json.loads(line)
        if row["event"] == "trial_started":
            starts[row["job"]] = row["ts"]
    lanes=[]
    for old in saved["lanes"]:
        label,model,backend,port,gpu=endpoints[old["label"]]
        progress=Progress(time.time())
        log=run/(label+".jsonl")
        offset=0
        if log.exists():
            with log.open() as f:
                while True:
                    before=f.tell()
                    line=f.readline()
                    if not line or not line.endswith("\n"):
                        offset=before
                        break
                    reason=progress.event(json.loads(line))
                    if reason and not old.get("quarantined"):
                        raise RuntimeError(f"Unsafe request history on {label}: {reason}")
        progress.last_progress=time.time()
        worker=AdoptedProcess(old["worker_pid"], run.name) if old.get("worker_pid") else None
        lanes.append(dict(label=label,model=model,backend=backend,port=port,gpu=gpu,
            proxy=AdoptedProcess(old["proxy_pid"],run.name),worker=worker,
            log=log,offset=offset,progress=progress,job=old.get("job"),task=old.get("task"),
            started=starts.get(old.get("job"),time.time()),stage=old.get("stage"),
            quarantined=old.get("quarantined"),preferred_task=old.get("preferred_task")))
    return lanes


def main():
    run = pathlib.Path(sys.argv[1]).resolve()
    run.mkdir(parents=True, exist_ok=True)
    lock = (ROOT/"supervisor.lock").open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    for name in ("validation.json", "validation-long.json", "watchdog-validation.json",
                 "smoke-validation.json", "guardian-validation.json"):
        if not (ROOT/name).is_file():
            raise RuntimeError("Missing validation gate: "+name)
    long = json.loads((ROOT/"validation-long.json").read_text())
    assert any(x.get("elapsed", 0)>600 and x.get("next_turn_advanced") for x in long)
    resume = "--resume" in sys.argv[2:]
    saved = json.loads((run/"status.json").read_text()) if resume else None
    if saved and saved.get("finished"):
        raise RuntimeError("Cannot adopt a finished run")
    queue = saved["queue"] if saved else {m:list(TASKS) for m in ("qwen", "bonsai")}
    manifest = dict(created=time.time(), tasks=TASKS, endpoints=ENDPOINTS,
                    harness="harbor 0.23.0 + experiment-local ReliableTerminus",
                    source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob("*.py")},
                    transport_timeout_s=86400, automatic_retries=0,
                    task_deadline_s=28800, polling_interval_s=15,
                    parse_failure_limit=10, invalid_trials="preserve separately, never count as reward zero")
    if not resume:
        atomic(run/"manifest.json", manifest)
    lanes=restore_lanes(run,saved) if saved else []
    results=saved["results"] if saved else []
    def emit(kind, **fields):
        row=dict(ts=time.time(), event=kind, **fields)
        with (run/"events.jsonl").open("a") as f:
            f.write(json.dumps(row)+"\n")
        if kind == "ALERT":
            with (run/"ALERTS.jsonl").open("a") as f:
                f.write(json.dumps(row)+"\n")
        print(json.dumps(row),flush=True)

    def quarantine(lane, reason):
        if lane.get("quarantined"):
            return
        lane["quarantined"] = reason
        emit("ALERT", label=lane["label"], job=lane.get("job"), reason=reason,
             action="stop trial and proxy; quarantine endpoint; preserve all artifacts")
        stop(lane.get("worker"))
        stop(lane["proxy"])
        # Harbor owns sandbox teardown on SIGTERM. Record any interrupted result,
        # and leave its files intact even when cleanup itself fails.
        if lane.get("job"):
            results.append(dict(job=lane["job"], model=lane["model"], task=lane["task"],
                                outcome="quarantined", reason=reason))
        lane["worker"]=None

    def snapshot(finished=False):
        atomic(run/"status.json",dict(heartbeat=time.time(), supervisor_pid=os.getpid(),
            finished=finished, queue=queue, results=results,
            lanes=[dict(label=l["label"],model=l["model"],gpu=l["gpu"],
                        proxy_pid=l["proxy"].pid, worker_pid=l["worker"].pid if l.get("worker") else None,
                        job=l.get("job"),task=l.get("task"),quarantined=l.get("quarantined"),
                        preferred_task=l.get("preferred_task"),
                        active_requests=len(l["progress"].pending), last_progress=l["progress"].last_progress,
                        stage=l.get("stage"),decoded_tokens=l.get("decoded_tokens")) for l in lanes]))

    try:
        additions = []
        if resume and (run/"add-endpoints.json").exists():
            additions=json.loads((run/"add-endpoints.json").read_text())
        endpoints = [a["endpoint"] for a in additions] if resume else ENDPOINTS
        for label, model, backend, proxy, gpu in endpoints:
            if any(l["label"] == label for l in lanes):
                continue
            assert get_json(backend,"/health")["status"] == "ok"
            assert not any(s["is_processing"] for s in get_json(backend,"/slots"))
            log=run/(label+".jsonl")
            process=spawn([sys.executable,str(ROOT/"reliable_proxy.py"),str(proxy),
                           f"http://127.0.0.1:{backend}",str(log),label],run/(label+"-proxy.log"))
            lanes.append(dict(label=label,model=model,backend=backend,port=proxy,gpu=gpu,
                              proxy=process,log=log,offset=0,progress=Progress(time.time()),worker=None))
            if resume:
                task=next(a["task"] for a in additions if a["endpoint"][0] == label)
                if task not in queue[model]:
                    raise RuntimeError(f"Task {task} is no longer pending")
                queue[model].remove(task)
                lanes[-1]["preferred_task"]=task
                emit("endpoint_added",label=label,gpu=gpu,priority_task=task)
            snapshot()
        time.sleep(2)
        for lane in lanes:
            if not lane.get("quarantined"):
                assert get_json(lane["port"],"/proxy-health")["status"] == "ok"
        if resume:
            updated=json.loads((run/"manifest.json").read_text())
            updated["endpoints"]=[[l["label"],l["model"],l["backend"],l["port"],l["gpu"]] for l in lanes]
            updated.setdefault("amendments",[]).append(dict(ts=time.time(),reason="User requested third Bonsai endpoint and prioritized MVCC",
                controller_handoff=True,source_sha256=manifest["source_sha256"]))
            atomic(run/"manifest.json",updated)
            emit("controller_adopted",workers=[l["worker"].pid for l in lanes if l.get("worker")])
        while True:
            if os.environ.get("RELIABILITY_GUARDIAN_PID"):
                os.kill(int(os.environ["RELIABILITY_GUARDIAN_PID"]), 0)
            snapshot()
            now=time.time()
            for lane in lanes:
                if lane.get("quarantined"):
                    continue
                if lane["proxy"].poll() is not None:
                    quarantine(lane,"proxy_process_exited")
                    continue
                if lane["log"].exists():
                    with lane["log"].open() as f:
                        f.seek(lane["offset"])
                        while True:
                            before=f.tell()
                            line=f.readline()
                            if not line or not line.endswith("\n"):
                                f.seek(before)
                                break
                            reason=lane["progress"].event(json.loads(line))
                            if reason:
                                quarantine(lane,reason)
                        lane["offset"]=f.tell()
                if lane.get("quarantined"):
                    continue
                try:
                    slots=get_json(lane["backend"],"/slots")
                    get_json(lane["port"],"/proxy-health")
                    reason=lane["progress"].poll(now,slots)
                    lane["decoded_tokens"]=sum(t.get("n_decoded",0) for s in slots for t in s.get("next_token",[]))
                except Exception:
                    reason=lane["progress"].poll(now,[],healthy=False)
                if reason:
                    quarantine(lane,reason)
                    continue
                worker=lane.get("worker")
                if worker and worker.poll() is not None:
                    job=BASE/"harbor_jobs"/lane["job"]
                    path=job/"result.json"
                    data=json.loads(path.read_text()) if path.exists() else {}
                    stats=data.get("stats",{})
                    if worker.returncode or stats.get("n_errored_trials",0) or not data.get("finished_at"):
                        quarantine(lane,"trial_exit_error_or_missing_result")
                        continue
                    trial_results=[json.loads(p.read_text()) for p in job.glob("*/result.json")]
                    results.append(dict(job=lane["job"],model=lane["model"],task=lane["task"],outcome="completed",
                        verifier_results=[r.get("verifier_result") for r in trial_results]))
                    emit("trial_completed",label=lane["label"],job=lane["job"])
                    lane["worker"]=None
                if lane.get("worker"):
                    activity=list((BASE/"harbor_jobs"/lane["job"]).glob("*/agent/reliability-status.json"))
                    if activity:
                        a=json.loads(activity[0].read_text())
                        lane["stage"]=a["stage"]
                        # Terminal batches have an explicit upper bound; verifier/build phases
                        # remain under Harbor's own deadlines, plus the outer 9h watchdog.
                        if a["stage"] == "executing_commands" and now>a["deadline"]:
                            quarantine(lane,"terminal_command_batch_exceeded_deadline")
                        elif (a["stage"] in ("llm_returned","parsed","commands_finished","waiting_for_llm")
                              and not lane["progress"].pending and now-a["ts"]>180):
                            quarantine(lane,"response_delivered_but_agent_not_advancing_180s")
                    elif now-lane["started"]>1800:
                        quarantine(lane,"agent_setup_no_activity_1800s")
                    if now-lane["started"]>32400:
                        quarantine(lane,"trial_exceeded_9h_outer_deadline")
                if (not lane.get("worker") and not lane.get("quarantined")
                        and (lane.get("preferred_task") or queue[lane["model"]])):
                    if lane["progress"].pending:
                        continue
                    task=lane.pop("preferred_task",None) or queue[lane["model"]].pop(0)
                    job=f"{run.name}-{lane['label']}-{task}"
                    args=[str(pathlib.Path.home()/".local/bin/harbor"),"run","-a","reliable_terminus:ReliableTerminus",
                          "-m","openai/"+lane["label"],"--ak",f"api_base=http://127.0.0.1:{lane['port']}/v1",
                          "--ak",'llm_kwargs={"api_key":"not-needed-local-server"}',
                          "--ak",'model_info={"max_input_tokens":262144,"input_cost_per_token":0,"output_cost_per_token":0}',
                          "--ak","interleaved_thinking=false","--ak","store_all_messages=true",
                          "--ak","enable_summarize=true","--ak","session_id="+job,
                          "--yes","-n","1","--max-retries","0","-p",str(BASE/"terminal-bench-tasks/tasks"/task),
                          "--job-name",job,"--jobs-dir",str(BASE/"harbor_jobs")]
                    env=dict(os.environ,PYTHONPATH=str(ROOT),OPENAI_API_KEY="not-needed-local-server")
                    lane.update(worker=spawn(args,run/(lane["label"]+"-harbor.log"),env),
                                job=job,task=task,started=time.time(),stage="starting")
                    emit("trial_started",label=lane["label"],job=job,pid=lane["worker"].pid)
                    snapshot()
            snapshot()
            if not any(l.get("worker") for l in lanes):
                if not any(queue[l["model"]] for l in lanes if not l.get("quarantined")):
                    break
            time.sleep(15)
        emit("run_finished",completed=len(results),remaining=queue)
        snapshot(finished=True)
    finally:
        for lane in lanes:
            stop(lane.get("worker"))
            stop(lane["proxy"])


if __name__ == "__main__":
    main()
