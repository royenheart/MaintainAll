# Agent evaluation framework (legacy adapter)

> Unified entry point: `benchmarks/evaluation/README.md`. This tree remains the dsh-skill case/result source; it is no longer a separate report path.

This is the preserved, model-agnostic harness from the retired
`dsh-plugin-development` benchmark. It evaluates a skill by running the same case with
and without a frozen skill snapshot; it is not tied to one skill. The current frozen attribution subset is `sandbox-natural-11` (WebGL/both), `sandbox-natural-09` (dsh), and `sandbox-natural-08` (application control); `sandbox-natural-02` is a missing-input control and `sandbox-natural-01` is retired.

## Components

- `runner/isolate.py` — allowlist-root bubblewrap jail. No host home, MaintainAll
  checkout, `.agents`, `.dsh`, `.codex`, or projects; the official
  `cordis-plugin-development` skill is masked.
- `runner/probe_isolation.py` — credential-free isolation gate using
  `probe-skill/`; without finds no target skill, with finds only the declared one.
- `runner/proxy.py` — host-side DeepSeek proxy; the jail receives a dummy key.
- `runner/run_dsh_in_jail.py` — one dsh SDK trial with a required `--skill-dir` for
  the with arm.
- `runner/run_codex_in_jail.py` — Codex CLI arm with a temporary `CODEX_HOME`;
  `auth.json` is chmod 000 after startup (a race-window mitigation, not a proxy).
- `runner/run_case.py` — frozen case → trial → external grader → sealed JSON.
- `runner/metrics.py` — event-derived tokens/cache/tools/latency/compaction.
- `runner/codex_metrics.py` — Codex `--json` usage/items.
- `runner/report.py` — per-run table.
- `runner/test_metrics.py`, `runner/test_codex_metrics.py` — synthetic checks.

## Add a case

A case directory contains:

```text
case.json          # id, prompt, fixture, grader, optional seedHome/extraPatch
prompts/...
repo/              # fixture copied into /work/repo
<grader>           # trusted, runs outside the jail; receives repo and home
```

Run:

```sh
python3 benchmarks/agent_eval/runner/run_case.py \
  --case <case-dir> --mode with --skill-dir skills/<skill> --model deepseek-flash
```

For a without arm, omit `--skill-dir`. The runner writes `case-result.json` with
`skill_sha256`, grade, and metrics. Graders must be calibrated with a known-good and a
plausible-broken fixture before a result is used.

## Gates

1. `probe_isolation.py` passes.
2. The target skill is the only skill in the with arm; without has none.
3. The case grader passes known-good and fails plausible-broken.
4. A trial without a result is an explicit failure, not a low score.
5. Do not compare different models or task sets as a model ranking.

## Claims

The framework measures a skill's marginal effect and its cost. It does not prove
necessity from a control; a skill with no stable with/without spread has no
correctness claim. Keep process metrics separate from correctness.
