# Voodoo agentic comparison: confirmed timeout failure and monitored restart

2026-09-29. This supersedes the parser-size hypothesis in the earlier session report.

## Confirmed cause

Harbor 0.23.0's OpenAI-compatible client timed out after **600 seconds** while
llama-server was still generating a nonstreaming response. The old synchronous
logging proxy continued waiting on the backend after its downstream client left.
Retries therefore accumulated behind abandoned requests on each single-slot server.
Stopping and replacing the Harbor process did not clear the proxy's queued work.

Evidence from voodoo, captured in `reliability/incident_evidence.json`:

- Qwen-a's failing job log explicitly records `litellm.Timeout`, `timeout value=600.0`,
  and `time taken=1801.42 seconds`.
- Reconstructed request start times (`ts - latency_s`) for a repeated Qwen-a turn:
  1790655958.40, 1790656558.87, 1790657159.80, 1790657763.81. Starts are approximately
  600 seconds apart. Completed requests take approximately 1,000 seconds of generation
  plus increasing queue time: 1,000.945, 1,403.741, 1,810.236, 2,215.735 seconds.
- Qwen-b shows the same pattern; Qwen-c also began retrying a 631-second generation.
- The installed OpenAI SDK exposes a 600-second default read timeout. LiteLLM's
  separate global timeout is 6,000 seconds, so relying on that global alone was unsafe.
- Harbor has two nested three-attempt retry decorators. Injecting a transport timeout
  into the actual installed Harbor stack produces **nine completion calls**. Provider
  SDK retries are additional to these decorators.

The original logs recorded counts and completions, not request bodies. Consequently,
their repeated counts alone do not prove byte-identical requests. The timeout message,
600-second reconstructed start intervals, source inspection, and regression tests
establish the transport retry failure. New logs record actual request hashes and bodies.

Harbor's normal parse-error path appends feedback and changes the conversation. A
27,396-token archived completion parses successfully in the installed JSON parser.
There is no evidence of a generic 18K–33K completion-size parser limit here.

## Changes

Source is in [harbor-reliability](harbor-reliability/). The matching remote directory
is `/mnt/data/private/cmaira/bonsai_perf/reliability/`.

- `reliable_terminus.py`: experiment-local subclass; explicitly sets transport timeout
  to 86,400 seconds and SDK/LiteLLM retry counts to zero, bypasses Harbor's two transport
  retry decorators, preserves upstream context/output recovery and agent behavior.
  All tasks retain their existing 28,800-second agent deadline. The task descriptions'
  1/2/4/5/8-hour figures are **expert estimates**, not agent timeouts.
- `reliable_proxy.py`: asynchronous, cancellation-aware proxy. Disconnecting a client
  closes its upstream request. It rejects overlapping generations on a single endpoint,
  emits one Content-Length header, and preserves request/response bytes. It logs request
  start, backend completion, downstream write completion, cancellation, and errors.
  Raw requests and full responses, including reasoning, are stored separately by ID.
  A successful downstream write is logged; the adapter's next stage supplies evidence
  that Harbor actually consumed it.
- Context metadata is explicitly 262,144 tokens, correcting Harbor's unknown-model
  fallback of 1,000,000. No new generation-token cap or sampling change is imposed
  on benchmark trials. Actual servers report temperature 1.0 and seed 1, contrary to
  the earlier report's assumption of temperature zero.
- Ten consecutive unparseable responses raise `ModelNonProgressError`, resetting on
  a valid parse. This is recorded separately as an interrupted diagnostic outcome,
  not silently counted as a model reward of zero.

Old trials were stopped with artifacts preserved. Terminating the old proxies cleared
their abandoned requests; all four GPUs returned to 0% use before validation/restart.
The installed Harbor package and old proxy source remain unchanged.

## Failure detection and response

`supervisor.py` runs on voodoo independently of this chat. Every 15 seconds it checks
proxy events, backend `/slots` counters, worker processes, and adapter stage telemetry.

| Failure | Detection / action |
|---|---|
| Repeated request hash within the same session | Next poll; quarantine endpoint |
| Overlapping requests | Proxy immediately rejects; supervisor quarantines |
| No generation/prefill counter progress | 180 seconds plus polling interval; quarantine |
| Request pending but backend not processing | 180 seconds plus polling interval |
| Backend working without a tracked request | 60 seconds plus polling interval |
| Proxy/backend health failure | Three consecutive failed checks |
| Proxy process exits | Next poll |
| Worker exits with errors or without a final result | Next poll; preserve and classify separately |
| Response consumed but next agent stage stalls | 180 seconds when no request is active |
| Terminal batch exceeds expected bound | 180 seconds per command plus 120 seconds |
| Agent never starts | 1,800 seconds |
| Trial exceeds outer deadline | Nine hours, including setup/verifier |
| Supervisor dies/freezes | Independent `guardian.py`; stale heartbeat threshold 120 seconds |

Quarantine stops the trial and proxy, persists a reason in `ALERTS.jsonl`, and leaves
healthy endpoints running. No automatic trial retries are permitted. Remaining tasks
are assigned to healthy endpoints of the same model as they become free. Long
generations with advancing counters are allowed. The watchdog is an infrastructure
detector, not a claim that the model is making useful semantic progress.

