# ds-harness 插件部署

MaintainAll 的 dsh 插件集现在独立放在 `~/projects/dsh-plugins/` 下，由本目录的
`deploy.py` 统一安装/卸载。旧的 `stow-configs/dsh/maintainall.yml` 与
`.bash_my_profile` 里的 `install_dsh_plugins` / `uninstall_dsh_plugins` 已移除。

## 用法

```bash
python3 deploy.py install                 # 按 plugins.yaml 安装全部插件
python3 deploy.py uninstall               # 按 plugins.yaml 卸载全部插件
python3 deploy.py list                    # 只列出清单与目录是否存在

python3 deploy.py install --only dsh-plugin-skills-manager
python3 deploy.py install --profile web --skip-build
python3 deploy.py install --dry-run       # 只打印每个插件会执行的命令/写入
```

环境变量：`DSH_PROFILE`（默认 `web`）；profile / `DSH_HOME` 的解析规则与各插件
`install.py` 一致。

## 插件列表

编辑 `plugins.yaml` 即可增删插件，每个条目：

```yaml
plugins:
  - name: dsh-plugin-skills-manager            # 目录名/标识, --only 用它匹配
    path: ~/projects/dsh-plugins/dsh-plugin-skills-manager
    git: https://github.com/royenheart/dsh-plugin-skills-manager.git  # 可选
```

- `path` 不存在且配置了 `git` 时，deploy.py 会先 `git clone`。
- `dsh plugin add` 收到的**始终是本地 `link:<dir>` 路径**，不会是 GitHub URL；
  `git` 字段只用于把缺失的插件仓库 clone 到 `path`，随后仍走本地 link 安装。
- 每个插件目录必须自带 `install.py`，接受 `install` / `uninstall` 以及
  `--profile`、`--skip-build`、`--dry-run` 参数（deploy.py 只负责转发）。
- `install.py` 负责构建、`dsh plugin add link:<dir>`、维护 profile 目录下的共享
  `maintainall.yml` 条目与 `cordis.patch.yml` 里的 `cordis:include`；因此多个插件
  可以各自独立安装/卸载而不互相覆盖清单。

## 注意

`dsh-plugin-skills-manager` 需要先给 deepseek-harness 应用插件目录 `patches/` 下的
两个补丁并重新构建，否则安装成功也无法正常工作（详见插件 README 与
[#1413](https://github.com/deepseek-ai/deepseek-harness/discussions/1413)、
[#1427](https://github.com/deepseek-ai/deepseek-harness/discussions/1427)）。
