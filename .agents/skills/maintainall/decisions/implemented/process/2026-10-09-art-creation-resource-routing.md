# Decision: Art Creation resource routing and optional execution

Status: implemented — compact domain/backend references, mechanical preview support and static resource validation are available; empirical claims remain scoped.

## Problem

Art Creation needs to support vague creative intent, clothing/avatar design, and application backends without accumulating incident-specific rules or forcing serial context growth. Resource discovery and executable detection are mechanical concerns; they should not depend on repeated guessing.

## Decision

Keep the two-capability entry and analysis output contract. Shorten [iterative creation](../../../../../../skills/art-creation/references/iterative-creation.md), add compact intent/evidence and optional delegation guidance, and route fashion/avatar, procedural-system, Blender, and Houdini details on demand through a [resource index](../../../../../../skills/art-creation/references/resource-index.md).

The standard-library [index checker](../../../../../../skills/art-creation/scripts/check_index.py) validates routing schemas, local links/heading anchors, resource types, uniqueness, bundle boundaries, and inventory coverage. The [runtime probe](../../../../../../skills/art-creation/scripts/probe_runtime.py) distinguishes executable detection from unverified control/render/export capabilities. [Regression checks](../../../../../../tests/skills/test_art_creation_helpers.py) and a [credential-free CI workflow](../../../../../../.github/workflows/art-creation-skill.yml) cover these contracts.

The optional [browser capture helper](../../../../../../skills/art-creation/scripts/capture_browser.py) captures actual local pages with an existing runtime and records its source, viewport, DOM, PNG and failure state; it neither installs a browser nor establishes playback. The optional [avatar runtime guide](../../../../../../skills/art-creation/references/avatar-runtimes.md) distinguishes Core model execution and exact VRM target acceptance.

Keep real incidents and project constants in research/project evidence or evaluation tasks. Delegation remains optional and includes output ownership and concise evidence handoff. The benchmark work uses bounded old/new tasks with the explicitly requested local Codex model, reusing an established sandbox rather than building a new one. Its isolated worktree and current status are tracked in the [research TODO](../../../../../../docs/research/art-creation-2026-10-09/TODO.md).

## Alternatives considered

- Import complete backend or avatar skill bundles: broad coverage carries unverified dependencies, platform defaults, and unnecessary context.
- Add a rule for every observed incident: encodes one project instead of enabling interpretation and alternative mechanisms.
- Require subagents: imposes coordination cost even on small tasks and does not establish total efficiency.
- Depend only on documentation links: leaves stale routing, missing inventory, and guessed runtime capabilities undetected.
- Require a large benchmark before editing: delays testing uncertain ideas; bounded paired tasks can establish the initial feedback loop.

## Consequences

Guidance is English, optional resources stay outside the frequent path, and no per-line prose limit is introduced. The analysis still produces the requested two chapters. Static checks cannot certify preference, external URLs, production applications, or empirical model improvement. Under the user's explicit installation authorization, official Blender and Live2D Web SDK plus a pinned browser VRM target were installed in user-local runtime directories. The user-provided Houdini 22.0.466 installation now has a legitimate Apprentice license and an enabled user-level license service; actual SOP/VEX generation, native Mantra rendering, and independent scene/cache readback passed. Required SHFS assets passed manifest checksum verification and the native GUI loaded using a task-local CPU OpenCL configuration. These application settings stay outside the reusable skill. Current model/render/source/export/pose evidence is recorded in [runtime verification](../../../../../../docs/research/art-creation-2026-10-09/runtime-validation.md). Installation does not establish a complete garment or live-tracking production pipeline. No applications are installed merely because the skill is loaded.
