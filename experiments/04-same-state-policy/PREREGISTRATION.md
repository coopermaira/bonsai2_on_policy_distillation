# Shared-state music policy experiment

Specified before sampling, 2026-09-29. This extends, and supersedes causal interpretations of, the earlier one-action substitution sanity check.

## Design

Three fixed archived Bonsai histories, each supplied verbatim to both artifacts:

1. `selection`: before response B7, after text extraction returns only the title.
2. `recovery_api`: before B8, after the forced image-extraction branch returns an AttributeError for `get_resources`.
3. `recovery_evidence`: before B16, after the same longer mistaken history and an object listing containing fonts/content streams but no image objects.

Forty independent seeded next-response samples per model per state, 240 total. The environment observation is literally the same archived message for both models; no actions are executed and no fresh environment is required to sample this policy. This estimates next-decision behavior, not successful tool execution or full-task completion. In particular, the late recovery state is a selected survivor history, not a population estimate of recovery across arbitrary mistakes.

Same Prism server binary, one GPU per artifact, four concurrent slots per server, 32,768 context tokens per slot. Explicit temperature 1, top_k 20, top_p .95, min_p .05, repeat penalty 1; zero presence/frequency penalties. Preserve reasoning. Cap each response at 8,192 output tokens. No adaptive stopping based on labels. Resume completed samples only after a transport/job interruption, preserving distinct seed/sample IDs. Report any unsuccessful requests and capped responses, never silently drop them.

Verify rendered template and input-token equality for every state before generation. Archive messages, server properties, sampling parameters, outputs, seed IDs, hashes, timing, finish reason, and usage. Seeds use disjoint deterministic ranges across state/model. These are independent samples, not paired-seed causal estimates. GPU nondeterminism may prevent bit-exact reruns.

## Classification, fixed before viewing samples

Shuffle responses with model and seed hidden for semantic annotation. Read assistant analysis/plan and actual proposed commands. Recorded internal reasoning may clarify an ambiguous decision but is not privileged evidence of its cause.

Primary action labels (mutually exclusive):

- `image_commitment`: seeks/extracts presumed embedded images, or only repairs image-extraction APIs while maintaining that premise. Merely inspecting `/Resources` counts here only when the stated purpose commits to image extraction rather than discriminating representations.
- `diagnose_representation`: inspects content streams, object/resource dictionaries, or operators to discriminate representation without asserting embedded images as established. A genuinely conditional image-presence check belongs here, not automatically in the harmful category.
- `vector_pivot`: explicitly rejects the image premise or identifies vector notation AND proposes an action consistent with inspecting/parsing/rendering that content.
- `render_agnostic`: rasterizes the PDF or installs a renderer without deciding it contains embedded images. Rendering a vector PDF is not image extraction.
- `other`: valid action not covered above, with explanation.
- `unusable`: no interpretable actionable response, invalid protocol, or output cap before any reliable action can be determined.

Additionally mark `premise_rejected` true/false/unclear, `mixed_action` if multiple commands span categories, and `capped` independently. For a mixed batch, label the first consequential information-gathering action; preserve the later action in notes. Syntax-only variants are equivalent. A capped sample with a usable complete action remains labeled but enters a sensitivity analysis separately.

Primary selection endpoint: proportion `image_commitment` among ALL 40 samples per artifact at `selection`. Report alternative actions and unusables, not just a binary success count.

Primary recovery endpoint at each bad state: `vector_pivot`, with explicit premise rejection and a consistent action, among ALL 40 samples. Secondary endpoint: broad escape from image commitment (`diagnose_representation`, `vector_pivot`, or `render_agnostic`). A generic API failure does not prove the premise false, so testing it is distinct from explicit recovery; report both endpoints rather than treating all continued investigation as irrational.

## Statistics and interpretation

Report category counts, Wilson 95% intervals per binomial proportion, and Bonsai-minus-FP16 risk differences with Newcombe independent-proportions intervals. Report a two-sided Fisher exact test descriptively, with Holm adjustment across the three primary endpoints. No confirmatory population claim from one selected task; report effect size and interval first. Unusables stay in denominators, plus worst/best-case endpoint bounds and conditional-valid sensitivity results. Do not infer equivalence from a nonsignificant test; 40 samples per cell can miss moderate or small effects.

Artifact-dependent local policy differences with the same state/runtime support a narrower claim than quantization-only causality: source revision/precompression provenance remains imperfectly established. Neither this one-step experiment nor a null result establishes compounding long-horizon noise. That third hypothesis requires many checkpoints and repeated rollout/snapshot interventions, including within-model baselines and final verifiers.
