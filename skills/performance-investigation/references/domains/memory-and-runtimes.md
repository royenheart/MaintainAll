# Memory and runtimes

## Separate lifetime from activity

Follow objects or regions through allocation, reuse, retention and release. Compare repeated operations at a known lifecycle boundary, not just before/after gauges from processes of different ages. Determine whether growth is intentional cache state, delayed reclamation, fragmentation, mapped resources or unexpected ownership.

Correlate pauses and completion delays with allocation/collection activity, JIT transitions, page behavior and the runtime's scheduling. A low retained footprint can coexist with expensive churn; a larger bounded cache can remove repeated work. Choose the experiment according to the user-visible constraint.

## Explore with controlled state changes

- Hold completed work fixed and vary repetition count or lifetime transitions. Test whether growth stabilizes, follows retained owners or continues after the supposed release boundary.
- Vary working-set shape, reuse distance or object lifetime while keeping semantics equivalent. Examine whether the response follows churn, locality or pressure.
- Compare pooling/caching/batching with controls that expose retained-state cost, contention and invalidation behavior. Trace where the saved work moves.
- Compare cold and warmed runtime states, then inspect generated-code/deoptimization or compilation activity when the difference suggests a runtime transition.

For native or mixed runtimes, follow ownership across language/FFI/device boundaries rather than assuming the visible heap owns every allocation. Under memory limits, examine the coupling between reclamation, paging, concurrency and latency before changing a heap limit.

## Instrumentation leads

Choose allocation profiles, comparable heap snapshots, retaining paths, allocator/page diagnostics and GC/JIT/runtime event traces as needed. Candidates include the runtime's native tooling, browser memory tools, JFR, .NET diagnostics, allocator profilers or platform memory instruments. Heavy snapshots and forced collection can change the behavior; use them as separate diagnostic interventions when appropriate.

Validate a lifetime fix by exercising acquisition/release and a surviving owner or later operation. Validate an allocation optimization against completion and sustained behavior, not merely fewer sampled allocations.
