# Model Tiers and Skill Adaptation

Research snapshot: 2026-09-24. `registry.json` is the only normative model index.
This document explains the method without maintaining a second ranking table.

## Contents

- Discovery and resource location
- Identity and tiers
- Initial evidence status
- Evidence channels
- Promotion, conflicts and expiry
- Adaptation and distribution

## Discovery and resource location

Skill-aware hosts generally index name/description and load the body when a task
matches or a user invokes the skill. A description is not a resource resolver or
a model-switching API. See [OpenAI Skills](https://developers.openai.com/plugins/concepts/skills).

Development skill descriptions identify the shared index by the **skill name**
`model-policy`. Each body supplies the bootstrap rules:

1. Prefer the host catalog entry whose frontmatter name is `model-policy`. Open its
   exact supplied location with its supplied reader. Catalog entries may use renamed
   folders, virtual resources or provider-specific URIs; do not invent filesystem paths.
2. If there is no catalog entry, a normal filesystem installation may use
   `../model-policy/SKILL.md` relative to the current skill's resolved `SKILL.md` location.
   Resolve symlinks before applying this fallback. Never resolve it against the shell cwd.
3. Once the policy skill is loaded, `registry.json`, `methodology.md` and
   `scripts/resolve.py` are relative to **that policy skill's location**. Use the same
   provider/reader for its resources. The filesystem CLI anchors its default registry
   to `__file__`, not cwd.
4. A host that neither exposes dependency locations nor preserves the sibling layout
   cannot guarantee discovery. If the policy/index is missing or inaccessible, report
   unavailable adaptation and continue with bounded steps and observable checks. Do not
   claim a tier, search unrelated directories or install a substitute automatically.

This policy maps the ten development skills under `skills/`. The AIOps skills in
`.agents/skills/` and the deployment skill in `deploy/compute-use/skills/` have separate
purposes. This PR does not integrate policy execution into the TUI loader or change
its model settings or permissions.

## Identity and tiers

Evaluate a model snapshot, provider/endpoint, native reasoning configuration and task
as one configuration. Reproducible experiments also pin prompt/skill Git SHA, harness,
tool permissions, context length, sampling settings and token/time budgets. Local
models additionally require weight/tokenizer revisions, precision, engine and hardware.

- `U`: unassessed, unknown or expired; use scaffolded guidance without claiming weakness.
- `T1`: bounded tasks with explicit contracts and intermediate checks.
- `T2`: multi-step implementation/integration with checks at component boundaries.
- `T3`: complex diagnosis/design/review with competing hypotheses and independent evidence.

These are MaintainAll engineering categories, not human IQ or vendor marketing tiers.
Record total and active parameters separately. Unknown proprietary sizes stay null.
Do not infer capability from size, price, brand or writing style. Precision and serving
conditions can affect quality and latency.

Native reasoning controls are not interchangeable: OpenAI effort, Qwen enable_thinking,
and other providers' modes/budgets are different axes. Missing configuration stays U;
a high-effort result does not establish low-effort performance. Supported values and
defaults are model-dependent; see [OpenAI reasoning](https://developers.openai.com/api/docs/guides/reasoning).

## Initial evidence status

The six models and ten configurations are **provisional candidates or unassessed
records**, not a measured ranking. The JSON contains task tiers, size, configuration,
rationale and sources for OpenAI Sol, DeepSeek, different Qwen sizes and a historical
GPT-5.4 anchor. Higher-effort candidate tiers are hypotheses, not proven improvements.

Only two clearly readable AA composite observations were imported. They do not directly
establish coding, review or tool-use capability. Missing sample counts, confidence
intervals and per-task metrics remain null. No local or paid model evaluation ran.
`observed_at` is the source snapshot date; `measured_at` is the actual evaluation date,
which remains null when undisclosed. Reading a page does not rerun its benchmarks.

The Qwen comparison did not expose reliable per-task values. Arena methodology was
checked, but no community observations attributable to these exact configurations were
imported. Empty evidence fields remain empty; v1 cannot certify calibrated performance.

DeepSeek documents that `deepseek-v4-flash` is now a legacy alias served by V4.1 Flash.
The resolver deliberately does not silently map that old name. Verify the actual version.
The thinking-configuration page could not be retrieved in the research pass, so its API
parameter spelling was not invented; AA's max label is a benchmark configuration label.
See [DeepSeek model details](https://api-docs.deepseek.com/quick_start/pricing/).

## Evidence channels

Registering a source does not mean results for a particular model were captured.

| Direction | Preferred evidence | Limits |
|---|---|---|
| Local coding/tests | [LiveCodeBench](https://livecodebench.github.io/) and local behavior tests | Contest problems do not establish repository maintenance skill |
| Repository repair/debugging | [SWE-bench](https://www.swebench.com/index.html) and local failures | Keep subsets, agents and budgets separate |
| Terminal/multi-step execution | [Terminal-Bench](https://www.tbench.ai/) and sandbox tasks | Results describe a model-agent combination |
| Tool/structured output | [BFCL](https://gorilla.cs.berkeley.edu/leaderboard) and schema/recovery tests | Separate native function calling from prompted formats |
| Reasoning/instructions/documents | [LiveBench](https://github.com/LiveBench/LiveBench) and [AA methodology](https://artificialanalysis.ai/methodology/intelligence-benchmarking) | Reposts of one benchmark are not independent evidence |
| User experience | [Arena methodology](https://arena.ai/blog/arena-rank) and reproducible community traces | Preference and fluency are not executable correctness |
| Skill adaptation | Paired no-skill/base-skill/adapted-skill holdouts | Do not claim generalization on prompt-tuning samples |

Review evaluation needs both known-defect and defect-free samples, with detection,
false-positive and severity metrics. Architecture tasks need a predefined rubric and
independent human review rather than a single universal leaderboard score.

## Promotion, conflicts and expiry

These are future calibration requirements. The v1 helper only resolves a static policy.

1. For each task, obtain relevant results from at least two independent evaluation
   organizations. Vendor documentation establishes specifications, not a second
   independent performance measurement. Preserve raw values, units, direction,
   benchmark version, configuration, dates and harness.
2. Keep different benchmark versions/configurations separate. Never average Elo,
   pass rates and composite indexes directly. Any aggregate must fix the reference
   cohort/time window, normalize only comparable groups, and disclose weights and
   missing coverage. Prefer task vectors and quality/cost/latency Pareto comparisons.
   Missing evidence is neither zero nor permission to inflate other weights.
3. Initially require at least 30 independent local cases per direction, repeated three
   times. Cluster 95% intervals by case; repeated calls are not independent samples.
   These are proposed project thresholds to calibrate, not industry standards.
4. Evaluate T1/T2/T3 on bounded, multi-component and complex-judgment difficulty sets.
   Pre-register quality, false-positive, cost and latency gates; allow no critical
   destructive failures. Passing easy cases alone cannot establish T3.
5. Community evidence needs URLs/dates, original prompts, environment, version,
   sample counts, reproducible traces and positive/negative observations. Deduplicate
   reposts and mark sponsorship/selection bias. Anonymous sentiment is an investigation
   lead; preference does not override objective correctness.
6. Preserve conflicts between public, community and local results. Investigate alias
   drift, tools and budgets, then expand paired validation. Use conservative guidance
   while unresolved; do not cherry-pick results or assert unproven contamination.
7. A record, source access, contributing observation snapshot or known measurement
   older than the JSON review window, or dated in the future, falls back to U. Alias
   or environment changes require immediate review even before time-based expiry.
8. Promote through a reviewed PR that records evidence, rationale and rollback version.
   The v1 validator rejects calibrated status; future integration must implement and
   review the evidence checks, not merely change a status string.

## Adaptation and distribution

Keep one core skill per workflow. Differences belong in JSON profiles, supplements and
additional_skills: scaffolded guidance adds explicit contracts and small experiments;
standard guidance works at component boundaries; analytical guidance compares hypotheses.
All profiles retain verification. Model-specific patches need reproductions and expiry
conditions. Missing context, tools or permissions must be addressed before model escalation.

Load additional skills by catalog name only at their applicable phase, once per task.
Keep an already-loaded set to prevent recursion. High risk always adds review guidance;
no tier overrides authorization, data protection or required tests.

From the repository root:

```bash
python3 skills/model-policy/scripts/resolve.py --validate
python3 skills/model-policy/scripts/resolve.py --check-install skills
python3 skills/model-policy/scripts/resolve.py --model gpt-6-sol --variant medium --skill systematic-debugging
python3 skills/model-policy/scripts/resolve.py --skill writing-skills
python3 -m unittest discover -s tests -p 'test_model_policy.py' -v
```

Use `--as-of` only to inspect a snapshot. Any date different from the real current
date returns `replay: true`, `evaluated_at` (the real date), and
`next_action: replay_only_not_for_execution`, with empty instructions, supplements
and additional skills. Its tier/profile describe the snapshot and must not guide
current execution. Replay evaluates the supplied registry at that date; it does
not retrieve an older registry revision. Rerun without `--as-of` to check current
expiry and obtain execution guidance. An explicit current date behaves like an
ordinary lookup. Manual readers must likewise use the real current date for active
guidance. Use a relevant `--task` override for roles such as reviewers, not to
obtain a higher tier.

For filesystem distribution, copy complete selected skill directories together with
model-policy and the referenced writing-plans/verification-before-completion dependencies.
Keep them as siblings, or ensure the host catalog exposes their exact names and locations.
Do not copy only SKILL.md. Preserve the full subagent template directory when included.
The installation check validates model-adaptation dependencies by frontmatter name, even
when directories have been renamed; it does not install anything or validate unrelated
workflow dependencies. Run it on the destination, not just the source tree.

For virtual/catalog-only hosts, the host must make the policy skill and its bundled
resources readable through the supplied reader. A filesystem check cannot prove that
host integration. Missing dependencies degrade explicitly instead of triggering a search
or download. Never silently install these development skills into the AIOps catalog.

Static tests establish lookup, dependency and fallback behavior, not model superiority or
empirical prompt improvements. The offline CLI requires Python 3.11+ and no API key.
