# Skill Benchmark

An isolated Python 3.13 framework for versioned tasks, explicit skill interventions, private execution evidence and independent review. Tasks, requirement dimensions and score definitions belong to each benchmark suite. The current measured dataset is art-creation; the execution and reporting framework supports other skill suites without mixing their results. Delivery, requirement judgments, source checks and usage remain separate.

## Multiple benchmark suites

The site has a benchmark navigation bar and one cumulative page per registered suite. Every suite owns its submitted experiments, case evidence and commit history. Source bundles are publication inputs; they do not also appear as duplicate navigation pages. A suite may contain several frozen dataset versions; changed tasks or scoring conditions still produce separate chart series. Suites share only the execution framework, report presentation and hash-addressed image storage. Report-directory names distinguish submitted bundles; experiment IDs need only be consistent within their suite.

The local restored collection uses a version 2 `reports.json`. The committed [result catalog](../results/catalog.json) additionally pins each downloadable package, report fingerprint and summary; `fetch-results` creates this local collection:

```json
{
  "schema_version": 2,
  "suites": [
    {"id": "art-creation", "title": "Art creation"},
    {"id": "code-review", "title": "Code review"}
  ],
  "reports": [
    {"id": "art-run", "title": "Art comparison", "path": "art-run", "suite_id": "art-creation"},
    {"id": "review-run", "title": "Review comparison", "path": "review-run", "suite_id": "code-review"}
  ]
}
```

This is a configuration example, not an additional measured dataset. Register a suite when its first independently exported public bundle is available. Add its frozen `benchmarks/<suite>/suite.json`, cases, assets, requirement anchors and capability declarations; plan with that suite and explicit skill inputs. Git-based planning requires `--skill-path skills/<skill-name>` so another skill cannot silently inherit art-creation snapshots. The catalog's logical suite ID is independent of the frozen dataset ID and fingerprint. Register later dataset versions under the same section when appropriate; fingerprints continue to isolate changed evaluation conditions.

Version 1 catalogs remain readable as one generic default suite. Generated site manifests use version 2 and validate every page's suite assignment and navigation against the catalog. The first registered suite retains `timeline/index.html` for existing preview links; later suites use `suite-<suite-id>/index.html`. Keep registry order stable. History directories and identities are reserved. There is no cross-suite quality chart or combined score.

The shared case contract supports up to three turns and an explicit artifact-format allowlist. Independent source reopening supports bounded SVG edits, sampled offline HTML playback, and native Blender reopen/edit checks; review exports accept hash-checked raster evidence. Other domains can use supported text/JSON/HTML/Python artifacts, their own requirement dimensions and trace/measurement evidence. Additional formats, source checks or application capabilities require corresponding contract, sandbox and verifier extensions. Registering a section alone does not prove a new domain's toolchain works.

Adding a skill suite within that contract needs its task data, scoring anchors, assets and catalog entries, followed by validation and publication; it does not need a per-skill HTML template. Names and unknown requirement dimensions come from the submitted records. A new scoring scale, specialized metric chart or interactive media viewer requires a shared schema/renderer extension. Existing two-suite regression fixtures verify navigation and result isolation; they are synthetic display tests, not a second measured skill benchmark.

## Install and validate

Run from the repository root:

```bash
uv sync --project benchmarks/skill_bench --frozen
uv run --no-sync --project benchmarks/skill_bench skill-bench validate --suite benchmarks/art_creation/suite.json
uv run --no-sync --project benchmarks/skill_bench python -m unittest discover -s benchmarks/skill_bench/tests -v
```

Optional browser integration tests use `SKILL_BENCH_TEST_CHROMIUM=/path/to/chrome`. Set it to a compatible installed Chromium executable when running those tests locally; the default offline test run skips them. Namespace and resource tests also require their declared Linux runtimes. Tests use synthetic user paths and session IDs.

Harbor is the preferred measured backend. The exact pinned installation has passed a native Job with three real user-turn steps and both backend doctors; local Codex remains an explicit compatibility lane with its own comparison cohort. Harbor is packaged as an optional dependency to keep offline/base installation separate from authenticated execution. The supported Harbor runtime is version `0.24.0` from exact Git source `d5ac1be17f575852eaf4fffc4072fd18481c209b`; the optional release lock is a dependency entry, not proof of that source. The adapter checks installation provenance and executing dependency bytes. A backend must pass its own capability and execution-boundary checks before an experiment can use it. An unsupported capability is an explicit result, not an inferred pass.

