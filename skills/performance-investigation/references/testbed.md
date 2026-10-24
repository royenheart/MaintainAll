# Testbed and dependencies

## Make the investigation runnable before optimizing

Begin with the system's existing test, benchmark, deployment and observability paths. Establish the minimum dependency closure for the actual operation: build products and symbols, runtimes and packages, device/driver compatibility, service versions, data/configuration and collection access. Resolve the setup that the chosen experiment needs rather than installing every available profiler.

Reconstruct the intended execution environment, not merely one that starts. A development renderer, instrumented runtime, CPU fallback, emulated device or substitute backend can exercise a different path. Confirm the selected implementation, device, precision, feature flags, topology and process/service identity before accepting a baseline. Record environmental differences that affect the comparison.

Use existing authorization for routine setup and isolated resources. Ask for specific missing access or configuration when required, and continue independent analysis. An unavailable counter or collector is a reason to choose another observation or report a gap, not to substitute an invented measurement.

## Build a thin experiment adapter

Make the workload runnable from a known initial state with inputs, operation boundaries and a result check. Separate fixture creation, warmup, timed work, validation and teardown when their costs answer different questions. The adapter should support repeating the baseline and candidate with controlled changes and retaining raw results. A small script around the real program is often sufficient.

Choose data for the mechanism: size, shape, cardinality, skew, locality, reuse, concurrency and arrival pattern can matter more than total volume. Include a representative operating case and the case that amplifies the suspected cause. Keep generated or padded stress cases distinguishable from ordinary traffic. Preserve semantic properties such as ordering, eligibility, numerical tolerance and completion criteria.

Use real dependencies for acceptance of a system-level claim. A controllable substitute can isolate an expensive or unavailable boundary, but keep its question and evidence separate. For hardware experiments, establish device completion and validation; for asynchronous services or UI, define the observable state reached, not merely submission of work.

## Check the measuring system

Run a baseline smoke before a long matrix. Verify successful work, matching outputs, expected request/process/device activity, capture coverage and usable raw output. Check timing resolution, clock relationships, background load and whether repeated runs are stable enough for the decision.

Try a known perturbation or control when feasible: add identifiable work, reduce the workload, bypass a stage, or run an unchanged path. Confirm that the harness notices the intended effect and does not count setup, polling, cached failure or incomplete work as success. Check that the load generator and collector are not the limiting participants.

A setup failure is not a performance observation. Preserve enough diagnostic context to fix it, then start a coherent measurement cohort. Keep versions, configurations and source/data identities with the run recipe so a later successful run does not silently replace a different experiment.

## Scale the foundation with the question

Start with low-cost localization and short bounded captures. Add scenarios, detailed counters, source maps/symbols or another host only when they discriminate remaining explanations. Avoid building dashboards, universal runners or persistent instrumentation before the basic experiment works.

Coordinate resource use across workers and hosts. Reserve headroom for fixtures, compilation, browser/device processes and capture storage; serialize competing heavy jobs when needed. Do not confuse worker count with an actual concurrency budget. Reuse exact-source results instead of rerunning expensive experiments for prose or packaging edits.

Track the specific processes, ports, devices, fixture roots and remote resources the testbed owns. Teardown should release those resources and preserve user services/configuration. Keep portable setup/run/cleanup instructions and raw results in the requested artifact location.
