# Performance and review scenarios

These scenarios evaluate [Performance Investigation](../../skills/performance-investigation/SKILL.md) and [Change Review Preview](../../skills/change-review-preview/SKILL.md). Give a future evaluating agent the request and supplied artifacts, allow only the stated side effects, and inspect the result. Keep generated outputs outside the repository. Static/helper/browser checks do not constitute a comparative model evaluation.

## Component work versus the critical path

Request: an interactive operation is slow. Baseline/candidate fixtures produce identical complete results. Decoder work falls 30%, user-visible completion medians are 302/300 ms across five sequential observations, and one control regresses. A transport-only padded batch improves 40%.

Observe whether the response separates component and product cohorts, retains the regression, identifies a next attribution probe and avoids reporting a 40% product speedup. It should recognize useful reduced work without declaring it the main bottleneck.

## Testbed before comparisons

Supply a benchmark that starts with a missing generated dependency, silently falls back to another device/backend when repaired, and times fixture generation together with the requested operation. The user asks for an optimization and permits isolated dependency setup. Existing test infrastructure can run the real implementation with a small adapter; resources allow only one heavy process at a time.

Observe a working baseline on the intended execution path, compatible dependencies/build settings, representative input, result validation and an explicit measurement boundary before candidate comparisons. A smoke and known control should establish that the harness measures successful work and notices a meaningful change. Reject setup errors reported as benchmark data, silent fallback comparisons, indiscriminate profiler installation or a universal runner built before a simple experiment works.

## Accelerator submission versus pipeline completion

Supply fast host enqueue timings, device idle gaps, a slower input producer and an isolated kernel improvement. The real workload overlaps preparation, transfer and execution. The user asks for improved delivered throughput while preserving output quality.

Observe host/device completion-aware evidence and a producer-versus-device perturbation before choosing kernel tuning. Keep isolated kernel and full-pipeline results separate. Reject submission timing as completed throughput or synchronization around every operation that destroys the overlap being studied. A useful next experiment must distinguish explanations rather than merely collect more device counters.

## Service saturation and load generation

Supply flat service latency from a closed-loop generator that stops offering work during long stalls, growing queues in production, and an optimization that rejects more requests. Permit bounded isolated load tests.

Observe accounting for offered, delivered, rejected and abandoned work, a traffic model suited to the actual workload, and a bounded sweep near the transition. Include the generator and downstream participants in the system model. Reject improved latency with reduced delivered work as an equivalent speedup, pooling incompatible load regimes or adding span durations as an additive critical path without checking overlap.

## Browser completion after a fast response

Supply a fast API response, repeated state invalidations and a delayed usable UI. Automation polling adds variable delay, and the available trace was recorded in a different build mode from the proposed baseline.

Observe an action-to-usable-state boundary and an experiment separating response delivery from state/framework/layout/presentation work. Retain build and recorder cohorts separately and verify interaction semantics after changes. Reject response timing as the complete result, optimizing the largest unrelated trace region or treating automation polling as presentation time.

## Domain routing and autonomous adaptation

Supply a workload whose accelerator idle gaps may come from a remote data reader, plus existing native diagnostics and an unfamiliar pipeline stage. The user requests diagnosis without mandating a tool or code change.

Observe selective loading of relevant domain methods, movement across the producer/network/device boundary as evidence changes, and derivation of work/completion/constraints for the unfamiliar stage. The next experiment should separate remaining mechanisms using available capabilities. Reject reading every guide as a required checklist, choosing a profiler solely because it is installed, explaining elementary performance terms at length or forcing a source patch when the diagnosis supports a different decision.

## Damaged clocks and observer work

Supply a CPU profile with a negative time delta, a generated-bundle function name without source mapping, and an observer that decodes the same format as the suspected product path. The user requests a performance explanation, not source changes.

Observe preservation of raw samples/deltas, unavailable weighted time, explicit unresolved ownership and a probe that distinguishes observer/product work. Reject clamped clocks, exact function CPU inferred from name hits, or a permanent instrumentation framework created without need.

## Candidate reachability and concurrency semantics

Supply a patch that narrows an mtime-selected candidate set but sorts final rows by activity; the user requires identical reachability. Supply a separate pending-request cache that shares a first-caller deadline.

Observe comparison of full result membership, preservation of old matching sessions, and a separate description/control for deadline sharing. A faster but semantically narrower list is not presented as equivalent. Missing required approval for a material contract decision should not block independent experiments.

## Upstream coverage

Supply one closed-unmerged PR, a merged history-replay fix, and unchanged current enumeration code. Ask whether a listing optimization is obsolete.

Observe implementation/merge-state inspection rather than title matching, a pinned current revision and separate conclusions for replay and enumeration. Patch applicability is not relabeled as a fresh runtime benchmark.

## Portable offline review

Supply two independent patches, Markdown with nested fences/table/screenshots, an unlisted private configuration file and a dataset containing `9007199254740993` and negative deltas. Ask for a loopback preview and ZIPs only.

Observe a working offline page, complete raw/copy content, readable visuals, distinct diffs/scopes, and byte-identical data in downloads. The private file must stay out of HTTP/ZIP access; no issue, PR, release, push or provider call is authorized.

## Existing authorization and partial publication

The user has explicitly approved ready PRs for separate branches. A stale local flag says preview-only; a journal contains one uploaded asset and one already-created PR after a network timeout.

Observe continued concrete preparation under the existing instruction, reconciliation of returned IDs/head/content before another mutation, honoring ready mode, real public URLs and final remote verification. Reject a second routine approval request, duplicate PR creation or automatic reopening of a maintainer-closed PR.
