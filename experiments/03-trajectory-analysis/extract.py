#!/usr/bin/env python3
"""Index archived proxy calls without equating proposed commands with execution."""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def proposal(text):
    # This is a conservative annotation aid, not Harbor's execution parser.
    dec = json.JSONDecoder(strict=False)
    for i, c in enumerate(text):
        if c != "{":
            continue
        try:
            obj, _ = dec.raw_decode(text[i:])
            if isinstance(obj, dict) and isinstance(obj.get("commands"), list):
                return obj
        except ValueError:
            pass
    return None


def extract(run):
    records = []
    for log in sorted(run.glob("*.jsonl")):
        raw = run / (log.stem + "-raw")
        if not raw.is_dir():
            continue
        calls = {}
        for line in log.read_text().splitlines():
            event = json.loads(line)
            rid = event.get("request_id")
            if rid:
                calls.setdefault(rid, []).append(event)
        attempts, successes = defaultdict(int), defaultdict(int)
        for rid, events in sorted(calls.items(), key=lambda x: x[1][0]["ts"]):
            session = events[0].get("session_id") or "unknown"
            attempts[session] += 1
            reqp, resp = raw / (rid + ".request.json"), raw / (rid + ".response.json")
            req = json.loads(reqp.read_text()) if reqp.exists() else {}
            res = json.loads(resp.read_text()) if resp.exists() else {}
            backend = next((e for e in events if e["event"] == "backend_completed"), {})
            choice = (res.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            text, reason = message.get("content") or "", message.get("reasoning_content") or ""
            parsed = proposal(text)
            if backend.get("status") == 200:
                successes[session] += 1
                response_index = successes[session]
            else:
                response_index = None
            records.append(dict(
                session=session, lane=log.stem, attempt=attempts[session],
                response_index=response_index, request_id=rid,
                timestamp=events[0]["ts"], status=backend.get("status"),
                events=[e["event"] for e in events],
                request_path=str(reqp.resolve()), response_path=str(resp.resolve()),
                context_sha256=digest(req.get("messages", [])),
                request_sha256=hashlib.sha256(reqp.read_bytes()).hexdigest() if reqp.exists() else None,
                request_parameters={k:v for k,v in req.items() if k != "messages"},
                message_count=len(req.get("messages", [])), usage=res.get("usage"),
                finish_reason=choice.get("finish_reason"),
                reasoning_chars=len(reason), content_chars=len(text),
                proposal_parsed=parsed is not None,
                analysis=(parsed or {}).get("analysis"), plan=(parsed or {}).get("plan"),
                proposed_commands=(parsed or {}).get("commands", []),
                task_complete=(parsed or {}).get("task_complete"),
                semantic_label=None, environment_execution_verified=False,
            ))
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    records = extract(args.run)
    with (args.output / "steps.jsonl").open("w") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    groups = defaultdict(list)
    for r in records:
        groups[r["session"]].append(r)
    for session, rows in groups.items():
        lines = ["# " + session, "", "Indices count successful backend responses, including unparseable outputs.",
                 "Proposed commands are not proof of execution. Check the subsequent observation and Harbor events.", ""]
        for row in rows:
            lines += [f"## Response {row['response_index']} / attempt {row['attempt']}",
                      f"Request: `{row['request_id']}`; status: {row['status']}; finish: {row['finish_reason']}",
                      "", str(row['analysis'] or '(No extractable command envelope)'), "",
                      str(row['plan'] or ''), ""]
            for cmd in row['proposed_commands']:
                lines += ["```sh", str(cmd.get('keystrokes', '')), "```", ""]
        (args.output / (session + ".md")).write_text("\n".join(lines))
    print(json.dumps(dict(calls=len(records),sessions=len(groups),output=str(args.output))))


if __name__ == "__main__":
    main()
