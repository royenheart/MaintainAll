# Open data for supply-chain checks

There is no unified dsh-plugin security dataset. Use generic npm data plus the
plugin's own repository history.

| Source | What it answers | Access | Limits |
|---|---|---|---|
| OSV.dev | npm package/version vulnerabilities, GHSA/CVE/MAL aliases, malicious packages | `POST /v1/querybatch` or `query`; offline `npm/all.zip` | batch returns IDs only; fetch `/v1/vulns/{id}` for detail; snapshot ages |
| GitHub Advisory Database | GHSA records as OSV files; malware type | clone `github/advisory-database` or REST global advisories | no lockfile resolution; 60 req/h anonymous |
| npm audit bulk | npm-only advisories for posted versions | `POST registry.npmjs.org/-/npm/v1/security/advisories/bulk` | undocumented, weak IDs, no malware coverage |
| OpenSSF malicious-packages | malicious npm packages as MAL OSV records | clone repo; also inside OSV npm dump | malware only |
| OSV-Scanner | lockfile resolution + OSV matching, offline | `osv-scanner --offline --format json` | tool, not data; needs DB mirror |
| deps.dev / OpenSSF Scorecard | dependency graph, scorecard, advisories | APIs | provenance/reputation signal, not a vulnerability verdict |
| GitHub issues/PR search | plugin-specific reported problems | `/search/issues?q=repo:...` | rate-limited; no advisories for most repos |

For a deterministic benchmark, vendor trimmed OSV/GHSA records and frozen issue JSON in
`fixtures/` and grade against those IDs. For a real audit, mirror OSV npm data locally
and record `id` + `modified`; never turn "no fixture / no result" into "safe".
