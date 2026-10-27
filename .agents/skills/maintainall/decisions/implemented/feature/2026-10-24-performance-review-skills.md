# Decision: Reusable performance investigation and change review

Status: implemented — separate development skills own performance evidence and local issue/PR review, with a manifest-driven offline preview helper.

## Problem

Component speedups, profiler samples and end-to-end latency describe different boundaries. Repeated investigations can overstate impact, miss changes to candidate reachability or concurrency semantics, and preserve a polished summary while losing the source needed to reproduce it. Review material also needs a reusable presentation path without importing one project's filesystem, accounts, ports or publishing decisions.

## Decision

[Performance Investigation](../../../../../../skills/performance-investigation/SKILL.md) owns a general investigation loop: frame the decision, establish a runnable testbed and dependencies, discriminate competing mechanisms, and validate the causal explanation. The root links shared experiment/evidence methods and a [domain index](../../../../../../skills/performance-investigation/references/domains/index.md). Domain guides cover CPU, accelerators, runtimes, UI, services, storage, networks and build/startup through experimental choices and attribution methods. The agent loads only relevant guides, crosses boundaries as evidence requires and derives a method for unlisted domains. Tools are discovery leads; their operational help remains with their own documentation.

[Change Review Preview](../../../../../../skills/change-review-preview/SKILL.md) owns public copy, evidence packaging, review presentation and verification of an authorized publication. Its Python helper validates an explicit relative-path/hash manifest, serves listed artifacts through a read-only HTTP site, and packages complete selected files. The browser shows rendered/raw drafts, a patch, source/evidence and optional scoped measurements. Numeric metrics are transported as strings and raw dataset files remain unchanged. Large evidence is downloaded instead of automatically loaded into the DOM.

The preview uses pinned unmodified Marked and DOMPurify distributions with their licenses for offline Markdown rendering. It contains no checkout, benchmark, credential, upload or forge-write operation. Publishing guidance uses current conversation authorization and returned remote IDs instead of a stale approval flag or a project-specific publisher.

The bundle privacy review covers authored guidance, helpers, tests, metadata and packaged resources. Examples use portable placeholders or loopback addresses; vendor sources and license attribution remain intact. HTTP failures return a neutral message because filesystem exceptions and validation messages can contain absolute paths or private manifest values. Detailed diagnostics stay in the local validation command.

Both skills retain this development collection's model-policy integration. Registry entries describe proposed task minima, not a new measured model ranking. The existing host installation is not changed.

## Alternatives considered

- **One combined investigation-to-publication skill:** would load forge/preview details for a performance diagnosis and profiling details for an ordinary code review. Separate entrypoints can be selected independently and cross-reference the relevant phase.
- **Only append instructions to systematic debugging:** useful for shared diagnosis principles, but insufficient for metric interpretation, evidence packaging and a working review UI. General debugging guidance remains with its existing owner.
- **Make one application investigation the universal workflow:** preserves useful examples but overfits execution boundaries and misses accelerator, runtime, data and distributed-system questions. A testbed-first core and indexed domain methods retain the transferable reasoning without prescribing one architecture.
- **Put a performance glossary and tool cookbook in the root skill:** spends context on established concepts and tool syntax while obscuring how to choose an experiment. Progressive guides instead connect competing explanations, controlled perturbations and observations that change the next decision.
- **Copy the original project-specific preview and publication scripts:** preserves hard-coded paths, provider assumptions, remote accounts and irreversible network actions. The helper instead consumes a portable artifact manifest and leaves publication to an explicitly authorized workflow.
- **Use CDN Markdown modules or a handwritten Markdown parser:** a CDN prevents offline review; an ad hoc parser risks changing fences, tables or raw source. Small pinned licensed modules retain the required rendering behavior.
- **Build a generic forge publisher into the helper:** adds platform credentials, limits and mutation recovery to a local reader. The publication reference captures the reusable verification rules without adding those operations.
- **Return raw exceptions to preview clients for diagnosis:** convenient during setup, but file errors and invalid configuration can reveal local paths or private values over a requested LAN binding. A neutral HTTP error and local validation retain a diagnostic path without copying those details into the page.

## Consequences

Distribute complete skill directories and the collection's model-policy dependencies. Domain methods are a starting map rather than a mandatory test matrix; the testbed grows with the unresolved question and available resource budget. Drafts, fixtures, captures, archives and runtime logs stay in the chosen output location. Focused helper tests exercise path/hash boundaries, byte-preserving packaging, large counters and the read-only HTTP surface; browser acceptance checks the real rendered fixture. [Review scenarios](../../../../../../tests/skills/performance-review-scenarios.md) define future behavioral evaluations, including testbed readiness and cross-domain experiment selection, and do not claim measured model improvement.
