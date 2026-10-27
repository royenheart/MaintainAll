# configs

## Stow link management

Some configurations are managed with stow. To use them:

1. Install stow:

```bash
sudo apt install stow
```

2. Clone stow-configs locally:

```bash
git clone https://github.com/royenheart/MaintainAll.git
cd MaintainAll
# Link the bash configuration into its active location; other packages work the same way.
stow bash -t $HOME
```

## dsh plugins

dsh plugins have moved out of `apps/` and are maintained under `~/projects/dsh-plugins/`. Install and update them through `MaintainAll/deploy/ds-harness/deploy.py`, which reads the plugin list from `plugins.yml`. It first tries a remote `dsh plugin add <spec>` and falls back to a temporary checkout for a `file:` install.

This no longer uses `stow-configs/dsh`, `maintainall.yml`, `cordis:include`, or the `install_dsh_plugins` / `uninstall_dsh_plugins` bash functions.

A single plugin can be installed or removed independently:

```bash
cd ~/projects/dsh-plugins/dsh-plugin-skills-manager
python3 install.py install
python3 install.py uninstall
```

Note: before using `dsh-plugin-skills-manager`, apply both patches under its `patches/` directory to deepseek-harness. See the plugin README for details.
