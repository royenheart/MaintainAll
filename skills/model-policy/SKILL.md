---
name: model-policy
description: Use when adapting MaintainAll development skills to a known model and reasoning configuration, selecting task-appropriate execution guidance, or maintaining model evidence. Shared model index is provided by the model-policy skill.
---

# Model Policy

Use [registry.json](registry.json) as the single source for model identities,
reasoning variants, task tiers, profiles, supplements, sources and skill mappings.
Read [methodology.md](methodology.md) for evidence review and packaging details.

## Locate the index

The host catalog's location for the skill named `model-policy` is authoritative;
the folder need not be named model-policy. Resolve the resource links above relative
to this skill's supplied location using the same reader. For opaque/virtual URIs,
use the host's resource mechanism, not a guessed filesystem path.

For ordinary files, resolve this SKILL.md's real location (following symlinks);
the index is `registry.json` in that directory. The helper below independently
anchors its default index to its own script location. Neither uses the shell cwd.
If the index is missing or inaccessible, state that adaptation is unavailable
and use bounded steps with observable checks; never invent a tier or silently
retrieve another policy.

## Apply the policy

1. Resolve the requested development skill by its exact name. Obtain the model ID
   and actual reasoning configuration from the host or caller; never guess your
   identity from writing style. Unknown identity/configuration stays unassessed.
2. Use the helper below, or read the matching registry records manually when a
   shell is unavailable. Substitute the actual resolved filesystem directory for
   `<model-policy-dir>`; do not execute that placeholder or convert a virtual URI
   into a path. Resource-only hosts should read the JSON with their supplied reader.

   ```bash
   python3 <model-policy-dir>/scripts/resolve.py --model gpt-6-sol --variant medium --skill systematic-debugging
   ```

3. Apply the returned profile instructions and supplements to the original skill.
   Load additional skills only for their applicable phase, once per task; exclude
   skills already loaded to prevent recursive policy/skill loading.
4. Treat provisional tiers as starting hypotheses, never measured superiority.
   An unknown/stale configuration gets scaffolded guidance. Missing benchmark
   data does not mean a weak model and cannot justify fabricated rankings.
5. When a task exceeds the candidate tier, split it into bounded steps or ask the
   host for an available, authorized model/configuration with relevant evidence.
   Changing text cannot change the running model or reasoning effort. Preserve
   permissions and verification requirements at every tier.

Use `--risk high` for migrations, destructive operations, security boundaries or
broad cross-system changes. It adds review/rollback guidance without authorizing
the action. Cost, latency, privacy, modality, context length and tool availability
remain host constraints; this offline helper is not a scheduler or API adapter.

If this companion is missing, use explicit small steps and observable checks,
report that adaptation is unavailable, and continue authorized work. Do not fetch
or install a replacement automatically.

For filesystem bundles, run `python3 <model-policy-dir>/scripts/resolve.py
--check-install <installed-skills-root>` to check the model-adaptation dependencies
by frontmatter name. This catches missing policy resources and supporting skills;
it does not install them or prove a virtual host can read them.
