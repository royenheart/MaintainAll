# Privacy and evidence handling

Metrics are derived data; the raw run may contain prompts, source, credentials, tokens,
cookies, `.npmrc`, or personal paths.

- Report aggregates and relative paths, not raw prompts/tool output.
- Never print `.credentials.yaml`, `auth.json`, cookie values, API keys, or `.npmrc`.
- Never upload raw trajectories without explicit authorization.
- If a path is needed as evidence, use the repository-relative path; redact the home
  prefix.
- A missing credential is reported as "configured/not configured", never by value.
