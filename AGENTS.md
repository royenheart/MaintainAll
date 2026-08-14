# MaintainAll AIOps Agent

## 目标

仓库级 AIOps 控制台：用自然语言驱动运维任务，基于 **Skills**（先验知识）与 **Missions**（可固化 DAG），经 LangGraph 工作流执行白名单命令，并支持 cron daemon 与邮件通知。

- AI 模式 TUI（Layout C）：对话 / 思考流 + 右侧 Missions/Skills + 运行态任务板
- Skills：`.agents/skills/<name>/SKILL.md`
- Missions：`.agents/missions/<id>/MISSION.yaml`（可选 cron `schedule`）
- 运行时产物：`~/.maintainall/{reports,logs,history}/`（或 `data_dir`；不纳入版本控制）
- Daemon：按 **trusted_dirs** 下固化 mission 的 cron 触发 `run_mission()`；调度键为 `{abs_repo}::{mission.id}`；产物写入全局 `data_dir`

> **历史说明：** 旧版五 Tab TUI（浏览 / 对话 / 命令参考 / 模板填充 / 脚本工具）及 `PLUGIN_META` 插件面板已移除。Environment Modules 等能力改为 skill + mission + CLI（见 `scripts/modulefiles/manage_modules.py`）。

---

## 技术选型

| 项目 | 选择 | 理由 |
|---|---|---|
| TUI | **Textual** | AI 模式 Layout C |
| 工作流 | **LangGraph** | assess → board → review → ReAct → validate → finalize |
| LLM | **langchain-deepseek**（默认） | DeepSeek；`api_base` 非 DeepSeek 时可走 OpenAI 兼容 |
| 配置 | **pydantic-settings** + **keyring** + **platformdirs** | 非密钥 TOML；密钥进 OS keyring |
| Missions | **PyYAML** | DAG + `allowed_commands` 白名单 |
| 调度 | **croniter** + systemd user unit | 固化 mission 定时跑 |

---

## 架构概览

```
User / Cron
    → assess → build_board → review → react_loop → validate → finalize
                                              ↑___________| (mismatch / rebuild)
                                              validate may revise mission once → rebuild board
```

- **assess** 会带上当前 `mode`，由模型判断「在该模式下能否真正完成用户目标」；不可行则直接 reject，不进入 board / ReAct。
- **finalize** 后：交互会话只要有可保存的 mission draft，即可弹出固化（不要求 `validation_ok`）；也可稍后输入 `/solidify`。

包布局：

```
MaintainAll/
├── maintain.py / maintain_daemon.py   # 薄入口
├── pyproject.toml
├── src/MaintainAll/
│   ├── config.py                      # settings + keyring
│   ├── skills/  missions/  tools/
│   ├── graph/                         # LangGraph nodes + LLM
│   ├── memory/  notify/  cron/
│   ├── tui/                           # AI mode only
│   └── daemon/service.py
└── .agents/
    ├── skills/                        # 版本库跟踪（每个可信工作区一份）
    └── missions/                      # 版本库跟踪
# 运行时数据默认在 ~/.maintainall/（Settings data_dir）
#   reports/  logs/  history/  daemon_state.json  locks/
```

---

## UI（AI mode / Layout C）

- **中央：** 思考 / 助手流 + 底部输入
- **右侧（空闲）：** Missions 列表 → Skills 列表；点击打开详情浮层（Esc 关闭）
- **右侧（运行中）：** mission 描述、`allowed_commands` 执行计数、任务板状态（pending/running/done/failed）
- **模式：** `Shift+Tab` 循环（仅交互、未绑定 mission）：

| 模式 | Review | 命令执行 |
|---|---|---|
| **`readonly`**（默认） | 需要人工确认 | **禁止** `subprocess`（dry-run 记录跳过） |
| **`restricted`** | 需要人工确认 | 仅 `allowed_commands` 白名单（`re.fullmatch` 整行） |
| **`unlimited`** | 自动通过 | 任意非空命令（无白名单） |

- **Mission / cron 模式：** 仅允许该 mission 的 `allowed_commands` / 固化脚本；daemon 跳过交互 review

---

## Skills 与 Missions

### Skill（`.agents/skills/<name>/SKILL.md`）

YAML frontmatter：`name`、`description`。正文建议含 Context / Instructions / Constraints / Examples。启动时索引 name+description；触发时加载全文。

### Mission（`.agents/missions/<id>/MISSION.yaml`）

- `id` / `name` / `description` / `skills`
- `schedule`: `null` 或 cron 字符串（仅固化 mission 由 daemon 调度）
- `notify`: `{ on_complete, on_failure }`
- `allowed_commands`: `[{ pattern, cwd }]` — 完整命令行正则；相对 cwd；禁止裸 shell
- `tasks`: DAG（`needs`、`instruction`、`expect`；可选 `script` / 嵌套 `tasks`）

`expect` 类型包括：`contains`、`report_section`、`file_exists` 等。

