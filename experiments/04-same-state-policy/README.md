# Same-state local policy: music harmony

**The repeated-sample experiment finds a large difference in explicit premise correction, but much smaller differences in the next tool choice.** It does not show a large initial image-extraction preference difference at the selected checkpoint.

Both artifacts received exactly the same archived message histories and environment observations. We sampled 40 next responses per artifact at each of three checkpoints: 240 samples total. These are comparisons of the two models on the same state, not comparisons of their independently evolved trajectories and not action-substitution continuations.

## Results

The preregistered primary endpoints require valid strict JSON as well as the semantic event. Every row has denominator 40, including malformed outputs. Percentage-point differences are Bonsai minus FP16; intervals are 95% Newcombe intervals for independent proportions.

| Checkpoint and primary event | Bonsai | FP16 | Difference, percentage points (95% CI) |
|---|---:|---:|---:|
| Before committed image-extraction action: chooses image-extraction branch | 4/40 (10%) | 3/40 (7.5%) | +2.5 (−11.3 to +16.4) |
| After the same extraction API error: explicitly rejects image premise and proposes consistent action | 0/40 | 0/40 | 0 (−8.8 to +8.8) |
| After the same object listing: explicitly rejects image premise and proposes consistent action | 22/40 (55%) | 39/40 (97.5%) | −42.5 (−57.8 to −24.8) |

The last primary comparison has two-sided Fisher p=0.00000805, Holm-adjusted p=0.0000242 across the three primary endpoints. The other two primary comparisons have p=1. These are selected-checkpoint results with sampling uncertainty; they are not population estimates across tasks, and the intervals do not account for annotation uncertainty.

The **behavioral escape endpoint** is broader: the next consequential action diagnoses the representation, inspects vector content, or renders the whole page, instead of continuing presumed embedded-image extraction. This was specified as a secondary endpoint before sampling.

| Same bad state | Bonsai | FP16 | Difference, percentage points (95% CI) |
|---|---:|---:|---:|
| After API failure: useful alternative next action | 2/40 (5%) | 7/40 (17.5%) | −12.5 (−27.4 to +2.0) |
| After object listing: useful alternative next action | 38/40 (95%) | 39/40 (97.5%) | −2.5 (−14.2 to +8.5) |

One FP16 response at the last checkpoint adds prose before otherwise interpretable JSON. If this wrapper is accepted, FP16 is **40/40 for both explicit correction and useful next action**. Bonsai remains 22/40 and 38/40 respectively. Under that semantic interpretation, the next-action difference is −5 points (95% CI −16.5 to +4.5). The substantial gap in explicit correction and the much smaller gap in action selection remain.

Full rates, Wilson intervals, category counts, and protocol bounds are in [statistics.json](statistics.json); the [semantic sensitivity](protocol-semantic-sensitivity.json) accepts interpretable actions despite JSON wrappers. The reviewed sample-level data are in [labeled-samples.csv](labeled-samples.csv).

## What the difference means

**Initial branch selection:** these samples do not reproduce a large Bonsai-versus-FP16 difference. Image-extraction commitment occurs in 4 versus 3 samples. This is a proxy for choosing the original bad branch; we did not execute these actions, so it is not a measured rate of downstream harm. Some correctly implemented image-presence checks could expose the absence of images immediately. Rendering a PDF to a bitmap is not classified as embedded-image extraction.

**After an API error:** most samples from both models keep trying to access images. The error only says `get_resources()` does not exist; it does not itself contradict the image premise. FP16 chooses a broader investigation or rendering route more often in this sample, but the interval includes no difference. Zero explicit corrections is not proof of zero recovery probability: the per-model Wilson upper bound is 8.8%, before treating malformed responses as unknown outcomes.

**After contradictory evidence:** FP16 consistently revises its stated representation of the PDF. Bonsai often carries forward the image idea or leaves it unresolved, yet still inspects the content stream. Of Bonsai's 40 responses, 22 explicitly reject the premise and propose a consistent action, 16 inspect the representation without that explicit correction, and two continue searching for presumed missing image objects. This is evidence of a difference in **expressed premise revision conditional on this state**. It is weaker evidence of impaired next-action recovery because 38/40 Bonsai samples choose a useful investigation or rendering action.

For example, [Bonsai sample 017](outputs/recovery_evidence-bonsai-017.json) says that images must be referenced in the content stream, then proposes decompressing that stream and the CMap. [FP16 sample 003](outputs/recovery_evidence-fp16-003.json) identifies the ProcSet entries as process-set identifiers rather than actual images, then also proposes decompressing the content stream. The explanations differ more than the information-gathering actions. Bonsai samples [004](outputs/recovery_evidence-bonsai-004.json) and [011](outputs/recovery_evidence-bonsai-011.json) are the two that search for presumed missing images first; sample 004 also proposes content inspection later in its batch.

