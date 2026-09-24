---
name: model-policy
description: Use when adapting MaintainAll development skills to a known model and reasoning configuration, selecting task-appropriate execution guidance, or maintaining model evidence. Model policy index - model-policy/registry.json.
---

# Model Policy

Use [registry.json](registry.json) as the single source for model identities,
reasoning variants, task tiers, profiles, supplements, sources and skill mappings.
Read [methodology.md](methodology.md) for evidence review and packaging details.

1. Resolve the requested development skill by its exact name. Obtain the model ID
   and actual reasoning configuration from the host or caller; never guess your
   identity from writing style. Unknown identity/configuration stays unassessed.
2. Use the helper below, or read the matching registry records manually when a
   shell is unavailable. Paths are relative to this skill, not the user's cwd.

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
