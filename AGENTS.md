# MaintainAll AIOps Agent

## 目标

仓库级 AIOps 控制台：用自然语言驱动运维任务，基于 **Skills**（先验知识）与 **Missions**（可固化 DAG），经 LangGraph 工作流执行白名单命令，并支持 cron daemon 与邮件通知。

- AI 模式 TUI（Layout C）：对话 / 思考流 + 右侧 Missions/Skills + 运行态任务板
- Skills：`.agents/skills/<name>/SKILL.md`
- Missions：`.agents/missions/<id>/MISSION.yaml`（可选 cron `schedule`）
- 报告：`.agents/reports/`（gitignored）
- Daemon：按固化 mission 的 cron 触发 `run_mission()`

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
```

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
    ├── skills/                        # 版本库跟踪
    ├── missions/                      # 版本库跟踪
    └── reports/                       # gitignored
```

---

## UI（AI mode / Layout C）

- **中央：** 思考 / 助手流 + 底部输入
- **右侧（空闲）：** Missions 列表 → Skills 列表；点击打开详情浮层（Esc 关闭）
- **右侧（运行中）：** mission 描述、`allowed_commands` 执行计数、任务板状态（pending/running/done/failed）
- **模式：** `Shift+Tab` 循环 `readonly` → `restricted` → `unlimited`（仅交互、未绑定 mission）
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
| 密钥（`api_key`、SMTP 密码） | OS keyring，service `maintainall`；内存中为 `SecretStr` |
| 环境覆盖 | `MAINTAINALL_*`、`DEEPSEEK_API_KEY` |
| keyring 不可用 | `~/.config/maintainall/secrets.toml`（mode `0600`）+ TUI 警告 |

默认：

- `api_base`: `https://api.deepseek.com`
- `model`: `deepseek-v4-flash`（可改为 `deepseek-v4-pro`）
- `agent_mode`: `readonly`

首次运行若存在旧版 `~/.maintainall.json`，会迁移到 TOML + keyring。TUI 设置（F1）可改 model / api_base / SMTP / 默认模式；密钥字段掩码显示。

---

## 快速开始

```bash
pip install -e ".[dev]"
python maintain.py
# daemon
cp deploy/systemd/maintainall-agent.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now maintainall-agent
```

也可使用入口脚本：`maintainall` / `maintainall-daemon`（需保证 `~/.local/bin` 在 PATH，或按 unit 中的 `ExecStart` 调整）。

独立 CLI（modulefiles，非 TUI 插件）：

```bash
python scripts/modulefiles/manage_modules.py list
python scripts/modulefiles/manage_modules.py scan /opt/software
python scripts/modulefiles/manage_modules.py add cuda 12.2 /usr/local/cuda-12.2
python scripts/modulefiles/manage_modules.py delete cuda 12.2
```

---

## Daemon、报告与通知

1. Daemon 加载带非空 `schedule` 的固化 mission；触发时 `run_mission()`（mission 权限、跳过 review）。
2. 每 mission 一把锁，避免重叠执行。
3. 完成后始终写 `.agents/reports/<mission-id>-<timestamp>.md`。
4. 若配置了 SMTP → 发信；否则尝试本地 `sendmail`/`mail`；都失败则保留报告并打警告日志。

---

## 键盘快捷键

| 快捷键 | 功能 |
|---|---|
| `Shift+Tab` | 循环 agent 模式（交互 unbound） |
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