The strict correction endpoint combines a stated belief and a proposed action. It does not measure internal beliefs directly, guarantee correct replacement hypotheses, or establish that the command executes. Some responses reject images but incorrectly attribute the notation to the title font. The useful-action endpoint is closer to the user's semantic-policy question; an appropriate inspection can coexist with uncertainty or an incorrect explanation.

## Exact states and controls

| State | Archived next-response position | Input tokens | Last observation |
|---|---:|---:|---|
| `selection` | Bonsai B7 | 3,851 | Text extraction returns only `Harmony`, `Piano`, `5` |
| `recovery_api` | Bonsai B8 | 4,257 | Identical forced image-extraction action fails with missing `get_resources` |
| `recovery_evidence` | Bonsai B16 | 9,465 | Identical longer wrong-branch history ends with complete object dictionaries and no image XObjects |

Each state uses the same literal archived messages for both models, including assistant history and terminal output. Before generation, the runner verifies identical rendered chat templates and token IDs. Every output's prompt-token usage agrees with the relevant checkpoint length. Thus the recovery comparison does not select only the models' naturally failing samples: both are supplied the same bad history and evidence.

The selection state already contains B5's earlier generic assertion that the PDF has “content streams, images, and fonts.” It is before the committed image-extraction action, **not before the first mistaken image claim**. These probabilities are conditional on an existing Bonsai-generated history, not a neutral minimal prompt or each model's own natural state distribution. The late recovery state is also one selected history; it cannot estimate recovery across all possible mistakes.

Models: `Qwen3.8-27B-F16.gguf` and `Ternary-Bonsai-2-27B-PTQ1_0.gguf`. Both use the same Prism `src_p215` server binary, one GPU each, four concurrent slots, and 32,768 context tokens per slot. Sampling is temperature 1, top_k 20, top_p .95, min_p .05, repeat penalty 1, no presence/frequency penalties, disjoint deterministic seed ranges, and an 8,192-output-token cap. No cap was reached. All 240 HTTP requests completed successfully; combined completion usage was 121,122 tokens. Generated commands were not executed.

Matched runtime and input isolate artifact-dependent local-policy behavior. They do not establish quantization-only causality: the FP16 downloader used unpinned `main`, so exact precompression checkpoint identity remains insufficiently established. Artifact hashes are preserved in the [earlier provenance file](../replay-results/model-sha256.txt).

## Annotation and audit

The [preregistration](PREREGISTRATION.md) fixes states, sample counts, sampling settings, semantic categories, and endpoints before generation. A single reviewer annotated shuffled responses with model and seed IDs hidden, reading analysis, plan, and proposed commands. This is not an independent multi-rater study. The [annotation notes](ANNOTATION_NOTES.md) record clarifications, borderline cases, and deviations.

All 240 semantic labels were assigned before model unblinding. A final protocol assertion detected one additional prose-prefixed response, but the shell continued to the statistics command, revealing group rates before that deterministic format correction. Only that protocol label changed afterward; its semantic interpretation stayed the same. Both [initial labels](labels-initial.csv) and [final labels](labels.csv) and the [audit record](labels-frozen.json) are retained. No semantic category was revised after unblinding.

There are six strict-JSON failures: one FP16 selection response, one Bonsai and three FP16 API-recovery responses, and one FP16 evidence-recovery response. All have readable semantic intent. A forgiving parser would classify the selection response as diagnostic, the four API-recovery responses as image commitment, and the last response as explicit correction plus rendering. Treating those as interpretable actions does not reverse the substantive findings. The experiment did not run Harbor's parser and does not claim these six would necessarily fail in the live agent.

The mixed selection response `0126b603` is borderline: it probes images, inspects page structure, then installs a renderer. Classifying it as diagnostic instead changes Bonsai's selection rate from 4/40 to 3/40. That sensitivity further weakens, rather than strengthens, any initial branch-selection claim.

## What remains unresolved

Forty samples per model can miss small or moderate local-policy effects. Nonsignificance does not establish equivalence. These three checkpoints also cannot show that many small perturbations compound into long-horizon failure.

The specific follow-up suggested by these results is to continue samples that choose the same useful inspection but express different premises, using the same actual inspection output. Measure subsequent relapse into image extraction, correct decoding, successful command execution, and verifier outcomes. Across many checkpoints, repeated within-model baselines and shared-environment rollouts would distinguish ordinary sampling variation, persistent belief errors, code-generation defects, and accumulated local-policy differences.

Reproducibility files: [sampling runner](sample.py), [Slurm script](sample.sbatch), [plan](plan.json), [statistics code](statistics.py), [outputs](outputs/), and [server properties](fp16-props.json). Slurm job 5717 completed successfully in 12m19s; both servers were removed. Final checks showed no queued `cmaira` jobs or running Docker containers on voodoo.
