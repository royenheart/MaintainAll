# Small Art Creation old/new experiments

This local runner compares one or two trusted, synthetic tasks across frozen old/new skill snapshots. It uses the official Codex Linux permission profile and the existing local subscription authentication. It does not install Harbor, call an LLM judge, publish artifacts, or run a paid CI workflow.

Requirements: Linux, the npm installation of `codex-cli 0.160.0`, Python 3.11+, and existing local Codex authentication. The model and effort are fixed to `gpt-6.1-sol` and `low`. A changed CLI version fails closed until its sandbox is revalidated. See [source pins](sources.lock.json).

```sh
python3 benchmarks/art_creation_ab/run.py --help
python3 -m unittest discover -s tests -p test_art_creation_ab.py
python3 benchmarks/art_creation_ab/run.py doctor
python3 benchmarks/art_creation_ab/run.py prepare \
  --old-commit 805a538e2693ffc20e3ebb074e0792861f370374 \
  --new-dir /absolute/path/to/candidate/art-creation \
  --task expressive-ribbon \
  --output /absolute/private/path/to/a-new-run \
  --timeout 180
python3 benchmarks/art_creation_ab/run.py run \
  --output /absolute/private/path/to/a-new-run --execute
```

`prepare` accepts `--old-dir` or `--old-commit`, and `--new-dir` or `--new-commit`. `--repo` chooses the repository for commit sources. Repeat `--task` once to include `fashion-boundary`: two tasks mean four CLI invocations. Execution is sequential, old then new, with one independent ephemeral session per task and no retries. A CLI invocation can contain multiple provider requests; the provider request count remains unknown. A wall-clock timeout is a time limit, not a token or monetary guarantee.

`doctor`, `prepare`, `check`, `usage`, and `--help` make no model requests. Only `run --execute` starts model work. Use trusted skill changes and trusted task fixtures; this v0 is not a service for arbitrary PR code.

The trusted CLI can read the existing authentication, but generated commands cannot read it. The task filesystem defaults to root deny, permits the minimal OS runtime and precise Codex package path, permits writes only in its own workspace, and makes the selected skill read-only. `/tmp` and `$TMPDIR` are explicitly denied outside that workspace. Generated command network access is disabled; the trusted model API connection remains available. User configuration/rules, project AGENTS documents, plugins, web search, and every discovered host skill are excluded. The chosen skill is explicitly loaded from `skill/SKILL.md`; automatic skill-trigger quality is outside this experiment.

The preflight performs real denied-read, denied-write, and denied-network probes, then checks that the enabled host skill catalog is empty and project AGENTS loading has a zero-byte limit. It preserves `HOME` and `CODEX_HOME`, does not copy credentials, and does not change global configuration.

Global Codex-home `AGENTS.md` and `AGENTS.override.md` are independent of the project byte limit. The preflight requires them to be absent and fails closed if either appears; it never moves or edits user instructions.

Private outputs use mode `0700` for the run root and a `077` umask. Keep the output outside the repository. `manifest.json` freezes skill file hashes, task identities, model, effort, order, and timeout; `preflight.json` records the environment. Each trial has `events.jsonl`, `stderr.log`, `final.txt`, `result.json`, and its workspace. `summary.json` contains contract checks and the CLI-reported token totals. Raw process logs stay private.

The tasks require two editable 320×240 SVG directions plus `brief.json`, original content, pending intent/preference decisions, and honest capability limits. The checker rejects raster/script/external-resource SVGs and invented acceptance. Different file hashes are a mechanical proxy; they do not establish visible difference or aesthetic quality. Human visual review remains required. Currency, provider snapshot, seed control, compaction count, and user acceptance are unknown unless independently observed; no aesthetic total score is assigned.

## Two real feedback turns

The [feedback runner](feedback.py) adds a separate, small experiment for confirmation scope, source-object retention, sampled motion, and agent display evidence. Freeze the current baseline before changing the skill, then prepare each arm with identical task inputs and the same static renderer:

