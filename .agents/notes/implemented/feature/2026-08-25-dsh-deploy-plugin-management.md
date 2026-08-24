# Agent Note: dsh-deploy plugin management

Status: implemented — deploy/ds-harness/deploy.py now reads plugins.yml and installs/updates dsh plugins remotely, separate from deployment actions.

## Problem

`deploy/ds-harness/deploy.py` was a pure Caddy reverse-proxy deployer. dsh plugin
installation had been moved out of `apps/` into `~/projects/dsh-plugins/`, but
there was no single place that listed *which* plugins a ds-harness deployment
should have. The stow-configs README already promised a `plugins.yaml`-driven
`deploy.py`, but the script did not implement it.

## Decision

- Add `deploy/ds-harness/plugins.yml`: a top-level `plugins:` list. Each entry is
  one remote spec — either a bare npm package spec (`@scope/name`, `name@version`)
  or a git/github URL/shortcut (`https://github.com/...`, `git@...`,
  `github:owner/repo`).
- `deploy.py` gains two actions, `install` and `update`, that are mutually
  exclusive with deployment actions (`up`/`down`/`status`/`scan`/`reload`). One
  invocation does exactly one of them; the action positional enforces it.
- Install strategy per entry: remote-first via `dsh plugin --profile <name> add
  <spec>`. Only when that fails does the script pull the plugin into a
  `tempfile.mkdtemp` directory — `git clone --depth 1` for git specs, `npm pack`
  for npm specs, direct download for remote tarball URLs — then
  `dsh plugin add file:<tmpdir>/...` and delete the temp directory.
- Update strategy: npm specs update through `pnpm update --latest` by package
  name (falling back to the install flow when the package is missing or the
  update fails); git specs re-run the remote-add flow because `pnpm update`
  does not re-resolve git dependencies to their latest commit.
- Plugin actions take `--profile` (default `$DSH_PROFILE` or `web`), `--home`
  (default `$DSH_HOME` or `~/.dsh`), `--dsh` (default `dsh` on PATH), and
  `--dry-run`. Deployment-only flags are rejected for plugin actions and vice
  versa.

## Alternatives considered

- **Continue with a separate bash function/script**: rejected — the stow-configs
  README already deprecated that path, and a Python deploy script can validate
  the YAML list and share `--dry-run`/command-printing conventions.
- **Reuse `dsh plugin update` for git entries**: rejected after testing — pnpm
  treats a git dependency as already up to date, so re-running `add <git-spec>`
  is the only way to re-resolve the latest commit.
- **Make plugins.yml a line-based text file to avoid PyYAML**: rejected — the
  user asked for `plugins.yml`; PyYAML is loaded lazily only for `install`/
  `update`, so deployment actions keep their zero-dependency startup.
- **Fallback always via clone even for npm specs**: rejected — `npm pack` is the
  npm-native way to fetch the publish tarball into a temp dir and respects the
  same registry/version resolution as pnpm.

## Consequences

- Deployment actions are unchanged and still need only the Python standard
  library; PyYAML is required only when `install` or `update` runs.
- Plugin management shells out to `dsh` (and therefore `pnpm`), not to a custom
  profile manifest writer, so `dsh.profile.bundles` reconciliation keeps
  working exactly as `dsh plugin` defines it.
- `plugins.yml` starts empty; the first real plugin list is a deliberate future
  change and will make `install`/`update` meaningful.
- The old "this script does not manage plugins" claim in the script docstring
  and README is now false and was updated in the same change.
