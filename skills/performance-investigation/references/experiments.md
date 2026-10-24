# Experiments that change the diagnosis

## Choose between explanations

Form competing mechanisms from the system model. For each useful experiment, state what it changes, what competing explanations predict and which next decision each outcome enables. A hotspot, correlation or single counter narrows the search; it does not by itself establish why the user's outcome is slow.

Prefer interventions that separate mechanisms: vary problem size to test scaling; vary concurrency to expose serialization or saturation; vary locality/reuse to test data movement; bypass or replace one stage to locate a boundary; vary resource allocation to test sensitivity. Use factorial or interaction experiments when a one-variable design would hide the suspected coupling.

Look for a predicted signature, not just a favorable total. If reducing one component's work leaves completion unchanged, inspect overlap, fixed delays, moved work, downstream limits and observer resolution. If an optimization helps only an amplified workload, identify the workload region in which it matters.

Estimate a plausible ceiling from the critical path or resource demand before investing in a local optimization. Revisit that estimate after the change; parallelism, batching, caching and approximations can alter the execution graph rather than simply shorten a node.

## Construct a valid comparison

Choose the baseline/candidate, input semantics and operating state explicitly. Match the variables needed for the question and record meaningful differences. Reuse the same corpus/snapshot when identity, ordering, timestamps or state influence results; compare semantic outputs when native identities necessarily differ.

Separate startup, warmup, steady operation, recovery and sustained behavior where relevant. Use paired/interleaved or order-balanced execution to reduce drift when appropriate. When runs are inherently sequential or conditions cannot be matched, retain that design in interpretation rather than retroactively treating the samples as interchangeable.

Measure enough independent repetitions and operating points to support the decision. Preserve raw runs, warmups, failures and outliers with their conditions. Extend testing to resolve uncertainty that matters; do not repeat a whole matrix merely to obtain cleaner-looking values. Report single observations and small descriptive cohorts as such.

## Explore workload boundaries

Test the region in which the system will be used, including contention, bursts, skew, cache state, sustained memory pressure or tail-sensitive operations when relevant. Compare per-operation work and total delivered work so reduced demand or skipped results are not mistaken for faster execution.

Select controls from the actual contract: complete membership/order, numerical quality, durability, lifecycle cleanup, cancellation, retries, interactive reachability or other meaningful invariants. Performance tradeoffs can be valid design changes when the user permits them; state and test the changed contract.

## Separate measurement from intervention

Instrumentation is a participant. Check whether tracing, screenshots, heap snapshots, symbolization, polling or validation changes scheduling, optimization, caching or work volume. Use a lighter probe or a separate observer-off cohort when needed, and do not equate an unpaired difference with causal instrumentation overhead.

Correlate clocks and completion boundaries across participants. Keep submission, actual execution and observation distinguishable. Use operation identifiers and local monotonic intervals where possible rather than subtracting unrelated host timestamps.

Retain distinct experiments as distinct: microbenchmarks, isolated stages, real end-to-end runs, simulations and profiled runs answer different questions. Use their agreement to strengthen a mechanism, not to add their speedups or pool incompatible samples.
