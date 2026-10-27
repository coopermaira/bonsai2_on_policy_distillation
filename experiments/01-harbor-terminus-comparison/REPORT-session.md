# Session report: Qwen3.8-27B FP16 vs Bonsai2 27B PTQ1_0 agentic comparison (voodoo)

> **Superseded diagnosis (2026-09-29):** The retry loop was confirmed to be a
> 600-second client timeout plus abandoned backend requests retained by the proxy,
> not an oversized-JSON parser limit. See
> [confirmed fix, validation, watchdogs, and clean restart](voodoo-agentic-reliability-fix.md).
> The historical observations below are retained; their diagnosis was provisional.

Date: 2026-09-29
Machine: voodoo (4x RTX PRO 6000 Blackwell 96GB)
Framework: Harbor (`harbor` pip package v0.23.0) + Terminus-2 agent, Terminal-Bench task suite
(`harbor-framework/terminal-bench`)

## Setup

Five model-server endpoints, each `llama-server` (`-ngl 99 -fa on -c 262144 --parallel 1
--seed 1 --reasoning-preserve`), fronted by a transparent logging reverse-proxy
(`logging_proxy.py`) that records every `/chat/completions` round trip (reasoning_content,
content, finish_reason, usage, latency) to a per-endpoint JSONL file without altering
request/response bytes:

| Endpoint | Model | Binary | GPU |
|---|---|---|---|
| qwen-a | Qwen3.8-27B F16 | mainline `ggml-org/llama.cpp` (commit `1c4729414`) | GPU0 |
| qwen-b | Qwen3.8-27B F16 | mainline | GPU1 |
| qwen-c | Qwen3.8-27B F16 | mainline | GPU3 |
| bonsai-1 | Bonsai2 27B PTQ1_0 | PrismML fork + PR #215 speed fix | GPU2 |
| bonsai2 | Bonsai2 27B PTQ1_0 | PrismML fork + PR #215 speed fix | GPU2 (shared with bonsai-1) |

Agreed 5-task set (Terminal-Bench, varying difficulty, all `gpus = 0` in their own
`environment` section so no task-side GPU requirement confounds the model-serving GPU
comparison):

- `music-harmony` (1h, easy)
- `interleaved-vigenere` (2h, easy-medium)
- `mvcc-lsm-compaction` (4h, medium)
- `react-lead-form` (5h, medium)
- `session-window-debug` (8h, hard)

Harbor invoked once per (endpoint, task) pair (`-p`/`--path` is not repeatable in this
Harbor version — confirmed via its own `--help` text and reproduced via `lock.json` only
ever registering the last task passed), agent kwargs: `interleaved_thinking=false`,
`store_all_messages=true`, `enable_summarize=true`, credentials passed explicitly via
`--ak 'llm_kwargs={"api_key":"..."}'` (see `harbor-litellm-api-key-gotcha` memory note —
the `OPENAI_API_KEY` env var did not reliably reach litellm's client in this setup).

## Finding: Terminus-2 identical-request retry loop on long completions

### Symptom

Four of the first five launched trials (qwen-a/session-window-debug, bonsai-1/session-window-debug,
qwen-b/music-harmony, bonsai2/music-harmony) entered a state where the proxy log showed
**byte-identical `usage` (completion_tokens, prompt_tokens, total_tokens) and identical
`n_messages_in` across multiple consecutive HTTP round trips**, with per-request wall-clock
latency increasing roughly linearly each repeat (e.g. qwen-a: 1000s → 1404s → 1810s →
2216s → 2625s, in ~400-450s increments). Both models' own reasoning text claimed the
sandbox terminal was "frozen" from an earlier malformed heredoc.

### Diagnosis

Directly inspecting the live tmux pane (`terminus_2.pane`) for both qwen-a and bonsai-1
at the time of the stuck condition showed **normally functioning shells** — real, distinct
command executions and outputs (file searches, source reads), not a hung `>` heredoc
prompt. This contradicts the models' own self-diagnosis narrated inside the stuck
completions; that narration was evidently stale content carried inside one very large
generation, not a live description of current state.

Since the requests were reproducibly byte-identical (fixed seed, temperature 0 →
deterministic output for identical input), the repeat is not the model choosing to loop —
it is **Terminus-2 resending an unchanged conversation state**. The one clear correlate
across all four affected trials is completion size: every first stuck turn had an unusually
large completion (18,673 / 32,600 / 26,736 / 30,565 tokens). Working hypothesis: a
completion of this size fails Terminus-2's structured-JSON response parsing/validation
(`parser_name: "json"`), and its retry path resends the identical request rather than
surfacing the parse failure, truncating, or backing off with a varied request. This
occurred independently on **both model families (FP16 and ternary) and two different
tasks**, which argues against a quantization-specific or task-specific cause and for a
harness-level robustness gap in Terminus-2's handling of long structured completions.

`qwen-c` (interleaved-vigenere) did not exhibit the pattern over the same observation
window — `n_messages_in` and `usage` varied normally turn to turn.

### Impact and remediation

- `qwen-a` + `bonsai-1` on `session-window-debug`: caught at 5-6 identical repeats
  (~1.5-2h of the run each), killed.
- `qwen-b` + `bonsai2` on `music-harmony`: caught earlier at 2-3 identical repeats,
  killed proactively once the same signature was confirmed.
- All four associated Docker sandbox containers cleaned up (`docker rm -f`); the fifth
  (`qwen-c`/interleaved-vigenere) was left untouched and healthy throughout.
- `qwen-a` and `bonsai-1` relaunched fresh on `mvcc-lsm-compaction` (replacement task,
  4h estimate, `gpus = 0`) in place of `session-window-debug`.
- `qwen-b` and `bonsai2` relaunched fresh on `music-harmony` (retry).

### Open question

Root cause is not yet confirmed at the Terminus-2 source level (would need to inspect
its JSON-parse/retry code path directly, e.g. `harbor/agents/terminus_2/terminus_2.py`
around `_query_llm`/`_handle_llm_interaction`, and reproduce with a deliberately
oversized completion). Treat this as a standing risk for any future long-horizon run
with this Harbor/Terminus-2 version (`harbor` 0.23.0): monitor for frozen `n_messages_in`
+ repeated identical `usage` early, rather than assuming a long single-turn latency is
just slow decode.
