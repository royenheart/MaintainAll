---
name: performance-investigation
description: Use when investigating performance, designing repeatable experiments, finding bottlenecks across execution domains, or validating an optimization against real workload goals. Shared model index is provided by the model-policy skill.
---

# Performance Investigation

## Model adaptation

Load `model-policy` once from its exact host catalog location and apply its repository scope and model guidance. Without a catalog entry, use the [sibling policy](../model-policy/SKILL.md) relative to this skill's resolved location. If unavailable, use bounded experiments with observable checks and state the limitation.

## Frame the decision

Recover the workload, observable outcome, operating conditions and constraints from the request and system. Decide what would count as an improvement and which tradeoffs are allowed. Keep the user's objective separate from an initially suspected mechanism. Investigation need not produce a code change.

Map how work, data and waiting propagate through the actual system. Consider demand, algorithms, data layout, execution policy and shared resources as competing explanations. Ask what observation would disprove the current favorite before choosing instrumentation.

## Establish the testbed first

Before comparing fixes, build or repair the smallest repeatable testing foundation: compatible dependencies and build/runtime settings, representative inputs, a runnable path through the relevant system, result checks, collection boundaries and a cleanup recipe. Use [testbed and dependencies](references/testbed.md). Establish a working baseline and verify that the harness itself can detect a meaningful change. Reuse existing infrastructure and grow it as the investigation requires; do not turn setup into a separate framework project.

## Explore through discriminating experiments

Use [experiment design](references/experiments.md) to choose perturbations, comparisons and controls. Start with broad localization, then spend detail where it can change a decision. Select the next experiment for its information value, cost and risk rather than following a fixed profiler sequence.

Keep a compact working account of the hypothesis, expected observation, result and next decision. Revise the system model when evidence disagrees. Deliberately test alternatives and interactions instead of accumulating evidence only for the first explanation.

## Load domain methods as the evidence leads

Read the [domain index](references/domains/index.md), then only the guides relevant to the current execution boundary. Combine or switch guides when the bottleneck crosses layers. The index is a starting map, not an exhaustive taxonomy or a checklist to run in full.

Domain guides supply experimental lenses and useful tool capabilities. Discover the installed tools and the target system's own diagnostics; use their help and current documentation for operation. Choose or adapt instrumentation to answer the question rather than requiring a particular brand of tool. For an unfamiliar domain, derive a workload model and identify the observations needed to distinguish its mechanisms.

## Close the causal loop

Use a counterfactual change, supported by independent signals, to test the proposed explanation. Where useful, estimate the maximum improvement available from that mechanism. Investigate migration of cost to another phase, resource, participant or workload before calling the result a system improvement.

If a fix is requested, preserve the relevant functional contract and rerun the real workload plus affected controls. For upstream coverage and behavior changes, use [upstream and scope](references/upstream-and-scope.md). Reuse valid evidence when source and conditions are unchanged; remeasure what a revision invalidates.

Preserve raw evidence and the conditions needed to reproduce the conclusion. Read [evidence integrity](references/evidence-integrity.md) when validating captures, attributing profiles or transforming data. Explain the observed effect, mechanism, remaining uncertainty and next useful decision without filling the report with generic caveats. Use [Change Review Preview](../change-review-preview/SKILL.md) when review material is requested.
