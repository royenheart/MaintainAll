# ds-harness 插件部署

MaintainAll 的 dsh 插件集独立放在 `~/projects/dsh-plugins/` 下，由本目录的
`deploy.py` 统一安装/卸载。插件现在是 **dsh profile bundle**（package.json
声明 `dsh.bundle.patch`），因此：

- `dsh plugin add <git-url>` 成功后，dsh 会把插件自动 reconcile 进
  `dsh.profile.bundles`，由插件自带的 `cordis.patch.yml` 插入自身 host 行；
- **不再使用 / 维护** `~/.dsh/profiles/<name>/maintainall.yml`、
  `~/.dsh/maintainall.yml` 和 `cordis:include` 条目。

## 用法

```bash
python3 deploy.py install                 # 按 plugins.yaml 安装全部插件
python3 deploy.py uninstall               # 按 plugins.yaml 卸载全部插件
python3 deploy.py list                    # 列出 git URL 与 fallback 目录状态

python3 deploy.py install --only dsh-plugin-skills-manager
python3 deploy.py install --profile web --skip-build
python3 deploy.py install --dry-run       # 只打印将要执行的命令
```

环境变量：`DSH_PROFILE`（默认 `web`）。

## 安装流程

每个插件条目（`plugins.yaml`）提供 `git` URL 与可选的 `fallback_dir`：

1. **先直装 git**：`dsh plugin --profile <name> add <git-url>`。插件仓库带
   `prepare` 脚本，pnpm 安装时构建 `lib/`；第一次遇到 pnpm 的
   `allowBuilds` 提示时，把 dsh 命令行给出的 key 加进 profile 的
   `pnpm-workspace.yaml` 后重跑。
2. **失败再落到本地 checkout**：clone 到 `fallback_dir`（默认
   `/tmp/dsh-plugins/<name>`），在该目录里跑插件自带的
   `install.py install --local-dir <dir>`：先 `npm install && npm run build`，
   再 `dsh plugin add file:<dir>`。`file:` 是**复制**进 profile
   node_modules，不是 `link:` 软链，所以 checkout 放在 /tmp、装完删掉都
   不影响 dsh 运行——插件源码不是运行期依赖。

单个插件也可手动安装/卸载：

```bash
cd ~/projects/dsh-plugins/dsh-plugin-skills-manager
python3 install.py install                 # 默认 add package.json 的 repository URL
python3 install.py install --local-dir .   # 本地构建后 file: 安装
python3 install.py uninstall
```

## 插件列表

编辑 `plugins.yaml` 即可增删插件，每个条目：

```yaml
plugins:
  - name: dsh-plugin-skills-manager            # 目录名/标识, --only 用它匹配
    package: '@maintainall/dsh-plugin-skills-manager'  # 卸载时 dsh plugin remove 用
    git: https://github.com/royenheart/dsh-plugin-skills-manager.git
    fallback_dir: ~/projects/dsh-plugins/dsh-plugin-skills-manager  # 可选; 默认 /tmp/dsh-plugins/<name>
```

- `git` 尚未推送时，第 1 步会失败；第 2 步 clone 也会失败。此时把
  `fallback_dir` 指向本地 checkout（如上），deploy 会跳过 clone 直接构建
  安装。推送后删除 `fallback_dir` 行即可回到纯 git 直装。
- 新插件按同一 bundle 约定提供 `cordis.patch.yml` + `dsh.bundle.patch` +
  `install.py`（参考 `dsh-plugin-skills-manager`）。

## 注意

`dsh-plugin-skills-manager` 需要先给 deepseek-harness 应用插件目录 `patches/` 下的
两个补丁并重新构建，否则安装成功也无法正常工作（详见插件 README 与
[#1413](https://github.com/deepseek-ai/deepseek-harness/discussions/1413)、
[#1427](https://github.com/deepseek-ai/deepseek-harness/discussions/1427)）。