```sh
python3 benchmarks/art_creation_ab/feedback.py --help
python3 -m unittest discover -s tests -p 'test_art_creation_*.py'
python3 benchmarks/art_creation_ab/feedback.py doctor
python3 benchmarks/art_creation_ab/feedback.py prepare \
  --arm old --skill-dir /absolute/path/to/frozen-v1/art-creation \
  --task fashion-feedback --task source-motion \
  --output /absolute/private/path/to/baseline-feedback --timeout 180
python3 benchmarks/art_creation_ab/feedback.py run \
  --output /absolute/private/path/to/baseline-feedback --execute
python3 benchmarks/art_creation_ab/feedback.py prepare \
  --arm new --skill-dir /absolute/path/to/candidate/art-creation \
  --task fashion-feedback --task source-motion \
  --output /absolute/private/path/to/candidate-feedback --timeout 180
python3 benchmarks/art_creation_ab/feedback.py run \
  --output /absolute/private/path/to/candidate-feedback --execute
```

`--skill-commit` and `--repo` are alternatives to `--skill-dir`. One task means two calls per arm; two tasks mean four per arm and eight for the comparison. The first invocation persists its private conversation in the original Codex home. The second invocation uses `exec resume` with that exact recorded UUID, preserving the same workspace and permission settings; it never uses `--last` or packs both turns into one prompt. Snapshots after each turn preserve the original alternatives for verification. A failed first invocation or missing rendered previews prevents that conversation's second invocation. There are no automatic retries.

The first turn explores two directions without acceptance. The second is a synthetic user's explicit, limited selection and requests one unconfirmed revision while preserving the other direction and source object. Explicit JSON fields and image-viewing requests make these contract smoke tests. They do not independently show that a skill caused the behavior or represent real user acceptance.

`--renderer` selects an already installed isolated CairoSVG runtime; the default is `~/.local/state/maintainall/art-creation-ab/runtime/cairo`. This experiment used CairoSVG 2.9.0 in a private uv environment, not a global installation. Doctor adds an actual SVG-to-PNG sandbox probe to the existing isolation checks. Only the precise runtime directory is readable. Strict command networking remains disabled. Installed Chrome failed under this profile's network syscall restrictions, so the experiment uses static rendering and states that continuous playback is unverified. It does not enable a network proxy or weaken host-file denial to start Chrome.

The agent must render and inspect its actual images during each turn. Evidence comes from its exact private rollout: `task_started` boundaries separate turns, and both direct image tools and code-mode `view_image(...)` calls require returned image items. A declaration or an evaluator's later rendering does not count as agent display evidence. Sampled path coordinates, source IDs, retained objects, and generated code support mechanism review; two frames do not prove continuous playback or aesthetic quality.

The pinned CLI reports thread-cumulative token totals after resume. Results retain these as `reported_cumulative_usage` and store second-turn deltas in `usage`; only normalized per-turn values may be summed. Raw logs, UUIDs, and snapshots remain private.

## Complex reference tasks

The independent [complex entry point](complex.py) accepts trusted task cards with two or three real rounds and actual reference images. It reuses the same model, effort, authentication, discovery isolation and OS sandbox. It leaves the earlier entry points intact. The supplied [costume card](cases/complex/tasks/reference-costume.json) and [exhibition card](cases/complex/tasks/editorial-transfer.json) contain unchanged natural prompts, delivery contracts and evaluator-only quality atoms. Their four original Met images have source, license and SHA-256 provenance in the [input manifest](cases/complex/inputs/manifest.json); they were not resampled.

```sh
python3 benchmarks/art_creation_ab/complex.py doctor
python3 -m unittest discover -s tests -p 'test_art_creation_*.py'
python3 benchmarks/art_creation_ab/complex.py prepare \
  --old-dir /absolute/path/to/frozen-v1/art-creation \
  --new-dir /absolute/path/to/current/art-creation \
  --task-card benchmarks/art_creation_ab/cases/complex/tasks/reference-costume.json \
  --task-card benchmarks/art_creation_ab/cases/complex/tasks/editorial-transfer.json \
  --output /absolute/private/path/to/a-new-complex-run --max-cli-calls 12
python3 benchmarks/art_creation_ab/complex.py run \
  --output /absolute/private/path/to/a-new-complex-run \
  --arm old --task reference-costume --through-turn 1 --execute
python3 benchmarks/art_creation_ab/complex.py run \
  --output /absolute/private/path/to/a-new-complex-run --arm old --execute
python3 benchmarks/art_creation_ab/complex.py run \
  --output /absolute/private/path/to/a-new-complex-run --arm new --execute
python3 benchmarks/art_creation_ab/complex.py blind-export \
  --output /absolute/private/path/to/a-new-complex-run \
  --dest /absolute/private/path/to/a-new-review-packet
python3 benchmarks/art_creation_ab/complex.py validate-scores \
  --packet /absolute/private/path/to/a-new-review-packet \
  --scores /absolute/private/path/to/a-new-review-packet/ratings.json
```