After installing that pinned source, execute the installed CLI directly or use `uv run --no-sync`; a regular sync/run can replace the source installation with the release lock and invalidate its provenance:

```bash
uv pip install --python benchmarks/skill_bench/.venv/bin/python \
  'git+https://github.com/harbor-framework/harbor.git@d5ac1be17f575852eaf4fffc4072fd18481c209b'
benchmarks/skill_bench/.venv/bin/skill-bench doctor --backend harbor
uv run --no-sync --project benchmarks/skill_bench skill-bench doctor --backend harbor
```

## Fixed-budget experiments

Use new private runtime directories outside a repository. The first release fixes `gpt-6.1-sol` with low reasoning effort; it does not infer model service revision, provider sampling seed or monetary cost.

```bash
uv run --no-sync --project benchmarks/skill_bench skill-bench doctor --backend harbor
uv run --no-sync --project benchmarks/skill_bench skill-bench plan \
  --suite benchmarks/art_creation/suite.json \
  --case editorial-transfer --case reference-costume \
  --previous /path/to/previous/art-creation --candidate /path/to/candidate/art-creation \
  --arms previous,candidate --repeats 1 --max-calls 12 --wall-seconds 5400 --timeout 600 \
  --model gpt-6.1-sol --effort low --backend harbor --seed 20261009 \
  --output /path/to/private/new-experiment
uv run --no-sync --project benchmarks/skill_bench skill-bench run --run /path/to/private/new-experiment --execute
```

For the baseline, use `--arms none,previous,candidate --repeats 3 --max-calls 54 --wall-seconds 10800`. The without-skill arm contains no skill snapshot. Each trial receives only its declared intervention and assets; exact thread continuation is private. The order seed counterbalances execution positions and is not a provider sampling seed.

Execution holds a nonblocking per-experiment process lock before doctor or trial writes. A concurrent launch is rejected, and closing the descriptor releases the lock on exit; the durable start ledger still prevents retries. Linked or special lock files are rejected. Native Harbor can write lifecycle progress before the CLI summary, so treat execution stdout as a log. Machine consumers use the sealed `manifest.json`, validated ledger, trial results and derived `state.json`, rather than assuming execution stdout is one JSON document.

## Anonymous artifact review

```bash
uv run --no-sync --project benchmarks/skill_bench skill-bench review \
  --run /path/to/private/new-experiment --output /path/to/new-review-packet \
  --seed 20261009 --view artifact-only
```

Open the packet's `index.html`. It presents actual references, randomized left/right entries, all available turns, original pixel size, prompt-linked rubrics and evidence checkboxes. Supply reviewer identity and class, reasons and evidence for every atom and paired outcome; download the review draft. A browser download is a draft, not a frozen or automatically accepted quality assessment. Import it through the CLI:

```bash
uv run --no-sync --project benchmarks/skill_bench skill-bench review \
  --run /path/to/private/new-experiment \
  --packet /path/to/new-review-packet --ratings /path/to/downloaded-ratings.json
```

Ratings use ordinal `0`, `1`, `2` or `unverifiable`; paired preferences use `win`, `tie`, `loss` or `undetermined`, relative to the left entry. Unknown is not zero. Every judgment needs a reason and an allowlisted evidence path plus SHA-256. Duplicate IDs, inapplicable turns, missing judgments and mismatched evidence are rejected. A frozen version cannot be overwritten; corrections create a new positive version.

The private mapping binds the complete anonymous packet fingerprint, including its prompts and rubric. Changing packet contents invalidates import; a reviewer cannot remove difficult atoms while preserving the original review identity. Reports accept only hash-verified frozen rating records from that run's private ratings directory.

A hash-chain-validated closed execution ledger permits planned trials with no sealed result. No reservation/start evidence produces `not_attempted`; an observed reservation/start without a result produces `interrupted`. Every planned turn then has hash-linked status metadata and no fabricated artifacts. Such atom ratings must remain `unverifiable`, and pairs involving a missing result must remain `undetermined`. A still-running ledger or any existing unsealed/tampered result rejects export. Planned trials/turns stay in coverage denominators; placeholder turns are not observed model turns.

