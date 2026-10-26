# Agent Note: Native game creation with progressive human feedback

Status: implemented — Art Creation routes game requests to native Godot experiments and a reusable preview helper; enforced orchestration remains a documented proposal.

## Problem

The creative bundle handles visual analysis and iterative alternatives, but it lacks a native playable route for testing game behavior and collecting small player decisions. A browser-only game prototype would require a separate implementation when moving into the intended engine. Remote authoring also needs an actual playable delivery path.

Application setup and display guidance also need a shared entry point so a selected method produces something the user can actually inspect and respond to before substantial work accumulates.

## Decision

Add a concise [game capability](../../../../skills/art-creation/references/game-creation.md) and [engine method](../../../../skills/art-creation/methods/game-engine/SKILL.md). Follow player intent through observable hypotheses, native experiments, short build-linked responses and retained decisions. Reuse existing art methods for assets and inspect their behavior in the game.

Make [feedback setup](../../../../skills/art-creation/references/feedback-setup.md) a shared prerequisite in the skill entry. Reuse a working setup, read only the selected route, and expand capabilities with the current decision. Continue atomic decomposition, alternative construction, short human responses and progressive refinement through that path. Carry the viewing and response route through the method contract. Native game preview can use local execution, compatible Web export or streaming; [Selkies guidance](../../../../skills/art-creation/methods/game-engine/references/selkies.md) separates runtime, display, encoding, delivery and response verification in a reusable application session.

Provide a Python standard-library helper and a native Godot starter with movement, collisions, objectives and feedback controls. Check/import and export the same project to Web or Linux. Serve exported artifacts with the appropriate MIME type, optional HTTPS and optional cross-origin isolation. Preserve build directories and file hashes; keep machine-specific services, certificates and runtime builds outside the repository.

Extend the existing resource inventory and English-language checks to native Godot files. Existing static CI discovers the helper tests; it runs no model generation. [Research and workflow design](../../../../docs/game-creation.md) document the inspected AutoBulider frontend, relevant game-design practice, and Temporal/LangGraph/XState alternatives. Application-enforced transitions are a future layer.

## Alternatives considered

- HTML game prototype followed by engine migration: duplicates behavior and scene implementation instead of preserving one project.
- A separate top-level game skill: duplicates the existing intent, comparison, feedback and art-method routes; a progressively disclosed branch keeps them connected.
- A fixed questionnaire and full tool-stack setup: front-loads decisions and capabilities. Progressive setup and focused experiments follow the current question.
- A complete Temporal workflow service: requires durable application contracts. The current scope provides engine operations and a design proposal for that layer.
- Requiring Web export for every browser preview: narrows game runtime features unnecessarily. Native application streaming offers another viewing route with its own latency and rendering conditions to validate.

## Consequences

The native starter demonstrates movement comparison and atomic feedback in editable scenes. Godot and matching export templates are external prerequisites for the relevant export target. Remote browser playback needs a client-trusted secure context, and target-device performance requires separate validation. The feedback controls retain reactions in memory until export; Web execution downloads JSON and native execution writes to a persistent application-data directory. A local Selkies session verifies native frames, input, audio delivery, feedback binding and restart persistence. Durable creative decisions and guarded workflow transitions belong to the future application described in the [design document](../../../../docs/game-creation.md#future-enforced-workflow).
