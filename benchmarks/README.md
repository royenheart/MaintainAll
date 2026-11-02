# Benchmarks

The unified evaluation framework lives in [`evaluation/`](evaluation/README.md).

- One CLI: `PYTHONPATH=benchmarks/evaluation/src python3 -m eval_framework.cli`.
- One immutable record path: `benchmarks/evaluation/records/` (derived, ignored by Git).
- One report builder: `benchmarks/evaluation/site/` (derived, ignored by Git).
- One public build: `python3 benchmarks/evaluation/build_public_site.py` writes
  `public-benchmark-site/`:
  - `/` — evaluation index listing each tested skill,
  - `/dsh-sandbox-attribution/` — detailed DSH attribution report,
  - `/art-creation/` — normalized legacy art-creation report with public reference and comparison images.
- `agent_eval/` and `skill_bench/` remain source adapters: `agent_eval/` supplies
  frozen attribution cases and sealed evidence under `evaluation/evidence/`;
  `skill_bench/` remains the authoritative renderer for the rich art-creation reports.

## Current attribution snapshot

The active `both` case is `sandbox-natural-11` (WebGL). `sandbox-natural-09` is the
`dsh` case; `sandbox-natural-08` is the application-bug control. `sandbox-natural-02`
is a `missing-input` control and `sandbox-natural-01` is retired. Results are reported as
**semantic accuracy** (independent blind judge) and **evidence completeness** (frozen
grader), never as one merged score. See
[`evaluation/METRICS_ATTRIBUTION.md`](evaluation/METRICS_ATTRIBUTION.md).

## Local and Pages preview

```sh
python3 benchmarks/evaluation/build_public_site.py
python3 -m http.server 8780 --bind 192.168.31.143 --directory public-benchmark-site
```

GitHub Pages deployment is `.github/workflows/evaluation-site.yml`. CI validates the
art-creation site with the locked `skill_bench` environment and uploads the merged site;
it never runs models.