`--view notes-process` adds only notes whose exact path and `kind: notes` are declared by the frozen current case turn and whose text passes privacy and explicit arm-label checks. Solver-provided `review_safe: true` cannot grant permission; legacy `review_safe: false` remains excluded. The artifact-only and process-assisted views remain different judge cohorts. Raw events, final responses and model self-scores are excluded. The private arm mapping, random seed and run-private blind key stay under the original run's private `reviews/` directory. Anonymous IDs use HMAC with that random key, so public packet fields cannot reveal a guessed arm. A repeated export is reproducible only with the same private key and seed. An independent agent must identify itself as an agent; it is not a human preference panel. Disclosure of having seen the arm map is mandatory.

Private cases require explicit `--allow-private` for local review, and the resulting packet is local-private. A private reference makes its derived previews private as well; public default export never copies either. Local-private packets and their user images must not be uploaded as public artifacts. Session-derived public tasks use declared replacement material instead of silently substituting an image while claiming it was the original.

## Reports and history

The public catalog contains submitted skill evaluations. Framework development pilots and compatibility checks stay in local implementation archives; neither their bundles nor records embedded in a previously merged report belong in public suite history. Excluding an implementation check does not exclude failures or insufficient evidence within a formal evaluation. Export each formal sealed run separately and append its bundle to the catalog when submitting results.

```bash
uv run --no-sync --project benchmarks/skill_bench skill-bench report \
  --run /path/to/private/new-experiment --output /path/to/new-public-report
uv run --no-sync --project benchmarks/skill_bench skill-bench report \
  --run /path/to/private/new-experiment --history /path/to/previous-public-reports \
  --output /path/to/new-history-report
```

The plain report is mechanically assessed and remains quality-unassessed. To include independent judgments, add `--review-packet /path/to/new-review-packet --ratings /path/to/private/new-experiment/reviews/ratings/<review-id>/v1.json`; repeat both flags together for additional reviewers.

Reports are standalone `index.html`, `report.json` and hash-addressed raster media. They contain no raw trajectories, credentials, thread UUIDs, solver workspace or executable SVG/HTML. Text is escaped and the HTML has a restrictive Content Security Policy without external resources. Media must match its immutable size/hash inventory; traversal, symbolic links, oversized files and changed hashes fail explicitly. The independent artifact validator checks exact trusted HTML rendering and the complete file allowlist without executing downloaded HTML.

Sealed solver files with invalid or unsupported preview contents are listed under `withheld_previews`, with the original SHA-256, size and a fixed `withheld_reason`; their image bytes are not exported. Reviewers can cite the hash-linked delivery/status metadata and keep visual claims unknown. This does not suppress path/hash/size/limit errors, which still reject the export. PNG uses the bounded static-lane container/pixel checker; other supported raster types have signature checks only and are not described as fully verified. Invalid input references or source-rebuild proof images remain errors.

Filters cover skill arm, model, effort, backend, case, rubric, judge, review version and repeat. Dimensions retain ordinal counts and evidence coverage. Delivery, preservation, editability and usage are shown separately. Efficiency also retains observed command executions, nonzero command exits and CLI warning/error item counts; these are not counts of all tool calls or provider requests. Counts remain unknown when any contributing turn lacks valid observations. Sample counts distinguish independent cases, case-repeat units, trials, turns and atom observations. Cohort fingerprints include skill bytes, model, backend, generation runtime, invocation mode, task, rubric, judge and stable mechanical/source-verifier identity, including the source runtime fingerprint. Generation runtime is hashed rather than exporting private renderer paths; missing runtime uses the experiment fingerprint or an experiment-specific unknown marker. Regrading preserves the generation record and starts a new cohort when its verifier changes; the regrade file ID itself does not create a new measurement condition. Exact cohort histories retain their original identities. Commit charts allow skill bytes to change while holding task, model, runtime, rubric, judge, budget, order seed and protocol constant. Publication assembles all catalogued experiments and verified historical image evidence, deduplicating identical records and rejecting conflicting execution or rating identities.

The offline data viewer opens the latest experiment and follows a numbered document outline: **1. Evaluation setup**, **2. Execution and review coverage**, **3. Candidate versus baseline** and **4. Inspect the case evidence**. **5. Evaluation history** appears only when multiple submitted evaluations are available under the selected conditions. Its contents list links to visible level-two chapter headings; level-three headings and case summaries use chapter-relative numbers. Filters and skill changes are in setup, and the comparison summary is in the comparison chapter. Numbering refreshes after filtering without accumulating prefixes. Standard system sans-serif fonts serve interface text; numbers, hashes, chart values and source text use a local monospace stack with tabular digits. Numeric table columns align right and descriptions align left. Public frozen task prompts and rubric anchors explain the judgments; private case context remains withheld. Advanced filters, full fingerprints and source-verifier proofs are expandable. A full-size image view retains original pixels and proportions. The report interface uses English labels; original task and review text retain their supplied language.

