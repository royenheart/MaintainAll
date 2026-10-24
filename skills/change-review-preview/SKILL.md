---
name: change-review-preview
description: Use when preparing issue or pull-request drafts with diffs and reproducible evidence, building a local review preview, packaging review artifacts, or publishing already reviewed changes under the user's authorization. Shared model index is provided by the model-policy skill.
---

# Change Review Preview

## Model adaptation

Load `model-policy` once from its exact host catalog location and apply its repository scope and model guidance. Without a catalog entry, use the [sibling policy](../model-policy/SKILL.md) relative to this skill's resolved location. If unavailable, report that limitation and use bounded artifact checks with observable results.

Turn reviewed changes and evidence into material another person can inspect and reproduce. Distinguish drafting, local presentation and external publication. Use current conversation authorization, including approval already granted; a stale manifest flag does not override it.

## Prepare the review

Read current contribution guidance and issue/PR templates. Inspect the complete patch, including untracked files, against its intended base. Keep independent changes separate when requested. Preserve existing drafts, language and evidence while improving the requested material.

Lead with the observed problem and resulting behavior. Analyze performance alongside resource/lifecycle, correctness, cache/concurrency, interaction and compatibility changes. Use [review and publication](references/review-and-publication.md) for wording, evidence selection and remote checks.

Include reproduction/setup, complete helper dependencies, test commands/results, comparison data and visual proof appropriate to the claim. Preserve regressions and raw observations. Public instructions use portable paths and real public URLs; local reports use the host's clickable path convention.

## Build a preview when requested

Use [the manifest contract](references/manifest.md) with the bundled helper:

```sh
python3 scripts/review.py validate --manifest /path/to/review.json
python3 scripts/review.py serve --manifest /path/to/review.json --bind 127.0.0.1 --port 8787
python3 scripts/review.py pack --manifest /path/to/review.json --item scope-reset --output /path/to/scope-reset.zip
```

Resolve script paths against this skill directory. Keep artifacts in the requested location or external temporary storage. The helper reads listed drafts/patch/evidence, renders Markdown, shows source/diff/metrics views, and builds a verified ZIP. It has no Git or forge mutation endpoint. Default to loopback; bind to a LAN address when requested.

Inspect the rendered page: complete raw/copy text, intact fences/tables, readable images, usable source/diff views and the requested viewport. Keep local asset mapping separate from copied public Markdown. Pinned Markdown/sanitizer modules allow offline preview; licenses and sources ship with the assets.

## Publish within the requested scope

Previewing does not authorize push, issue/PR creation, uploads, deployment or contacting others. If publication is already requested, complete concrete checks and proceed without another routine approval round. Honor separate branches and the requested draft/ready mode.

Refresh relevant upstream code/issue states and verify the branch diff and evidence revision. Upload approved artifacts to an appropriate destination, substitute real URLs and issue references, and check host limits. Persist returned IDs/hashes outside the source patch so resumed work reconciles existing objects instead of duplicating them.

Verify remote heads, file sets, bodies, relationships, attachment hashes and rendered evidence. Inspect returned draft/open/closed states and update preview links/status accordingly. Preserve historical experiments and their raw data.
