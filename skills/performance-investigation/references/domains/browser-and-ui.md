# Browser and UI

## Begin with an interaction or loading journey

Mark the user's action and the state that makes the result usable. Reconstruct dispatch, network/cache, application state, framework work, layout, rendering and presentation as relevant. Separate initial loading, cached reopen, update, scrolling and recovery when their paths differ.

Check the actual build, browser/device, viewport and wrapper configuration. Development/runtime instrumentation, headless execution and automation recording can change scheduling and framework behavior. Preserve the deployment path needed for the claim, including native shells or desktop main/preload/renderer boundaries when present.

## Use experiments to localize the delay

- Supply an immediate deterministic response or replay a captured payload to isolate client work, then confirm the normal end-to-end path. Separate reduced network demand from faster response handling.
- Scale rendered content and state-update frequency independently. Investigate identity, invalidation, repeated computation and mounted work before assuming a framework or graphics bottleneck.
- Vary viewport, visibility and rendering strategy while checking focus, reachability, scrolling and interaction semantics. A smaller DOM or fewer commits is useful evidence but not the completion criterion.
- Inspect request/cache/service-worker and resource dependency chains when loading dominates; inspect event-to-presentation and frame activity when runtime interaction dominates.

Use system timelines and framework attribution together. Framework commit time, script work, layout, raster/compositor and presentation can overlap or occur in different participants. Follow the chain that delays the interaction rather than optimizing the largest unrelated trace region.

## Instrumentation leads

[Browser performance traces](https://developer.chrome.com/docs/devtools/performance), Performance APIs, framework profilers and platform UI/compositor traces provide different views. WebPageTest/Lighthouse or real-user telemetry can identify workload regions; browser automation can replay a controlled journey. Choose what answers the current question, correlate source maps/marks, and inspect recording overhead. Consult the installed browser/framework tooling for collection details rather than assuming a fixed event set.

Confirm representative interaction and visual behavior after an intervention. Preserve observation boundaries and keep automation polling or post-response assertions distinct from actual presentation timing.
