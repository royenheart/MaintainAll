---
name: systematic-debugging
description: Use when a bug, failing test, intermittent failure, or unexpected behavior needs diagnosis and a verified fix. Shared model index is provided by the model-policy skill.
---

# Systematic Debugging

## Model adaptation

Load the skill named `model-policy` using its exact location and reader from the host skill catalog. The catalog location takes precedence over directory names. For a filesystem installation without a catalog entry, try [the sibling policy](../model-policy/SKILL.md), relative to the resolved location of this `SKILL.md`, never the working directory. Do not guess filesystem paths for opaque resource URIs. Resolve this skill by its frontmatter name and apply the returned profile and applicable supplements once. If the policy or registry cannot be read, report that adaptation is unavailable, use bounded steps and observable checks, and continue authorized work without inventing a model tier.

Investigate the cause before proposing a permanent fix. Under time pressure, replace
speculative edits with explicit, falsifiable hypotheses.

1. Read the complete relevant error, stack trace and status. Capture expected versus
   actual behavior, reproduce when possible, and inspect recent code, dependency and
   environment changes. For intermittent failures, record frequency and timing.
2. Trace the failing operation or value across component boundaries. Use minimal
   instrumentation and compare a working case; do not dismiss unexplained differences.
3. Test one concrete hypothesis at a time: state why it fits the evidence and what
   observation would disprove it. Change one variable in a reversible experiment.
   Record failures instead of stacking speculative patches.
4. Once the causal explanation is supported, add a regression test where feasible,
   fix the cause, and rerun the reproduction and affected checks. Avoid unrelated
   changes and remove temporary diagnostics.
5. After three ineffective attempts, reconsider assumptions, evidence and task size.
   Address missing context or environment problems before requesting a model-policy
   escalation. Ask the user only for missing access or a consequential decision.

An incident may require a reversible mitigation before the root cause is known.
Label it as mitigation, document rollback and follow-up diagnosis, and do not claim
that the root cause is fixed. Redact secrets from diagnostic logs.

Avoid unsupported causal claims, arbitrary trial changes, simultaneous speculative
fixes, skipped meaningful regression checks, and symptom-only patches presented as
permanent solutions. If evidence establishes an environmental or timing problem,
record the investigation and add appropriate timeouts or monitoring. Use bounded
retries only when the operation is idempotent or a verified idempotency key prevents
duplicate effects. A timeout can occur after a write commits. Without that protection,
inspect and reconcile the actual state, report a clear error, and do not blindly retry.
Do not invent statistics to justify an explanation.
