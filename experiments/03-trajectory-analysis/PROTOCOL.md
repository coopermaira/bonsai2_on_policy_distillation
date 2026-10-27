# First meaningful divergence protocol

An observation state is the actual model-visible message history plus the relevant
environment state. It is not a claim about the model's unobservable knowledge.
Recorded reasoning is behavioral evidence, not a guaranteed causal explanation.

## Unit and alignment

Each raw response has a stable `(lane, session, response_index, request_id)`.
Response indices are one-based and count successful HTTP responses, including
empty or unparseable outputs. They are not counts of executed shell commands.
One response may contain several atomic decisions. Annotate each by:

`intent; target/subproblem; stated hypothesis; evidence consulted; proposed action;
observed execution; environment effect; constraint retained/lost; consequence;
recovery; confidence; evidence paths`.

Use intents such as inspect environment, read specification, read implementation,
form/test hypothesis, reproduce failure, edit implementation, test invariant,
diagnose failed command, repair diagnostic, change strategy, and submit.

Different shell syntax is equivalent when the information sought and relevant
effect are equivalent. Fold repeated reads and differences in batching into a
shared milestone only when neither adds a consequential observation. Do not fold
different hypotheses, edits, malformed actions, or lost constraints together.
Retain the raw indices and any extra calls even when milestones are aligned.

For these existing independent runs, report a divergence pair `(i_FP16, i_Bonsai)`
and the alignment rule. A single scalar based on raw request counts would confuse
batching and parser failures with strategy. Under a future shared-state rollout,
`T_diverge` is the number of equivalent decision units preceding the first material
branch. Also record whether that first branch was harmful, beneficial, or unresolved.
The first harmful branch is a separate event; do not retrospectively call the most
dramatic failure the first divergence.

## Shared-context measurement

The pilot uses the same Prism `src_p215` server binary for both model artifacts,
one GPU per model, no generated-command execution, and archived exact request
messages. It verifies equal rendered chat templates, identical input token IDs,
and all 248,320 output token IDs/pieces before comparing distributions.

Each checkpoint produces a full-vocabulary, pre-sampling distribution for one next
token. The server uses float softmax; the runner records returned probability mass
and normalizes only finite-precision summation error. It preserves the full result.
KL is in nats, directed FP16 to Bonsai; Jensen-Shannon and top-k overlap accompany it.
This is not KL from independently renormalized top-k lists.

Two positions are sampled: continuation start, and five constructed command
boundaries with the same archived Bonsai reasoning and response prefix forced into
both models. The latter measures behavior *conditional on that supplied reasoning*.
Neither measures the distribution over entire semantic actions. Syntactic tokens
such as `cat` or `I` can have matching distributions despite a later strategic split.
Longer contexts in this pilot also differ in content and task; they cannot isolate
a causal effect of context length.

The original experiment had stochastic sampling, different server builds, and
different container IDs in initial messages. Subsequent histories differ further.
Therefore an observed original branch cannot by itself be attributed to quantization.
The pilot removes the runtime/template/input differences at sampled checkpoints,
but does not establish a pure quantization-only intervention on an identical
precompression checkpoint. The source downloader used an unpinned `main` revision.
Actual model-file SHA256 hashes are retained for reproducibility.

## Counterfactual pilot

The selected checkpoint is Bonsai music response 7: it has read the title and
incorrectly assumes the music is embedded imagery. Reconstruct the task container
with the same PDF, Python base task image, pypdf 6.19.0, and its prior examination
script. Commit one new checkpoint and clone it into control and intervention arms.

Control executes Bonsai's archived response-7 command batch. Intervention executes
FP16's archived response-3 batch, which inspects and decompresses the PDF streams.
Keep the same Bonsai prior messages, analysis, and plan; replace only the command
batch. Append observations from the commands actually executed in each clone.
Then sample one next Bonsai response per arm at temperature 1, seed 1, with an
8,192-output-token ceiling. Preserve requests, outputs, command exit codes, image
ID, dependency inventory, and PDF hash. Execute no newly generated commands.

This tests immediate recovery after an action substitution in a reconstructed
replica. It is not a full-task rescue experiment, and the old run did not preserve
an intermediate container snapshot. It also does not replace a Bonsai action with
an FP16 action generated from the *same* checkpoint: the donor action was found in
the existing FP16 trajectory. That action's preconditions are verified in the clone.

For the definitive experiment, retain exact intermediate snapshots, sample both
policies from the same checkpoint, use repeated seeds and within-model controls,
and continue both arms to the task verifier. Compare command-only versus full
response transplantation separately. Carry forward the actual new observations;
never append the old trajectory's expected observations after a different action.

## Remaining hypotheses

Estimate harmful-branch frequency, recovery probability, and wasted calls/tokens
after the branch, not just T_diverge. Include repeated FP16-vs-FP16 and
Bonsai-vs-Bonsai rollouts to quantify sampling variation. This dataset has no
successful benchmark trials, so it cannot test successful-versus-failed Bonsai
T_diverge. Smoke tests with different reasoning settings are not a valid success
comparison group.