A compact glossary before chapter 1 has separate tables for core units/version identities and report headings. Only listed core terms and chapter, subsection or disclosure headings receive dotted-underlined help; metric captions, status badges, legends and table columns remain plain. Case and submitted-experiment headings add matching glossary rows as they are displayed. Tooltips use the same definitions as the glossary and open on hover, keyboard focus or tap; Escape or an outside click closes them. These definitions distinguish execution coverage, requirement judgments and missing evidence. They do not annotate or rewrite original prompts, review reasons, scoring anchors or skill patches. Technical records, public JSON and limitations are footer disclosures rather than a separate interpretation chapter.

Case evidence is initially collapsed as whole cases. Each summary shows runs/repeats, execution statuses, recorded/planned turns, runs with ratings and candidate-direction comparison counts under the current filters. Review coverage includes unknown ratings and is not a quality score. Expand a case to load its references, images and requirement reviews; select a repeat and turn within it. Expand/collapse-all controls affect visible cases. Open state is retained per evaluation and case fingerprint, and repeat/turn choices survive re-rendering. A comparison-table jump opens the selected case and repeat automatically. Several cases can be open together.

Inside a case, a compact requirement table aligns each applicable atom across the selected baseline and candidate. Score badges remain ordinal; no review, no run and insufficient evidence are distinct states. Expand a row's scoring rule for the frozen criterion, original requirement quotes and anchors, or a version's reason and evidence for its complete recorded judgment. Multiple selected reviewers or review revisions remain separate entries in the same cell. Version filters can show one column, and older reports without task context show only recorded atom identities without inventing definitions. Declared raster outputs align by exact artifact name in shared rows; missing outputs keep a placeholder. Other verified images and mechanical source proofs load only when their separate disclosures open. Image layout, filtering and table projection do not change frozen report data or obtain new judgments.

Report generation is deterministic: `report.json` supplies observations, frozen review reasons and provenance; Python and fixed HTML/JavaScript templates supply labels, explanations, tables and charts. Rendering, publication and filtering make no LLM calls. Running a solver or obtaining a new independent review is a separate operation. Identical frozen inputs produce identical patches and report HTML.

The primary selectors are **Candidate commit**, **Baseline commit**, **Evaluation run** and **Case**. Version selectors, comparison cards, evidence headings, diffs and historical details show the full tested Git SHA or frozen snapshot SHA-256. Only actually recorded pairs are selectable. Repeated evaluations of the same pair remain separate runs, and selecting a pair never pools their ratings. Directory-only and older inputs display `Snapshot <full hash>` and explicitly state that the commit was not recorded; report-upload commits are never substituted. A no-skill baseline is distinct and has no previous skill source to diff. Compact chart ticks use twelve characters with full hashes in the accompanying table and tooltips.

**More filters** has one **Skill version** filter scoped to the selected evaluation, with exact hash labels and a role suffix where needed. It refreshes when the commit pair or run changes; there is no redundant role-only baseline selector. Historical labels use their own experiment or cohort identity, never the currently selected run's hash. Technical presentation tables use full version identities; frozen JSON retains its original protocol arm IDs.

Semantic colors and borders distinguish Better (green), Similar (slate), Worse (red) and Not enough evidence (amber). Execution metrics, status badges, requirement ratings and chart categories use the same tone system while keeping their textual definitions. Candidate and baseline cards have distinct role accents and full hashes. Missing evidence remains a separate category, and colors do not create an overall quality score. The report declares English UI text and disables automatic page translation through the HTML `translate` attribute; original saved task/review content is unchanged.

The compact overview adds horizontal stacked bars for execution status by tested version and candidate-direction comparisons by case. Expand rating distributions to see ordinal counts per exact evaluated condition; expand Time and usage for known token bars and their observed-turn coverage. Input-cache components are not added to input totals, and commands retain their separate unit in the table. Charts use zero-based shared absolute scales with integer count ticks, exact count labels and accessible SVG metadata. They refresh with the same filters as the tables and require no remote chart assets.

Execution bars and their legend use green for Completed, red for Failed, blue for Stopped and slate gray for Other/not started. Status labels and counts accompany the colors. Execution status remains distinct from independent quality judgments.

