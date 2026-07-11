# MaintainAll

面向个人 / 实验室环境的运维资产仓库，外加一套 **AIOps Agent**：用自然语言驱动仓库内的脚本、部署配置与模板，在白名单命令约束下完成检查、巡检与固化任务。

详细设计与开发说明见 [`AGENTS.md`](./AGENTS.md)。

---

## AIOps Agent

Agent 以本仓库为工作区，把运维先验（Skills）和可重复流程（Missions）接到同一条工作流上：

```
提问 → 评估可行性 → 生成任务板 → 人工 Review → 执行（ReAct）→ 校验 → 写报告
```

| 概念 | 位置 | 作用 |
|---|---|---|
| **Skills** | `.agents/skills/` | 领域先验（何时用、怎么做、约束与示例） |
| **Missions** | `.agents/missions/` | 可固化的任务 DAG + `allowed_commands` 白名单（可带 cron） |
| **Reports / Logs / History** | `<workspace>/.maintainall/{reports,logs,history}/` | 运行报告、会话日志与输入历史（不纳入版本控制；daemon 写入 mission 的 `repo_path` 工作区） |

报告正文语言由设置项 `report_language` 控制（默认 `zh-CN`，F1 可改），只约束 OBSERVE / 报告内容，不影响思考链等其它输出。会话结束时 TUI 会打印报告全文。

交互入口是 Textual TUI（`python maintain.py` / `maintainall`）：中央为对话与思考流，右侧为 Missions / Skills；运行中展示任务板与命令执行计数。固化 mission 可由 systemd user daemon 按 cron 调度（跳过人工 Review）。

交互模式（`Shift+Tab`）：

| 模式 | 行为 |
|---|---|
| **`readonly`**（默认） | 可规划与 Review，**不执行**任何 shell / `task.script` |
| **`restricted`** | Review 后仅执行 `allowed_commands` 白名单（整行 `re.fullmatch`） |
| **`unlimited`** | 自动 Review，命令不受白名单限制 |

真正执行时命令仍经应用层门禁（`run_allowed`），不是模型自觉约束。

### 快速开始

```bash
pip install -e ".[dev]"
python maintain.py          # 或 maintainall
```

可选：安装 user systemd unit 后启用定时 daemon（见 `deploy/systemd/` 与 `AGENTS.md`）。

配置与密钥：非密钥在 `~/.config/maintainall/config.toml`，API Key / SMTP 密码进 OS keyring（详见 `AGENTS.md`）。

---

## 仓库一级目录

本仓库同时存放「可被 Agent 引用的运维资产」。一级目录职责如下（不展开内部具体项目）：

| 目录 | 用途 |
|---|---|
| **`apps/`** | 独立小工具 / 应用工程（自包含代码与说明），与集群或日常工作流配套，但不属于通用部署清单。 |
| **`deploy/`** | 服务与基础设施的部署资产：compose、配置片段、systemd unit 等，用于把组件落到机器或集群上。 |
| **`maintaince/`** | 主机侧维护脚本（目录名为历史拼写）。偏账号与权限等运维操作，供人工或 Agent 按白名单调用。 |
| **`scripts/`** | 通用运维与辅助脚本集合（含模块化子目录），覆盖打包、环境、模块文件管理等可复用能力。 |
| **`stow-configs/`** | 以 [GNU Stow](https://www.gnu.org/software/stow/) 管理的 dotfile / 用户级配置包，按包链接到 `$HOME`。 |
| **`templates/`** | 可填充的配置与 modulefile 等模板，供生成正式配置或由 Agent / 脚本实例化。 |

与 Agent 强相关、但通常不手改业务内容的目录：

| 目录 | 用途 |
|---|---|
| **`.agents/`** | Agent 运行时资产：`skills/`、`missions/`（入库）；`reports/`、`logs/`（运行产物，默认忽略）。 |
| **`src/MaintainAll/`** | Agent 与 TUI 的 Python 包实现。 |
| **`docs/`** | 补充文档（若存在）。 |

---

## 文档索引

| 文档 | 内容 |
|---|---|
| [`AGENTS.md`](./AGENTS.md) | Agent 架构、Skills/Missions、配置、快捷键、开发测试 |
| `stow-configs/README.md` | Stow 包的安装与使用约定 |
| 各 `apps/*`、`deploy/*` 内 README | 对应应用或部署栈的说明（按需查阅） |
