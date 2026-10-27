# Bonsai 2 27B agentic evaluation and RL groundwork (Terminal-Bench)

Consolidated from the voodoo GPU server (`/mnt/data/private/cmaira/bonsai_perf/`) and local
analysis directories on 2026-10-26. Covers 2026-09-28 through 2026-10-05.

**Goal:** find out where the ternary-quantized Bonsai 2 27B (`PTQ1_0`, ~1.75 bpw) falls
behind its full-precision reference (Qwen3.8-27B F16) on long-horizon terminal tasks, and
find a reward signal that could train it to close the gap.

**Status: no RL training has run yet.** Every phase was evaluation, failure analysis and
reward-signal validation; each protocol explicitly states "no training authorized". The
current recommended first training baseline is quantization-aware on-policy distillation
(see `experiments/06-recovery-signals/implementation-plan.txt`), pending a reproducible
quantizer and a validated reward.

## Experiments

| # | Date | Directory | What it did | Key result |
|---|---|---|---|---|
| 01 | 09-28/29 | `01-harbor-terminus-comparison` | Harbor 0.23.0 + Terminus-2 on 5 Terminal-Bench tasks (music-harmony, interleaved-vigenere, mvcc-lsm-compaction, react-lead-form, session-window-debug), Qwen F16 x3 endpoints vs Bonsai x2, logging proxy on every call | No full-task pass for either model on any task (session-window 3/7 tests each). Uncovered the retry-loop incident |
| 02 | 09-29 | `02-reliability-fix` | Diagnosed the "identical request" loop: 600 s litellm timeout + proxy keeping abandoned requests. Built `reliable_proxy.py`, `reliable_terminus.py`, supervisor + guardian watchdogs, tests | 605 s replay and 5 real-model smoke tests pass. Holds the canonical `comparison-20260929-065104` run |
| 03 | 09-29 | `03-trajectory-analysis` | Aligned the 5 paired trajectories (584 calls), first-divergence events, action-substitution replay, next-token probes at command boundaries | Main recoverable failure: Bonsai assumed embedded images in a PDF and kept repairing extraction code instead of checking the premise |
| 04 | 09-29 | `04-same-state-policy` | Preregistered, blinded: 40 seeded next-responses per model at 3 fixed music-task states (240 samples) | Explicit premise correction 22/40 Bonsai vs 39/40 Qwen (Holm p=2.4e-5); useful next action 38/40 vs 39/40, a much smaller gap |
| 05 | 10-03 | `05-retrospective-review` | Reference-informed requirement-coverage + 6-dimension process grading of the 10 trajectories; React app re-verification | Shared 0 pass score hid real partial work: React 91.7 both, MVCC 70 both, session window 37.5 vs 50 |
| 06 | 10-03 | `06-recovery-signals` | Candidate RL signals: executed matched-state recovery continuations, Qwen process judge (with/without prose), full-vocab teacher distributions and dense KL (`dense_score.cpp`), verifier audit | Judge not validated as a reward (one positive). Per-span forward KL 0.056-0.087 nats, measurement path verified. Benchmark reference itself fails 3/18 added conservation cases |
| 07 | 10-04/05 | `07-harness-v2` | Custom harness replacing Terminus (native act tool, deterministic context compaction, filesystem checkpoints, token budgets instead of wall clock). 8 new tasks, one paired attempt each, Slurm 5769. Rubric partial-credit scores + independent process review | Over the 7 tasks both completed: Qwen mean functional 54.4 vs Bonsai 44.3; process review 11.4 vs 9.2 of 20 over all 8. Bonsai showed clear repetition on production-planning and sound-change-cascade |

Each directory has its own protocol and report (`PROTOCOL*`, `REPORT*`, `README.md`,
`findings.txt`) written at the time. Read those for methods and caveats; the table above
is only an index.

## Setup common to all runs

- Machine: voodoo, 4x RTX PRO 6000 Blackwell 96 GB, Slurm, Docker (`ml_benchmark` image).
- Bonsai: `Ternary-Bonsai-2-27B-PTQ1_0.gguf` on the PrismML llama.cpp fork (+ PR #215 decode fix).
- Reference: `Qwen3.8-27B-F16.gguf` on mainline llama.cpp (`1c4729414`). Hashes in
  `01-harbor-terminus-comparison/scripts/models.sha256` and `03-trajectory-analysis/replay-results/model-sha256.txt`.
- Tasks: all from `harbor-framework/terminal-bench` at `4def1f3` (2026-09-23), Apache-2.0
  (see `third_party/terminal-bench/`). 01-06 use the same 5 tasks; 07 uses 8 different ones,
  run through the custom harness with prespecified requirement-group rubrics.
- None of these are official Terminal-Bench leaderboard scores.

## Not included in this tree

- Model weights (~173 GB) and the Terminal-Bench clone (965 MB). Use upstream.
- 118 files over 2 MB (0.81 GB, mostly gzipped full-vocabulary distributions and
  `.tar.gz` bundles) remain on voodoo. Listed with sizes in `data/large-files-on-voodoo.tsv`.
- Root-owned verifier scratch dirs in `harness-v2/runs/*/verification/verifier` (unreadable).
- The CUDA kernel performance work on the PrismML llama.cpp fork, which shared the same
  `bonsai_perf` directory, is a separate project and deliberately not in this repo.
- Raw per-trial trajectories (~730 MB, thousands of small files) are kept out of git:
  `07-harness-v2/runs/` (562 MB), `02-reliability-fix/comparison-20260929-065104/` (139 MB)
  and `01-harbor-terminus-comparison/jobs/` (28 MB). Links in the reports
  that point into these paths will not resolve here. The condensed evidence the analyses
  were based on is included: `03-trajectory-analysis/index/`, `05-retrospective-review/review/`
  and `07-harness-v2/independent-review*/` hold turn-by-turn indexes and selected records.