The guardian and supervisor monitor each other's existence. Guardian failure is
noticed by the supervisor on its next loop; a dead or stalled supervisor causes the
guardian to stop owned workers/proxies. Alerts are persistent local files and logs;
no email/Slack notifications are configured.

## Validation before restarting

- Transport timeout injection: original Harbor makes nine calls; adapter makes one.
- Replay of a real 27,396-token incident response: content/reasoning preserved, JSON
  parses, two commands recovered, next conversation advances by two messages.
- Same replay deliberately delayed **605.156 seconds**: succeeds beyond the old
  600-second boundary with one HTTP request for that turn.
- Client disconnect cancels backend work; endpoint then accepts another request.
- Overlap rejected; exact response and single Content-Length verified.
- Parse-failure bound and reset verified.
- Nine watchdog tests pass, including sustained slow token progress without false alarms.
- Real guardian fault injection: both a dead scheduler and a stale heartbeat cause
  real child processes to stop and an alert to be persisted.
- **Five out of five real-model Harbor/Docker/tmux/verifier smoke trials pass.**
  Smoke trials are separate from benchmark results and disable thinking only for
  their short plumbing test; benchmark trials retain the original reasoning behavior.

Machine-readable validation files are in the remote reliability directory and copied
beside the local source. The initial smoke fixture had an invalid unqualified task
name; it was corrected to `local/reliability-smoke` before the successful five-way run.

## Clean comparison

Run: `comparison-20260929-065104`.

| Endpoint | GPU | Initial task |
|---|---:|---|
| qwen-a | 0 | session-window-debug |
| qwen-b | 1 | react-lead-form |
| qwen-c | 3 | mvcc-lsm-compaction |
| bonsai | 2 | session-window-debug |
| bonsai2 | 2 | react-lead-form |

One clean trial per model per agreed task: ten total. Each model's shared task queue
contains the remaining tasks; completed lanes immediately take the next pending task.
No replicas or task substitutions are silently added. The manifest records source hashes,
task list, topology, and monitoring settings. Old results are not pooled with this run.

Remote inspection, in one SSH connection:

```bash
ssh voodoo 'python3 - <<'"'"'PY'"'"'
import pathlib
root = pathlib.Path.home() / "bonsai_perf/reliability"
run = pathlib.Path((root / "CURRENT_RUN").read_text().strip())
print((run / "status.json").read_text())
alerts = run / "ALERTS.jsonl"
print(alerts.read_text() if alerts.exists() else "No alerts")
PY'
```

`status.json` includes heartbeat, lane PIDs, task assignments, token counters, quarantine
reasons, remaining queues, and completed outcomes. Proxy events/raw bodies live in the
run directory. Harbor traces/results remain in `bonsai_perf/harbor_jobs/<job-name>/`.
Slurm retains the original serving allocations and their time limits; backend loss is
detected and quarantined rather than bypassing scheduler ownership.

## Upstream research

[Harbor Terminus source](https://github.com/harbor-framework/harbor/blob/main/src/harbor/agents/terminus_2/terminus_2.py)
and the downloaded/installed 0.23.0 source were inspected. An upstream
[parse-loop issue](https://github.com/harbor-framework/harbor/issues/2606) and
[proposed bound](https://github.com/harbor-framework/harbor/pull/2608) describe a separate
unbounded parse-failure problem. The
[large-heredoc issue](https://github.com/harbor-framework/harbor/issues/2677) is also
distinct and does not explain the transport timing evidence in this incident.
Those reports informed checks; they were not treated as proof of this root cause.

## Third Bonsai endpoint added at user request

At 2026-09-29 07:35:33 UTC (01:35:33 Boise), a third Bonsai endpoint began
`mvcc-lsm-compaction` as job
`comparison-20260929-065104-bonsai3-mvcc-lsm-compaction`.
Backend/proxy ports are 8106/9106. It uses the same Prism binary, model, 262,144-token
context, seed, reasoning settings, and eight-hour agent limit as the other Bonsai
endpoints. The server is an overlapping step inside the existing owned Slurm
allocation 5710 on GPU 2; no other allocation was bypassed.

The new endpoint passed a full Harbor/tmux/verifier smoke test. Three controller
adoption tests and the existing nine watchdog tests passed before the handoff.
The supervisor and guardian were replaced using the new `--resume` support, while
all five original workers and all five original proxies retained their process IDs
and process start identities. Their task deadlines and in-flight requests were
preserved. Only the controller processes were briefly stopped/replaced.
`handoff-before-bonsai3.json` and `handoff-after-bonsai3.json` record this check.

The scheduler reserved MVCC for bonsai3 and removed it from the shared Bonsai queue.
On completion, the third lane can take any remaining Bonsai task. Monitoring,
cancellation, raw reasoning logs, fail-closed behavior, and the independent guardian
cover all six lanes. This changes GPU contention partway through the run: Bonsai
now shares GPU 2 three ways. The manifest amendment and server launch record retain
timestamps so performance analysis can distinguish these phases. GPU memory after
loading the third server was 69,072 MiB used, 28,177 MiB free.

An earlier third-server launch was stopped at the user's intervening request to wait;
it never launched a benchmark trial. Its cancellation record is preserved separately
as `bonsai3-launch.json`; the authorized resumed launch is `bonsai3-launch-resumed.json`.
