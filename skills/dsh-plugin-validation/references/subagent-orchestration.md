# Subagent orchestration for a large plugin audit

Use subagents to keep raw source out of the parent context. They are read-only
reviewers, not installers.

## Fan-out

| Child | Surface | Read only |
|---|---|---|
| A | `package.json` scripts, dependencies/lockfile, tarball/files, registry/provenance | yes |
| B | host source: routes/auth, child_process, filesystem, credentials | yes |
| C | client source: slots, HTML sinks, eval, postMessage, network, packaging | yes |
| D | patch/composition/capability diff and issue/advisory history, if requested | yes |

Spawn A-C in parallel for most audits; add D when composition or reported issues matter.
Do not spawn more than four, and do not nest subagents.

## Brief template

Give each child exactly:

```text
Repository: <absolute path>
Surface: <A/B/C/D>
Read-only. Do not edit, install, execute lifecycle scripts, or commit.
Inspect only the files for this surface. Cap at 40 files.
Return a JSON object:
{"surface":"...","findings":[{"severity":"critical|high|review","file":"...","line":0,
"evidence":"one line","why":"...","verify":"...","notVerified":"..."}],
"filesRead":["..."],"uncertain":["..."]}
Do not include secrets, raw prompts, or entire files.
```

The parent supplies no credentials and does not ask a child to run the plugin.

## Merge

- Deduplicate by `(file,line,pattern)`.
- Keep the highest severity only with concrete evidence; downgrade pattern-only hits.
- Cross-surface taint (e.g. credential in B + network sink in C) is a parent-level
  finding; children do not see each other's reports.
- Record `notVerified` from every child; never let a clean child imply a clean plugin.
- Final report cites file:line and says which surfaces were delegated.

## Failure handling

A child timeout or malformed report is an explicit incomplete surface, not "clean".
Retry once with a narrower file list; then report the gap. Do not let the parent read
the whole tree just to fill a missing report.