Commit history supports rating-count columns and an evidence-coverage line when matching conditions have multiple recorded, commit-bound runs. Empty or single-point series are hidden. Coverage is the share of recorded ratings assigned a 0/1/2 level; unknown ratings remain in its denominator. It is not a quality score. Unreviewed runs have no value and break the line; changed evaluation conditions remain in separate charts. Full chart data and exact SHAs expand on demand. Missing tested commits produce no history point. A multi-evaluation history can still list exact snapshot identities without inferring Git revisions. The all-experiments metadata list is initially collapsed.

**View skill changes** expands a read-only diff of the exact sealed previous/candidate skill inputs, including references and scripts. Report export verifies the snapshot inventory, byte hashes and skill identities before generating a bounded unified patch. The viewer uses pinned [diff2html 3.4.56](https://github.com/rtfpessoa/diff2html) with side-by-side/unified views, line numbers, file selection, optional long-line wrapping and patch download. Its verified JavaScript, CSS and MIT notice are bundled locally under [vendor/diff2html](src/skill_bench/vendor/diff2html/source.json), included in framework snapshots and packaged wheels; no CDN is needed. The component adds about 95 KiB to a page, independently of the shared reference images.

Public diff records include the two frozen skill hashes, changed-file hashes/status/counts, a patch and its SHA-256. Binary files, private text, files over 256 KiB or 6,000 lines, and content beyond the 2 MiB total patch limit have explicit omission reasons. Public bundle and pooled-site validators check this supplementary contract and its binding to the evaluated arms. Diff text is escaped by the trusted component and is never executed. Source changes remain distinct from measured improvements. Historical exports lacking snapshots retain an explicit unavailable state; validated sealed runs can be re-exported without rerunning a model.

Pair comparisons allow skill bytes to be the intended intervention and check the remaining task, runtime, rubric and review conditions. They show wins, ties, losses and insufficient evidence in the selected candidate's direction. Exact cohort identities protect technical histories. Commit charts use separate bars for each manual run and group matching conditions while excluding the intended skill-byte difference. Other changed conditions form separate charts; unknown is not zero. Cases, case-repeat units, trials, observed/planned turns and dependent rating records remain separate. Missing future ratings are not fabricated. Known token subtotals state their coverage and do not stand in for unknown totals.

Bundle validation is tied to the installed trusted renderer bytes: a previous HTML rendering is not accepted automatically after the renderer changes. Keep historical bundles and their matching trusted framework revision; verify them with that revision or re-export from the sealed run into a new directory using the new renderer. Do not overwrite old evidence or relax exact HTML validation to merge versions.

Source evidence verifies a supported SVG fill edit, actual timed Chromium frames, or one saved Blender object-location edit reopened independently with decoded pixel changes. Original captures can enter anonymous review; verifier-modified captures appear only in technical details. New packets explicitly bind the reviewed source revision, and report import rejects a different selected revision. Deterministic calibration covers only two trusted geometry relations. These operations do not certify cloth simulation, VRM rigging, whole-project parameterization or motion continuity. Independent visual ratings remain exploratory; missing calibration is never a quality pass, and task inventory is distinct from executed evaluations.

## Offline browser and Blender backends

Use `doctor --backend harbor --browser /path/to/chrome --blender /path/to/blender` to probe actual runtimes with zero generation calls. The same optional executable arguments on `plan` freeze binary SHA/version, trusted driver bytes and namespace identity. Missing required capabilities reject a plan before any model call. Keep runtime binaries in dedicated installation directories; no tool grants expose home or subscription credentials.

The solver uses the readonly `tools/browser_client.py` to request bounded capture scenarios. A literal file-queue broker launches Chromium over CDP pipes in an independent Bubblewrap namespace with no external network or host loopback, readonly sealed workspace/runtimes and a private writable capture directory. The Codex command-network profile stays restricted. The browser driver records desktop/mobile/reduced-motion samples, trusted input events, DOM diagnostics, actual capture times and resource failures. Relative HTML, CSS, JS, fonts and raster resources reopen from sealed sibling artifacts; missing local resources fail capture. External resources stay blocked and cannot establish complete reopening. Run the driver with `--help` for the bounded declarative schema. Generic evaluator keyboard exploration is sampled evidence, not a complete per-case interaction test.

Tasks declaring `action_trace_capture` bind bounded turn-specific observation plans before generation. An independent input clock runs alongside screenshot requests; case-bound playback scope 3 includes actual event times, pre-action DOM snapshots and capture windows. `web_audio_probe` additionally requires tone, silence and unavailable-analysis conditions. Requested modes do not establish measured media signal or application response. Each browser scope verifies a 1 GiB memory limit, disabled swap and a 128-process ceiling; unavailable enforcement fails before page execution.

An optional `trace_samples_ms` array adds 2–128 strictly increasing geometry observations within the screenshot timeline. Explicit selectors are required. The trace clock runs independently of screenshot requests and records requested, started and completed times for bounded DOM rectangles, transforms, opacity and visibility. Driver scope 3 and case-bound playback scope 4 retain these observations with their scenario identities. Default capture contracts retain their earlier scope versions. Geometry samples help inspect interruption and repeated-click stability; they do not prove continuous pixels, hidden application state or aesthetic quality. Audio pause checks still need actual media observations and controlled inputs, not button labels or geometry alone.

Blender generators may run inside the existing command sandbox. Independent verification uses a trusted driver with `--factory-startup --disable-autoexec`; solver-generated Python is not executed by the verifier. Software Workbench views show geometry and diffuse colors. A saved, independently reopened object transform proves only that precise edit, not a generator parameter change, materials, deformation or target-avatar readiness.

`regrade --run <run> --reopen-sources` appends zero-generation evidence. Binary/runtime identities remain pinned, while a current independently fingerprinted trusted driver can create a new verifier revision without rewriting generation records. Use `review --run <run> --output <new-packet> --seed <seed> --regrade <record>` to review that exact capture revision. Do not reuse ratings from an older packet for newer captures. Model compatibility tests stay private and do not populate the public formal-comparison catalog.

Use `review --view notes-process-v2 --allow-private` to include declared bounded analysis deliverables, with local paths redacted and original source hashes retained. `local-report` exports authorized private references and validated ratings outside Git; public publication rejects this report kind. Both commands offer the explicit `--evidence-scope failed-turn-v1` condition. A failed turn with a hash-bound supported CLI stream showing no model-output events withholds inherited previews and requires unverifiable ratings; partial output and unknown streams retain their stated limits. Original artifacts, prior packets and legacy default behavior remain intact. Failed execution does not become artistic failure merely because final token usage is missing.

## Manual local evaluation and result submission

Model evaluation starts only when a person runs `skill-bench run --execute` locally. GitHub CI downloads and verifies published results and builds the site. It has no model-request job, automatic evaluation queue, worker command or self-hosted runner. Manual plans record the exact tested skill commits before execution.

Use the already authenticated local Codex CLI and the verified native Harbor environment described above. Examples below assume `skill-bench` was installed from the current checkout. When reusing a verified Python environment from another worktree, use the current source explicitly instead of its older installed entry point:

```bash
PYTHONPATH=benchmarks/skill_bench/src /path/to/verified-harbor/bin/python -m skill_bench.cli --help
```

Planning, review export/import, regrading, report export and publication checks do not run a generation model. `run` without `--execute` only inspects the frozen plan. The per-experiment call ceiling is not a subscription allowance or a token/cost guarantee.

For commit tracking, read the chosen local Git revisions directly. Planning seals their full SHAs and commit dates alongside the exact committed skill files, without switching the worktree, using uncommitted edits or fetching remote code:

```bash
skill-bench doctor --backend harbor
skill-bench plan --suite benchmarks/art_creation/suite.json \
  --case reference-costume --case editorial-transfer \
  --repo . --previous-ref <previous-commit> --candidate-ref <candidate-commit> \
  --arms previous,candidate --backend harbor --repeats 1 --max-calls 12 \
  --output /path/to/private/new-experiment
skill-bench run --run /path/to/private/new-experiment
skill-bench run --run /path/to/private/new-experiment --execute
```

Directory inputs remain supported with `--previous /path/to/old-skill --candidate /path/to/new-skill` instead of Git options, including uncommitted skill work. Its byte hash identifies the tested version; no commit SHA is inferred from the report's later checkout. Keep private run directories and authentication outside Git. Existing independently frozen ratings can be included in `report` with the paired `--review-packet` and `--ratings` arguments above. Without them, visual quality remains unassessed.

Export and package a reviewed result outside the repository. The package contains the frozen `report.json` and exact public image bytes; generated HTML is omitted:

```bash
skill-bench report --run /path/to/private/new-experiment \
  --review-packet /path/to/new-review-packet \
  --ratings /path/to/private/new-experiment/reviews/ratings/<review-id>/v1.json \
  --output /path/to/new-public-report
skill-bench pack-report --report /path/to/new-public-report \
  --output /path/to/packages/new-evaluation.zip
```

`pack-report` prints the package SHA-256 and size, frozen report fingerprint, experiment IDs and counts of trials, ratings, pairs and unique images. Inspect the public records and images, then upload the ZIP to a versioned GitHub Release with `--latest=false` so a data release does not replace the latest software release. Keep published assets unchanged; corrections use a new version and catalog entry. Release assets are the durable inputs; Actions artifacts are generated previews with a retention period.

Append an entry to the version 1 [result catalog](../results/catalog.json). Keep `id`, `title`, `path` and `suite_id` as in the local collection example; copy `report_fingerprint`, `summary` and `package` from the pack command, adding a public HTTPS `package.url` pointing to the versioned ZIP. The catalog stores hashes and counts in readable JSON so a PR can review changes without opening an archive. IDs, paths and package filenames must be unique. Existing entries remain in the catalog.

```bash
skill-bench check-catalog
skill-bench fetch-results
skill-bench check-reports
skill-bench publish --output /path/to/new-preview-site
```

`fetch-results` defaults to the committed catalog and restores into a new ignored `.cache/skill-bench/reports` directory. It verifies the archive size/hash, bounded file inventory, frozen report fingerprint, summary and every image hash, then rebuilds HTML using the current renderer and validates the full collection. It publishes the restored directory only after all packages pass. A changed renderer requires no result-data commit. Use `--output /path/to/new-collection` for later restores; `check-reports` and `publish` accept the same location via `--root`. For an offline copy, supply `fetch-results --archives /path/to/packages`, with ZIP filenames matching the catalog URLs. The command never executes packaged content or calls a model.

`check-catalog` is fully offline. `check-reports` and `publish` operate on restored local files, validating public fields, fingerprints, images, exact current HTML and file inventories. Downloads are explicit in `fetch-results`; ordinary unit tests use generated fixtures and need no release access. A failed download leaves the committed catalog and previous outputs untouched; a missing asset must be restored from its matching backup rather than silently omitted from history.

`publish` assembles one cumulative report per suite and pools duplicate images across all its inputs. Commit charts use the tested skill SHA recorded before generation, never the result-upload commit. Commit dates determine chart order, with hash order for undated identities. Multiple runs at one commit remain separate, unevaluated commits have no point, and old snapshots without a recorded SHA remain listed outside the commit charts. `report --history /path/to/previous-public-reports` remains an optional local export; its directory must contain only reports from one suite.

Public export removes PNG text, EXIF and timestamp metadata, which can contain local source paths. Image and color-profile chunks remain byte-identical. A changed image receives its own content hash plus `source_sha256`, `source_size` and a `png-metadata-removal-v1` transformation record. Review evidence keeps its original hash/path and adds the corresponding `public_sha256`/`public_path`; scores and reasons remain unchanged. Bundle and shared-site validators reject those metadata chunks. This is a publication derivative, not a new rendering or review. Other raster metadata and visible image content still need inspection before publication.

Published suite pages use relative image paths such as `../assets/<sha256>.png`. The whole site stores each distinct original image once, including references reused by different experiments and suites. No Base64 image payload or portable HTML is generated by default. Frozen input bundles remain independently verifiable; the published site's pooled projection is checked separately with:

```bash
skill-bench check-site --root /path/to/new-preview-site
```

Open the complete site directory in a browser. An application that isolates just one HTML file cannot resolve adjacent images; serve the site root and preview its local URL when that happens:

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory /path/to/new-preview-site
```

Open `http://127.0.0.1:8765/` to choose a benchmark, or `/timeline/index.html` for the first suite. The server serves public result files only; it does not run a model. CI packages the same relative-path site for downloading or static hosting.

For a single-file handoff only, embedding remains an explicit optional export. The input may be one frozen report bundle or the complete shared-image site:

```bash
skill-bench portable --report /path/to/new-preview-site --output /path/to/optional-preview.html
```

For a multi-suite site, add `--suite-id <registered-suite-id>` to select its history explicitly. Portable HTML preserves report content and images; navigation to other reports still requires the full site.

Base64 increases raster byte storage by about one third, and each standalone export contains its own copy. Such files are local optional handoffs, not the default CI artifact or a second set of committed result data. The original bundle ceiling remains 64 MiB, the source collection and pooled site ceiling 256 MiB, and optional portable HTML 96 MiB; exceeding a limit fails explicitly without deleting history. Original image bytes, task records and rating content are preserved. Site checks verify asset hashes, public fields, report fingerprints, exact trusted renderer output and file inventory without weakening the standalone bundle validator.

Commit the updated catalog, task definitions and code. ZIP packages, generated HTML, restored collections and private run directories stay outside the Git source tree:

```bash
git add benchmarks/results/catalog.json
git commit -m "benchmarks: index manually evaluated skill comparison"
```

Keep the local verified packages as a backup. Do not add `auth.json`, raw trajectories or the unblinded review map. Result packaging does not upload files or modify Git; publication is a separate maintainer action.

## Credential-free GitHub CI

The [workflow](../../.github/workflows/skill-benchmark.yml) runs GitHub-hosted offline checks and report packaging. `offline` checks task contracts, calibration, deterministic tests and the skill index. `report` installs its own locked environment, runs `fetch-results`, `check-reports` and `publish`, and uploads `skill-benchmark-reports-<commit-sha>` as an Actions artifact. It validates submitted evaluations without running models. Actions and uv are pinned; checks and packaging have read-only repository access.

Main pushes, relevant PR changes and a parameter-free `workflow_dispatch` run offline checks. Checkout downloads the repository's Git LFS image objects before validation. For a local clone, install Git LFS and run `git lfs pull` to obtain the same assets. A code-only commit may package the same historical evaluations; report charts retain the tested skill identities. Download and extract the artifact, then open `index.html` to browse reports with their images. Artifact retention is 30 days. The committed catalog pins the versioned Release inputs by SHA-256 and size; results are not stored in the source tree. Git LFS remains in use for the small authored reference dataset, not historical output images.

### Optional GitHub Pages publication

To serve the validated site from this repository:

1. In **Settings → Pages → Build and deployment**, select **GitHub Actions** as the source.
2. In **Settings → Secrets and variables → Actions → Variables**, set `BENCHMARK_PAGES_ENABLED` to `true`.
3. Merge the workflow into `main`, then run **Actions → Skill benchmark → Run workflow** on `main`, or push a later commit to `main`.

The `pages` job deploys the verified report artifact after both checks and packaging pass. Deployment runs on `main` when the variable is enabled and uses the `github-pages` environment with `pages: write` and `id-token: write` permissions. PR checks keep publishing downloadable artifacts. Model evaluation continues to run manually on the local authenticated Codex installation; GitHub needs no model API key, subscription credentials, or self-hosted runner. See [GitHub's custom Pages workflow guide](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

The main report interface is English, with plain metric names such as **Completed runs**, **Recorded / planned turns**, and **Better / Similar / Worse / Not enough evidence**. Original task text, review reasons, ordinal anchors and machine field names remain unchanged.

## Evidence APIs

- `review.export_review(run_dir, destination, seed=..., view=..., allow_private=False)` creates a new anonymous packet and private map.
- `review.validate_packet_mapping(packet, mapping)` verifies the complete packet fingerprint and private HMAC entry binding before import.
- `review.validate_review(packet, document, media_root=...)` checks applicability, complete judgments, reviewer disclosure and evidence.
- `review.freeze_review(packet, document, destination, media_root=...)` writes a new immutable version.
- `report.build_report(manifest, results, reviews=[{"packet": ..., "document": ..., "arm_map": ...}], execution_events=store.read_events(run_dir), skill_root=run_dir)` imports independent judgments without self-scores, uses validated ledger event types/IDs for closed-run coverage and derives supplementary diffs from verified frozen skills.
- `report.merge_reports(reports)` deduplicates report fingerprints and retains exact cohort series.
- `report.export_report(report, destination, media_root=..., packet_roots=...)` writes a new sanitized bundle.
- `report.validate_public_bundle(root)` checks a downloaded public allowlist without executing its sources.
- `result_packages.pack_report(root, output)` creates a deterministic data-and-images ZIP and prints catalog metadata.
- `result_packages.load_catalog(path)` validates the committed index without downloads.
- `result_packages.fetch_results(catalog, output, archives=None)` restores checked packages and current HTML into a new collection.
- `publication.validate_collection(root)` validates explicitly catalogued public bundles with zero generation.
- `publication.publish_collection(root, output)` stages only verified public files into a new offline site.

The [dataset](../art_creation/README.md) documents splits, provenance and task limits.
