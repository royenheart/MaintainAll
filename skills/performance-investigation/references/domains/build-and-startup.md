# Build and startup

## Reconstruct the dependency graph

Separate environment resolution, dependency discovery, generation, compilation, linking, packaging and process/application initialization. For incremental operations, identify what actually invalidates and reruns. For startup, distinguish reaching a ready signal from being able to complete the first useful operation.

Check build mode, toolchain, generated contracts, caches and dynamic discovery before comparing revisions. A stale declaration, missing artifact or different dependency closure can look like a performance regression or make a fast run incomplete.

## Explore graph and state sensitivity

- Compare clean, incremental, cache-hit and cache-miss paths intentionally. Change one source/input/dependency and observe invalidation, fan-out and critical tasks.
- Vary task parallelism within resource limits. Inspect scheduling, shared filesystem pressure, memory peaks and serialization instead of assuming more workers will shorten the critical path.
- Trace repeated imports, scans, resolution or initialization across processes. Reuse may be per process, workspace, service or request; test the actual lifetime boundary before introducing a cache or singleton.
- Separate compilation/initialization from the first real operation to detect deferred work. Exercise a later operation and a fresh process to check whether cost was eliminated or moved.

Use an isolated minimal reproducer to investigate a toolchain or dependency mechanism, then recheck the normal build/startup path. Optimize the graph or invalidation rule when it dominates rather than tuning an unrelated task's inner loop.

## Instrumentation leads

Look for native build traces, task/cache diagnostics, compiler timing reports, import/module-resolution traces and process/filesystem timelines. Build systems and runtimes often expose better dependency and invalidation evidence than a generic process profile. Use their help/current documentation to recover the actual graph and cache behavior.

Validate produced artifacts and the ready-to-use behavior. Preserve the environmental recipe so another run does not obtain its apparent speed from a missing step or an already populated cache.