### 内置内容

| Skill | Missions |
|---|---|
| `daed-connectivity` | `daed-connectivity-check` — gost 连通性 + Telegram CIDR 核对 |
| `modulefile-manager` | `modulefiles-list`、`modulefiles-scan-generate` — 调用 `manage_modules.py` CLI |

---

## 配置与密钥

| 类型 | 位置 |
|---|---|
| 非密钥 | `~/.config/maintainall/config.toml`（platformdirs） |
| 可信工作区 | `trusted_dirs`（绝对路径列表）；TUI 当前工作区取启动时的 `cwd`（不写入配置） |
| 运行时数据 | `data_dir`（默认 `~/.maintainall`；可用 `MAINTAINALL_DATA_DIR`） |
| 密钥（`api_key`、SMTP 密码） | OS keyring，service `maintainall`；内存中为 `SecretStr` |
| 环境覆盖 | `MAINTAINALL_*`、`DEEPSEEK_API_KEY` |
| keyring 不可用 | `~/.config/maintainall/secrets.toml`（mode `0600`）+ TUI 警告 |

默认：

- `api_base`: `https://api.deepseek.com`
- `model`: `deepseek-v4-flash`（可改为 `deepseek-v4-pro`）
- `agent_mode`: `readonly`
- `report_language`: `zh-CN`（约束 assess 的 `reason`、OBSERVE / 报告正文；不影响 RUN 命令与协议关键字）
- `data_dir`: `~/.maintainall`
- `trusted_dirs`: 旧配置若只有 `repo_path`、无此字段，加载时迁入 `trusted_dirs` 后不再持久化 `repo_path`

首次运行若存在旧版 `~/.maintainall.json`，会迁移到 TOML + keyring。TUI 设置（F1）可改 model / api_base / SMTP / 默认模式 / trusted dirs；密钥字段掩码显示。在未信任的目录启动 TUI 时会询问是否加入 `trusted_dirs`。

---

## 快速开始

```bash
pip install -e ".[dev]"
python maintain.py
# user systemd daemon — run from the same conda/venv used for pip install:
./deploy/systemd/install-user-daemon.sh
# 可选：loginctl enable-linger "$USER"
```

也可使用入口脚本：`maintainall` / `maintainall-daemon`。不要依赖 systemd 继承登录 shell 的 conda PATH；安装脚本会把当前环境的绝对路径写进 unit。

独立 CLI（modulefiles，非 TUI 插件）：

```bash
python scripts/modulefiles/manage_modules.py list
python scripts/modulefiles/manage_modules.py scan /opt/software
python scripts/modulefiles/manage_modules.py add cuda 12.2 /usr/local/cuda-12.2
python scripts/modulefiles/manage_modules.py delete cuda 12.2
```

---

## dsh 插件集（apps/）

本仓库 `apps/` 下维护一组自用的 **dsh 插件**（DeepSeek Harness 插件集），每个插件是一个独立包（自带 `package.json`、host/client 入口、`dsh.client` 清单），构建出 `lib/` 后用 `dsh plugin add link:...` 装进 profile 的 `node_modules`，在 `maintainall.yml` 里按**裸包名**引用（dsh 的正常加载方式；不发布 npm），统一挂到同一个插件清单 `stow-configs/dsh/maintainall.yml` 下，便于换机器时用 `dsh` 快速迁移。

### 目录规范

每个 dsh 插件放在 `apps/<name>/`，结构如下（以 `apps/dsh-plugin-skills-manager/` 为例）：

```
apps/<name>/
├── package.json            # dsh 插件清单: main/./client + dsh.client.inject + peerDeps
├── tsconfig.json
├── README.md
├── src/
│   ├── index.ts            # host 入口: 默认导出 Cordis Service/apply
│   ├── client.ts           # client 入口: 导出 apply (package.json exports[./client])
│   ├── core/               # 纯逻辑, 不 import 任何 dsh 包 (可独立单测)
│   └── locales/            # zh.ts / en.ts / keys.ts / index.ts (i18n 字典)
└── tests/                  # node --test 单测 (*.test.ts)
```