`prepare` also accepts old/new commits and `--repo`. Task cards declare `schema_version: 1`, a portable `id`, `attachments`, `rounds`, `rubric`, and `limits`. Each attachment declares an ID, a path relative to the card, SHA-256, source and license. Each round supplies a natural prompt, attachment IDs and explicit `required_artifacts` with `path`, `kind` (`editable` or `preview`), `format`, and optional PNG width/height. Artifact filenames, formats and viewports are delivery contracts, not a component-ID or construction-algorithm recipe. Each quality atom supplies an ID, criterion and 0/1/2 anchors; optional `applicable_turns` defaults to every round. Later feedback criteria are omitted from earlier rating forms.

Only explicitly named reference image bytes are copied into `workspace/inputs`, which is read-only under the official permission profile. No host input directory is granted. Doctor verifies reading, rejected overwrite/new-file creation/directory rename, and all previous isolation checks; its static-renderer mode has 17 checks and no model calls. CLI `--image` attaches each round's selected staged files. Exact persisted user-image items are counted separately from reference/artifact/unclassified image-tool returns; dynamic code paths remain unclassified rather than being assumed to show artifacts. Rubrics and manifests stay outside agent workspaces and are never appended to prompts.

Limits are explicit: at most two tasks, three rounds per task, twelve budgeted CLI calls, 600 seconds per round, 8 MiB per workspace file and 32 MiB for the whole workspace, including staged inputs and skills. A one-second monitor stops an over-limit invocation; the 90-minute experiment wall clock persists across entry-point invocations. Time limits do not guarantee a monetary or token ceiling. A completed first turn can be continued without rerunning it. Calls are reserved before launch; failed or interrupted phases cannot be retried automatically. Missing input/usage evidence, changed inputs or workspace violations stop the current execution path with raw logs retained. The runner never executes an agent-generated program on the unsandboxed host.

Every round captures all bounded regular output files, including `notes.md`, with SHA-256. Over-limit artifacts are explicitly rejected, never silently skipped. The complex snapshot excludes `__pycache__`, `.pyc` and `.pyo`; its logical bundle hash is SHA-256 of the sorted JSON mapping from relative file names to SHA-256 content hashes. Earlier snapshots and their hashes remain unchanged.

`check` reports source/PNG container contracts, sizes, real tool evidence and within-arm/task hash comparisons. It leaves `quality_status` as `unassessed`, even when delivery passes or the agent declares itself successful. PNG checks validate chunk boundaries/CRC/IHDR/IDAT/IEND and optional dimensions; they do not prove artistic quality or full pixel decoding. Source geometry and relationships require artifact inspection; object counts are not quality points.

`blind-export` copies preview PNGs, actual notes, references, user prompts and applicable rubric forms under random entry IDs. It does not export raw traces, credentials, source code or the arm map. The map stays separately in the original private run root. Hash comparisons are computed only within each entry's task and arm. The packet supports a single reviewer's artifact assessment with manual `0`, `1`, `2`, or `unverifiable` and visible evidence. Notes or artifact styling can reveal process choices, so this is partial anonymization, not a user blind trial. No automatic aesthetic score or aggregate pass is produced; source self-scores cannot populate ratings.

Actual [complex-task observations](complex-results.md) distinguish delivery success from the frozen root-agent review and document the first-round rubric alignment exception. Execution completion is derived from result rows; the stored manifest execution label is not a completion verdict. The framework does not change its mechanical quality status when a separate review is saved.
