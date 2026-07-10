---
name: modulefile-manager
description: When to use — scan, generate, list, or delete Environment Modules via scripts/modulefiles/manage_modules.py.
---

# Modulefile manager

## Context

Environment Modules files are managed by the CLI at `scripts/modulefiles/manage_modules.py` (templates under `templates/modulefiles/`). Former TUI `PLUGIN_META` plugin UX is replaced by this skill plus missions; keep using the CLI, not a plugin panel.

Subcommands:

| Command | Purpose |
|---------|---------|
| `list` | List managed modulefiles under `$MODULEPATH` |
| `scan <dir>` | Scan an install tree, parse name/version, batch-generate modulefiles |
| `add <name> <ver> <path>` | Generate a single modulefile for a known install |
| `delete <name> <ver>` | Remove a managed modulefile |

## Instructions

1. Prefer `python` or `python3` with the repo-relative script path from the repo root.
2. **List:** `python scripts/modulefiles/manage_modules.py list` — summarize names/versions in the report.
3. **Scan / generate:** `python scripts/modulefiles/manage_modules.py scan <install_root>` — review proposed packages before relying on generated files; note template type (generic/devel/custom).
4. **Add:** `python scripts/modulefiles/manage_modules.py add <name> <ver> <path>` when scan is too broad.
5. **Delete:** only when the user/mission confirms the exact name+version; never bulk-delete blindly.
6. Capture CLI stdout/stderr into the mission report; surface non-zero exits as failures with remediation (MODULEPATH, permissions, missing templates).

## Constraints

- Do not delete modulefiles without explicit confirmation in interactive sessions (or an explicit delete mission step with named targets).
- Run only commands matching mission `allowed_commands` (list / scan / add / delete patterns).
- Do not edit `scripts/modulefiles/manage_modules.py` as part of routine ops; treat it as the stable CLI.
- Do not invent install paths; use paths from the user, mission instruction, or a prior scan listing.

## Examples

```bash
python scripts/modulefiles/manage_modules.py list
python3 scripts/modulefiles/manage_modules.py scan /opt/software
python scripts/modulefiles/manage_modules.py add cuda 12.2 /usr/local/cuda-12.2
python scripts/modulefiles/manage_modules.py delete cuda 12.2
```
