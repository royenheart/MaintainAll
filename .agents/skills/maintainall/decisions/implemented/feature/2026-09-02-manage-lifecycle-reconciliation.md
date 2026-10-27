# Decision: deploy manage 后端生命周期自愈（pid 文件与端口事实对账）

Status: implemented — deploy.py 现在按“端口事实 + pid 文件 + 进程身份”对账 manage 状态，而不是只信 pid 文件。

## Problem

`deploy.py` 之前只凭 `data/manage.pid`（`os.kill(pid, 0)`）判断 manage 是否在跑。一旦 pid 文件缺失或过期，三种症状同时出现：

1. 一次失败的重复启动会 `EADDRINUSE` 退出并 unlink 自己刚写的 pid 文件（原文件已被覆盖），而**真正在跑的旧 manage 变成“孤儿”**——没人知道它的 pid；
2. `status` 因此误报 `manage server: not running`；`up`/`reload` 再拉一个 manage 继续撞 `EADDRINUSE` 报错退出；`down` 也停不掉孤儿；
3. 孤儿可能跑的是旧代码：2026-09-01 cb8403a 之后 manage 需要 401 探活分支（token 墙 401 视为“在线 · 需 token”）才能把健康实例判在线，而旧孤儿仍把 401 当失败，管理界面把健康 dsh 实例显示成“离线”。实际事故即由此而来。

## Decision

manage 状态改为三方对账（pid 文件内容 / 端口上的真实监听者 / 进程身份）：

- `manage_port_listener_pid(port, *, require_manage=True)`：先解析 `ss -ltnpH` 的 `pid=`；ss 拿不到时回退 `/proc/net/{tcp,tcp6}` 的 socket inode → `/proc/<pid>/fd` 扫描（镜像 manage.py `find_listener_pid`）。`require_manage=True` 时还要校验该进程 cmdline 含 `manage.py`，**绝不**收养/停掉恰好占用端口的其它服务；cmdline 不可读视为非 manage（宁可判不到，不误杀）。
- `classify_manage_state` 把事实归为四态：`running`（pid 文件与监听者一致）/ `orphan`（有 manage 在监听但 pid 文件缺失/过期/指向别处）/ `stale`（pid 文件过期、端口无 manage）/ `stopped`。
- `status` 如实打印四态；`orphan` 会附一句“up/reload 会重启它并纳入管理”，不再静默撒谎。
- `up`/`reload`（`start_manage`）：`running` 直接复用；`orphan` 先停后以当前代码重启并重建 pid 文件；`stale` 清理后新起；spawn 后 0.4s 内子进程退出时**复查端口**——若 manage 已在监听则收养写 pid 并成功返回，否则报错并提示占用者 pid。
- `down`（`stop_manage`）：pid 文件有效优先；无效/缺失时按端口找 manage 进程停；SIGTERM 后轮询端口释放（≤5s），超时才 SIGKILL；从不杀死 cmdline 不是 `manage.py` 的进程；`stale` 只删 pid 文件。

## Alternatives considered

- **import manage.py 的 `find_listener_pid` 复用**：两文件本就同目录成对发布，但 deploy.py 一贯自包含（`parse_instances_yml` 注释明示 mirroring manage.py），避免导入耦合与将来 manage.py 加模块级副作用时反噬 deploy.py。选了在 deploy.py 内镜像实现并补 cmdline 校验。
- **`status` 自动写回 pid 文件“收养”孤儿**：让只读状态命令产生副作用，行为难预期；改为 status 只报告、`up`/`reload` 自愈。
- **`orphan` 一律复用不重启**：无法保证在跑的是与 deploy.py 同目录的当前 manage.py 代码——这正是本次事故根因之一。manage 无状态、无会话，重启代价只是 /manage 秒级中断，故 orphan 一律替换重启。

## Consequences

- pid 文件缺失/过期时，`deploy.py status / up / reload / down` 行为正确且自愈：孤儿会被换掉、pid 文件重建、`down` 能停干净；旧代码孤儿不会再静默把健康实例判离线。
- `running` 判断需要能读 `/proc/<pid>/cmdline` 与宿主进程表；在隔离 PID 命名空间（沙箱/容器）里跑 deploy.py 会把“在跑的宿主 manage”误判为 `stale`——只影响隔离环境内的只读诊断，宿主上正常运行不受影响。
- 每次状态判定多一次 `ss` 子进程（超时上限 5s 兜底）和可能的 `/proc` 扫描，毫秒级，可接受。
- 行为说明已写入 `deploy/ds-harness/README.md`。
