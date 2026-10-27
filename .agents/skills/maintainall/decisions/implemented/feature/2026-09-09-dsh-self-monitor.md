# Decision: dsh 实例自监控（manage 后台通用事件记录）

Status: implemented — deploy/ds-harness manage.py 新增独立采样器，把 dsh 实例的重启 / 热重载 / 断连事件记录到 manage 页时间线

## Problem

- dsh 对 `cordis.patch.yml` / bundle 列表的变更做 Cordis HMR 热重组合；连着的浏览器随之
  反复整页重载、SSE 反复断连，代理日志里表现为一串 `context canceled` 与整页启动簇。
- 用户常问"刚才是不是代理/网络抖动"，但从外面无法区分：是 dsh 自己重启/热重载（正常
  维护动作），还是实例故障，还是客户端风暴 —— 现有 manage 页只有瞬时快照（可达性 /
  进程 / 流量），没有事件史，无法事后回答这类问题。
- 本机 dsh 是较老版本，但 GitHub master 上同一机制原样保留（`watchUserPatches` →
  `entry.update`、`/plugins/events` 的 graph|rebuilt 帧、"boot graph 保持到整页重载"），
  因此监控不能绑定某版本的内部实现，必须通用且跨版本有效。

## Decision

在 `deploy/ds-harness/manage.py` 增加一个后台采样线程（默认 3s，`--monitor-interval` /
`DSH_MANAGE_MONITOR_INTERVAL` 可调，<=0 关闭），每 tick 对每个实例做四类**稳定外部
事实**采样并判定单发事件：

- 监听进程身份：`ss`/`/proc/net` + `/proc/<pid>/stat` field 22 启动时刻 → `restart` /
  `down` / `recover`；
- profile 文件内容指纹（sha256）：`cordis.patch.yml`、`package.json`(bundles)、
  `cordis.yml`、`settings.yaml` → `reload`（文本给出停用/启用插件与 bundle 增删）；进程
  重启同 tick 的 boot 文件重写折叠进 restart 事件，不重复报 reload；
- Caddy access 日志尾部窗口计数（`GET /` 启动簇、`/plugins/events` 订阅、5xx/中断）与
  `docker logs` 中按 upstream 端口过滤的 abort/拒连 → 无归因时的 `churn` 风暴事件
  （阈值 + 120s 冷却）。

事件以环形缓冲（200 条/实例，最新在前）落盘到独立文件 `data/manage-monitor.json`；
`build_state` 读取后随 `/api/state` 下发，manage 页每个实例卡片底部渲染时间线。事件
记录与插件开关写者的 `manage-state.json` 分离，避免状态写竞争；任一信号失败只跳过
本次采样，绝不把 manage 拖垮。首轮采样只建立基线，不产生事件。

## Alternatives considered

- **复用 manage-state.json 记录事件**：与 `set_plugin_enabled` / safe-mode 的读改写并发
  写同一个文件，有覆盖风险；→ 独立 `manage-monitor.json`，由采样器独占。
- **依赖 maintainall 插件日志（`plugin ready`）或 dsh 内部 API 判定重载**：非通用、随
  版本漂移，违背"必须通用"；→ 只观察 dsh 文档化的 profile 文件 + proc/ss + 自产 Caddy
  日志这些跨版本稳定事实（已在 GitHub master 验证路径与机制未变）。
- **只做进程级探活（pid/端口）**：会漏掉无进程重启的热重组合（10:45/10:58 那种）；
  → 增加 profile 文件指纹差分，覆盖 reload。
- **前端风暴判定放进 Caddy/nginx 侧或由浏览器埋点**：改动面大、依赖客户端配合；→
  采样器用代理侧可观测回显（access 日志 + 容器日志）做启发式 `churn`，并注明局限。

## Consequences

- manage 页现在能事后回答"刚才 dsh 是否重启/热重载/断连风暴"，并给出每个 toggle 之后
  的代理回显（如"停用 codex 后 2s 起 N 次整页重载"可被还原）。
- 采样成本：每 tick 每实例一次 `ss`/proc 快照 + 少量文件 sha + 一次共享的
  `docker logs --since`；空闲时开销可忽略。
- 局限（诚实声明）：看不到浏览器/webview 内部，`churn` 无法区分用户手动刷新与自动
  重载，属阈值启发式；同 pid 监听器热重建不产生 restart（由 reload/churn 覆盖）；
  事件时间在 manage 停机期间只能取 proc 启动时刻近似。
- 需要重启 manage 后端生效；systemd unit 路径不变，无需改 unit。
