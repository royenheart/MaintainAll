# GPU and accelerators

## Reconstruct the host/device pipeline

Map input preparation, compilation, submission, transfers, kernels, synchronization and consumption of results. Align host and device activity before deciding whether to optimize a kernel. Device gaps can originate in the producer, allocator, dependency graph, communication or launch schedule.

Establish the completion event required by the workload. Submission timing can conceal unfinished device work; forcing global synchronization around every operation can destroy the overlap being investigated. Choose a timing/capture boundary that preserves the behavior in question, and keep isolated-kernel experiments separate from pipeline throughput.

## Discriminate the limiting mechanism

- Vary shape, batch, sequence length, precision or layout within the allowed result-quality contract. Look for regime changes, compilation specialization, padding and dispatch choices rather than averaging incompatible cases.
- Vary transfer volume or input-production rate while keeping device work comparable. Check whether gaps or stalls follow the producer, movement or compute stage.
- Compare an operator in isolation with the same operator in its stream/graph context. Investigate launch overhead, fusion, dependencies and overlap when isolated improvements disappear in the full workload.
- Vary concurrency, placement or device count and account for communication and imbalance. Examine individual participants and critical collectives rather than only aggregate utilization.

Relate kernel behavior to a plausible compute/movement ceiling for the actual shape and architecture. Use detailed kernel evidence to choose changes to reuse, tiling, layout, fusion or execution policy; a single occupancy or utilization reading is not the optimization objective.

For model workloads, include input/output distribution, batching/admission policy, cache state and quality constraints. For graphics or interactive workloads, relate device work to frame dependencies and presentation. Preserve the relevant latency/throughput tradeoff.

## Instrumentation leads

Start with a host/device system timeline, then use kernel-level or framework attribution where it resolves the question. Examples include [Nsight Systems](https://docs.nvidia.com/nsight-systems/UserGuide/index.html), Nsight Compute, ROCm profiling tools and framework profilers; graphics may need a frame capture or GPU scheduling view. Verify device/driver support and capture effects in the actual environment. Focus capture on relevant phases rather than collecting every available metric.