- **host 入口** (`src/index.ts`)：默认导出一个 Cordis `Service`（或 `apply(ctx)` 函数），通过 `super(ctx, '服务名')` 提供 `ctx.<服务名>`；依赖用 `static inject = [...]` 声明，初始化写进 `async *[Service.init]()`。
- **client 入口** (`src/client.ts`)：`package.json` 的 `exports["./client"]` 指向它，`dsh.client.inject` 声明 client 依赖；UI 用 `React.createElement`（不用 JSX），挂载点用 `ctx.slots.register`。
- **core/**：作用域解析、技能识别、schema 校验等纯逻辑必须无 dsh 依赖，用 `node --test` 直接单测（Node 24 原生 TS type-stripping，`import './x.ts'` 带 `.ts` 后缀）。

### i18n

复用 dsh 自带的 locale 框架（`@deepseek-ai/dsh-client-locale`）：

- 在 `src/locales/` 提供 `zh` / `en` 两套扁平字典（键 -> 模板串，占位符 `{name}`），`keys.ts` 用 `SKILL_MANAGER_KEYS as const` 声明键全集作为双语完整性的唯一来源；
- 用 `ctx.locale.register('命名空间', { zh, en })` 注册、`ctx.locale.bind('命名空间')` 取翻译函数；所有 UI 文案都走这个 API，禁止硬编码字符串；
- 双语键集合与占位符对称性由单测强制（`tests/i18n.test.ts`）。

### 技能识别范围

涉及「技能识别」的插件只认 `.agents` 通用目录与 dsh 自身技能目录，其它 agent 的技能目录不识别：

| source | 路径 | 含义 |
|---|---|---|
| `project-dsh` | `<project>/.dsh/skills` | dsh 自身项目目录 |
| `project-agents` | `<project>/.agents/skills` | `.agents` 通用目录 |
| `user-dsh` | `$DSH_HOME/skills` | dsh 自身用户目录 |
| `user-agents` | `~/.agents/skills` | 用户 `.agents` |

`.claude/skills`、`.codex/skills`、`.cursor/rules` 等其它 agent 目录以及 `bundled`/`runtime`/`custom` 来源一律不识别。

### stow-configs 联动要求（必做）

新增 / 移除 / 改动一个 dsh 插件时，**必须同步更新** `stow-configs/dsh/maintainall.yml`（插件清单，顶层 loader entry 数组），否则安装结果不会包含该插件。

- `stow-configs/dsh/` **只放 `maintainall.yml`**：stow 把它软链到 **profile 目录**
  （`stow dsh -t "$DSH_HOME/profiles/<name>"` → `$DSH_HOME/profiles/<name>/maintainall.yml`）；
  不要把 cordis 配置或安装脚本放进该目录（stow 会一并链接、且覆盖 cordis 配置会导致
  stow 应用失败）。`maintainall.yml` 必须和 `cordis.yml` 同目录（profile 目录），这样
  里面的裸包名才会从 profile 的 node_modules 解析。
- cordis 配置（`$DSH_HOME/cordis.patch.yml`，home 级、对每个 profile 生效）**由用户手动修改**，加一条 `cordis:include` 引用即可；之后新增/移除插件只改 `maintainall.yml`，cordis 配置装一次不用再动：

```yaml
- insert:
    - id: maintainall
      name: cordis:include
      config:
        path: ./maintainall.yml
```

- 完整安装 / 卸载步骤、嵌套配置原理与示例见 `stow-configs/README.md`；写插件时若涉及 cordis 配置，直接沿用上面这条 `cordis:include`，不要在 `maintainall.yml` 之外再引入新的 cordis 文件。

### 测试

```bash
cd apps/<name>
npm test            # node --test tests/*.test.ts (纯逻辑, 无需 dsh 运行时)
node --check src/index.ts src/client.ts   # host/client 语法自检
npm run build       # tsdown 打包 (需 dsh 仓库构建环境)
```

---

## Daemon、报告与通知

1. Daemon 迭代 `trusted_dirs`，加载各目录下带非空 `schedule` 的固化 mission；触发时 `chdir` 到该工作区并 `run_mission()`（跳过 review）。
2. 调度身份为 `{abs_repo}::{mission.id}`；全局锁与 last_run 写在 `data_dir/locks/`、`data_dir/daemon_state.json`（可从旧 `.agents/.daemon_state.json` 迁移）。
3. 完成后写 `data_dir/reports/<mission-id>@<repo-name>-<timestamp>.md`。
4. 若配置了邮件 → 发信；否则尝试本地 `sendmail`/`mail`；都失败则保留报告。
5. 每轮 scan 重新 `load_settings()`，改可信目录或 YAML 里的 `schedule` 一般无需重启 daemon。

---

## 键盘快捷键

| 快捷键 | 功能 |
|---|---|
| `Shift+Tab` | 循环 agent 模式（交互 unbound） |
| `↑` / `↓`（光标在输入开头） | 切换历史输入（按仓库 `.maintainall/history/prompt.jsonl` 落盘） |
| `Tab` | `/run`：在输入框上方弹出候选（↑↓ 选择，Enter/Tab 确认，Esc 关闭）；其它：接受补全预览 |
| `/run <mission-id\|name>` | 运行已固化 mission（支持前缀；Tab 打开候选框） |
| `/solidify` | 将当前 memory 中的 mission 固化到 `.agents/missions/` |
| `F1` | 设置 |
| `Escape` | 关闭浮层 / 取消 |
| `Ctrl+Q` | 退出 |

---

## 开发与测试

```bash
pip install -e ".[dev]"
python -m pytest -q
```

设计与实现计划见 `docs/superpowers/specs/2026-07-10-aiops-agent-design.md` 与 `docs/superpowers/plans/2026-07-10-aiops-agent.md`。
