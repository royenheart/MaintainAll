# Supply chain

Install-time execution is the highest-risk surface.

- Read every `preinstall`/`install`/`postinstall`/`prepare` script.
- Treat git/HTTP dependencies as unreviewed source; pin a commit and inspect the
  package's build script.
- `file:`/`link:` paths can point outside the repository or at another agent's
  checkout; resolve them and inspect the target.
- Check the registry identity: scope/name, typo-squats, deprecation, publish time,
  maintainers, lockfile integrity.
- A tarball install is not automatically safer; inspect the packed `files` and
  lifecycle scripts.
- Prefer a reviewed registry version or a pinned commit with a lockfile over a
  floating range.

A package that executes code at install can compromise the host before the agent ever
loads the plugin. Static review must happen before install.

## Local advisory fixture mode

`scripts/supply-chain-audit.mjs` resolves `package-lock.json` packages (including transitive ones), matches `fixtures/advisories/*.json` OSV-shaped records (id, aliases, affected ranges), and reads `fixtures/issues/*.json`. It is read-only and does not run `npm audit` or install anything. Missing fixtures means `not verified`, not clean. For live data use OSV.dev `querybatch` or an offline npm OSV dump; GitHub Advisory Database and npm audit bulk are cross-checks, not the same coverage.
