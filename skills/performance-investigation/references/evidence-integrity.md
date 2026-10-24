# Evidence that survives interpretation

Retain the raw capture, source/data identity, tool/runtime configuration and operation boundaries. Check that the capture includes the work and participants being attributed: source resolution, threads/processes, device streams, inherited work, sampling filters and collection loss can change the conclusion. Resolve ambiguous ownership with another signal or a narrower experiment.

Validate timelines before deriving weighted costs. Preserve invalid or negative intervals and missing/truncated regions; mark affected derivations unavailable rather than repairing the clock to obtain a plausible answer. Define clipping and aggregation at the relevant operation boundary. Whole-run and action-window results remain distinct.

Normalize counters against the actual delivered work and collection scope. Verify event semantics in the installed collector rather than inferring them from a flag name. Use source/stack and phase attribution where it matters. Keep unresolved symbols or generated-source ownership visible rather than interpreting unresolvable zero counts as absence.

Triangulate low-resolution or sampled evidence with work counts, boundary timing or controlled perturbation. Overlapping attribution groups must not be added as independent costs. Preserve uncertainty that changes the decision, and remove repetitive warnings that add no interpretation.

Keep raw numeric files byte-identical where possible. Redact necessary strings without changing values, order or event structure. Serialization can silently round large integers or alter floating-point tokens; use exact numeric processing or preserve original token spans and verify the transformed artifact. Review tools should avoid parsing and rewriting raw datasets merely to display them.

When correcting a summary, retain the original observations and identify the accounting correction. A new run with different settings is a new cohort, not a replacement for inconvenient evidence. Revalidate affected conclusions after changing the workload, implementation or measuring system.
