# Decision: Full version identities and semantic report colors

Status: implemented — visible version identities use exact hashes and report categories have distinct visual treatment.

## Problem

The primary commit controls coexist with a role-only baseline selector in More filters. Snapshot labels fall back to generic previous/candidate names, advanced version options can retain labels from another evaluation, and historical headings can incorrectly use the currently selected experiment's version. Outcome counts, execution metrics and requirement ratings lack sufficient visual separation. Repository-owned skill resources must remain English.

## Decision

The [report renderer](../../../../../../benchmarks/skill_bench/src/skill_bench/report_view.py) uses the [version identity helper](../../../../../../benchmarks/skill_bench/src/skill_bench/report_changes.py) for full generation-time Git SHA or frozen snapshot SHA-256 labels. The primary baseline control is authoritative; the redundant baseline selector is removed. The advanced skill-version filter is rebuilt from the selected experiment's actual arms whenever the run or commit pair changes. Role suffixes distinguish identical tested hashes without substituting a role name for an identity. Missing identities are explicit, and the no-skill arm remains a distinct absence of source rather than receiving a fabricated hash.

Comparison cards, evidence headers, original A/B-order explanations, diff panels and history entries show exact hashes. Historical rows resolve their own experiment or cohort identity. Commit-chart ticks remain abbreviated for layout, while the associated table and hover text show full SHAs. Technical presentation tables show identities; sealed public JSON retains protocol arm IDs and all original records. Report JSON and media are not changed by this presentation refresh.

Shared CSS tone tokens distinguish green positive results, slate neutral results, red negative results and amber unknown evidence. Outcome cards, metric boxes, status badges, requirement-rating cards and chart colors retain readable textual meanings. Candidate/baseline cards have separate blue/purple role accents. Numerical counts and ordinal judgments are not pooled into an overall score. Layout checks cover narrow screens, and outcome label/background contrast is measured at at least 4.5:1. HTML declares English and `translate="no"`; the application cannot control extensions that ignore that attribute.

The [language regression check](../../../../../../tests/skills/test_skill_language.py) scans repository-owned `skills/` and `.agents/skills/` text resources, including references, scripts, templates and decoded JSON strings. It detects CJK text without rejecting mathematical or typographic symbols. This is a deterministic guard for the observed language requirement, not a general natural-language classifier. Current repository resources and the installed art-creation bundle contain no CJK text. Frozen benchmark prompts and review reasons outside the skill bundles are not translated or modified. The [skill workflow](../../../../../../.github/workflows/art-creation-skill.yml) checks the guard on all repository-owned skill-path changes, using no model requests.

## Alternatives considered

- Retain duplicate baseline selectors and synchronize their role-only labels: adds another source of ambiguity; one authoritative full-identity comparison control is sufficient.
- Use only twelve-character identities everywhere: insufficient for exact inspection; full hashes are used in selectors and reading panels, with abbreviations limited to compact graph ticks backed by full details.
- Build advanced labels only at initial page load: becomes stale after selecting another run; labels are refreshed from current recorded inputs.
- Color every value according to an implied overall pass/fail: confuses task quality, execution and missing evidence; distinct categories retain their original definitions and counts.
- Translate sealed task/review data to satisfy the UI language: changes the evidence; only interface text and authored skill resources follow the English policy.
- Add LLM-based language review to CI: introduces authentication, cost and uncertain classifications; deterministic resource checks provide the required regression guard without new generation calls.

## Consequences

Long hashes wrap in version cards and historical details. Native select controls can visually clip long labels, but their options and tooltips retain the complete identity, and adjacent version cards display it in full. Existing commit provenance is not inferred, and old evaluations remain snapshots. The current report style remains a light paper layout with restrained category colors and borders.

The [version regressions](../../../../../../benchmarks/skill_bench/tests/test_skill_changes.py) reproduce the original generic/truncated labels and duplicate baseline selector before the fix. Browser checks inspect actual advanced-filter labels, verify synchronization across two commit-control fixtures, check category colors and contrast, exercise diff layouts and real case navigation, and load original shared images. Synthetic commit labels are limited to browser-memory QA and do not create public evaluation records. Language checks include plain reference/template text and escaped JSON. Report rendering and all checks make zero model calls.
