# Art creation task suite

The core [suite](suite.json) freezes eight three-turn cases: six development cases and two holdouts. The [trajectory suite](trajectory/suite.json) adds three development cases abstracted from actual user feedback. The [expanded suite](expanded/README.md) adds 16 cases: 12 development and four holdouts covering reference transfer, editorial hierarchy, costume/avatar planning, procedural rules, responsive state, interrupted motion and native spatial relationships. The combined inventory is 27 cases, 21 development and six holdouts. These are three frozen datasets, not 27 recorded model evaluations. Holdout prompts and rubrics are evaluator-side task data; do not load them while modifying a skill. Their use after release is recorded in the experiment manifest. This is a MaintainAll task suite, not a reproduction of GenEval, T2I-CompBench or other published benchmark results.

The [original-session expansion](session-expansion/README.md) separately indexes nine additional local-private task definitions using 29 exact original attachments from two sessions. They are development data whose execution and review records remain local. Browser cases use independent action evidence, with controlled audio probes where declared. Their original-reference input conditions remain separate from the public schematic tasks; the existing 27-case suite files are unchanged.

Each case links every rating atom to exact text in the delivered prompt and to the turns where that requirement is already known. Artifact filenames and observable evidence are declared separately. A future correction cannot create an earlier failure retroactively. The legacy editorial and costume prompts are preserved after JSON decoding; their new rubric is version 2, so its scores must not be pooled with the old pilot's rubric.

The four Met Open Access photographs retain the exact previously downloaded bytes and SHA-256 values. They are public-domain object images distributed under CC0; the object pages and official API metadata are indexed in [asset provenance](assets/manifest.json). The original photographs are actual solver inputs, not regenerated approximations. The trajectory suite instead uses original, labeled schematic replacements under CC0. Those diagrams illustrate the abstract brief and are explicitly different from the original session references.

Private original-session messages, screenshots, sketches and hash/line evidence remain outside Git. The private suite has different reference inputs and an `original_session_context` capability gate because the original site's state is not packaged. It cannot be pooled with the public schematic variant or presented as a faithful replay of the original user's site. Both derived variants are development data: the session has already informed skill improvements, and synthetic staged feedback is not a new user acceptance.

The [calibration manifest](calibration/manifest.json) covers two trusted positive/negative geometric pairs, plus color invariance. It controls equal element/text counts while changing baseline proximity or physical anchor contact. Counts are nuisance controls, never aesthetic scores. These checks establish that the small relation measurer detects its supported counterfactuals; they do not validate a general visual judge. [Measurement templates](measurements.json) specify the evidence needed before any quantitative relation can be used on a real task.

Backend capabilities gate execution. Native 3D requires Blender and independent scene reopening; interaction and motion require actual browser capture/playback. A missing backend is reported as unavailable, not silently replaced with a static SVG. Mechanical delivery can pass while quality is unassessed, source editability unverified or an individual atom unverifiable. The solver's notes and self-assessments cannot create quality ratings.

Offline checks from the repository root:

```sh
PYTHONPATH=benchmarks/skill_bench/src uv run --no-project --python 3.13 --with jsonschema==4.25.1 python -m skill_bench.cli validate --suite benchmarks/art_creation/suite.json
PYTHONPATH=benchmarks/skill_bench/src uv run --no-project --python 3.13 --with jsonschema==4.25.1 python -m skill_bench.cli validate --suite benchmarks/art_creation/trajectory/suite.json
PYTHONPATH=benchmarks/skill_bench/src uv run --no-project --python 3.13 --with jsonschema==4.25.1 python -m skill_bench.cli validate --suite benchmarks/art_creation/expanded/suite.json
PYTHONPATH=benchmarks/skill_bench/src uv run --no-project --python 3.13 --with jsonschema==4.25.1 python -m unittest discover -s benchmarks/skill_bench/tests -v
```

Use `python -m skill_bench.trajectory --help` for private extraction. The extractor reads only `response_item` user-message blocks, preserves original line and content hashes, and refuses output inside a Git working tree. It excludes assistant/tool output and does not aggregate inherited token usage. It neither fetches unknown external image URLs nor invents missing attachments.

Public trajectory provenance uses `source_session_sha256` and `source_thread_sha256` instead of raw session or thread identifiers. The original identifier mapping, messages and reference attachments stay outside Git; public replacements do not establish a faithful replay of the original application state.

Historical v1 pilots can be adapted with `python -m skill_bench.cli import-legacy --source <private-v1-run> --output <new-private-run>`. The adapter preserves the old rubric, source state, prompts and recorded normalized usage. It never replaces the original files, sums cumulative totals or imports old quality as new anonymous review. Historical quote alignment and absent properties remain unknown; these cases do not satisfy the new v2 requirement-link contract retroactively. Their content/runtime/rubric fingerprints keep them distinct from current tasks.
