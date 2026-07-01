---
name: cua-desktop-control
description: Remote Windows desktop control via the cuactl HTTP service. Use this skill when the user asks you to perform actions on their remote Windows PC (screenshot, click, type, open/close apps, list apps). Call the cuactl service directly via curl in your shell tool.
version: 3.0.0
---

# CUA Desktop Control

You control a remote Windows desktop through the **`cuactl` HTTP microservice**.
It runs as a separate Docker container (`cua-cuactl`) on the same network as
you, reachable at `http://cuactl:8000`. You call it with `curl` in your shell
tool — no special package, no `pip install`, no `cua` binary, and **no need to
forward requests through Hermes**. You call it directly.

> **Do NOT** invent substitute commands. There is no `cuactl` binary on your
> path, no `cua` pip package to install, and no `cua do switch host` command.
> Those are hallucinations. The only correct way is `curl http://cuactl:8000/...`.

## Architecture (so you understand what happens)

```
You (AstrBot LLM, in cua-astrbot container)
  │  curl http://cuactl:8000/cuactl/<cmd>
  ▼
cuactl HTTP service (cua-cuactl container, FastAPI :8000)
  │  HTTPS + Bearer Token (configured in the cuactl container's env)
  ▼
Client Control Plane (on the Windows PC, port 9111)
  │
  ▼
Windows desktop (click / type / screenshot / apps)
```

- `cuactl` is its own container. It does NOT live inside AstrBot, and it
  does NOT live inside Hermes. Any container on the `cua-net` docker network
  can call it.
- Auth between cuactl and the Windows PC is handled inside the cuactl
  container (`CUACTL_TOKEN` env). You do not need to pass any token when
  calling `http://cuactl:8000` — internal network trust.
- Hermes Agent has the same `curl` patterns in its own system prompt, so
  Hermes can also call cuactl directly. You are not going through Hermes.

## Endpoints (all return JSON: `{"success": bool, "error": str, ...}`)

### Health check — run this first if unsure
```bash
curl -s http://cuactl:8000/health
```
Returns `{"status":"ok","endpoint":"<client-ip>:9111","token_configured":true/false}`.
If `status != ok` or the curl fails, the cuactl service is down — tell the
user to check `docker compose ps cuactl`.

### Screen
```bash
# Screenshot — returns base64 + writes PNG to /tmp in the cuactl container
curl -s -X POST http://cuactl:8000/cuactl/capture

# Screen dimensions
curl -s -X POST http://cuactl:8000/cuactl/screen-size
```

### Mouse
```bash
curl -s -X POST http://cuactl:8000/cuactl/click \
  -H 'Content-Type: application/json' \
  -d '{"x":100,"y":200,"button":"left"}'
# button: left | right | middle (default left)

curl -s -X POST http://cuactl:8000/cuactl/move \
  -H 'Content-Type: application/json' -d '{"x":100,"y":200}'

curl -s -X POST http://cuactl:8000/cuactl/scroll \
  -H 'Content-Type: application/json' -d '{"dx":0,"dy":-3}'

curl -s -X POST http://cuactl:8000/cuactl/drag \
  -H 'Content-Type: application/json' \
  -d '{"from_x":10,"from_y":10,"to_x":500,"to_y":500}'
```

### Keyboard
```bash
curl -s -X POST http://cuactl:8000/cuactl/type \
  -H 'Content-Type: application/json' -d '{"text":"hello world"}'

curl -s -X POST http://cuactl:8000/cuactl/press_key \
  -H 'Content-Type: application/json' -d '{"key":"enter"}'
# key examples: enter, escape, tab, F5, space, backspace, up/down/left/right
```

### Deterministic operations (no screenshot needed — prefer these)
```bash
curl -s -X POST http://cuactl:8000/cuactl/list-apps
curl -s -X POST http://cuactl:8000/cuactl/list-installed-apps

curl -s -X POST http://cuactl:8000/cuactl/app-info \
  -H 'Content-Type: application/json' -d '{"app_name":"Chrome"}'

curl -s -X POST http://cuactl:8000/cuactl/app-position \
  -H 'Content-Type: application/json' -d '{"app_name":"Chrome"}'

curl -s -X POST http://cuactl:8000/cuactl/open-app \
  -H 'Content-Type: application/json' -d '{"app_name":"Chrome"}'

curl -s -X POST http://cuactl:8000/cuactl/close-app \
  -H 'Content-Type: application/json' -d '{"app_name":"Chrome"}'
```

## Workflow

1. **Check state first.** `capture` or `list-apps` before any click.
2. **Prefer deterministic ops.** `list-apps` / `app-info` / `open-app` are
   faster and more reliable than screenshot + click.
3. **Typical flow:** `list-apps` → `open-app "Chrome"` → `capture` →
   analyze the screenshot → `click X Y` → `type "..."` → `press_key "enter"`.
4. **Coordinates** are absolute screen coords, origin top-left of the
   primary monitor. Use `app-position` to locate a window first.
5. **Safety.** Only perform actions the user explicitly requested. Never
   type passwords or sensitive data unless explicitly asked. When unsure,
   ask first.

## Prerequisites (the user must satisfy these)

Before any command can succeed, **all** of these must be true:

1. **Client Control Plane is running on the Windows PC.** Installed via
   `client/install.bat`; lives in the system tray. The tray icon shows
   connection status.
2. **Permission level is not `off`.** Set via the tray menu to `readonly`
   (screen + read ops), `full` (also click/type/open/close), or `strict`
   (full + per-action tray confirmation).
3. **Network reachability.** The `cuactl` container must be able to reach
   `CUACTL_ENDPOINT` (the Windows PC's IP:9111). Recommended: Tailscale /
   ZeroTier mesh. A bare public IP without HTTPS pinning is unsafe.
4. **`CUACTL_TOKEN` matches** the token generated on the Client side.

If any is missing, calls return `{"success": false, "error": "..."}` — see
the table below. Do **not** retry in a loop; diagnose and surface the issue.

## Troubleshooting (diagnose, don't hallucinate)

| Symptom | Likely cause | What to tell the user |
|---|---|---|
| `curl: (6) Could not resolve host: cuactl` | cuactl container not running, or you're not on cua-net | "cuactl 服务没启动。在服务器上运行 `docker compose up -d cuactl`。" |
| `{"success": false, "error": "client PC unreachable at ..."}` | Windows PC offline / Control Plane not running / network down | "你的 Windows 客户端 Control Plane 没有启动或网络不通。请检查托盘图标是否在运行，并确认 `CUACTL_ENDPOINT` 指向的 IP 可达。" |
| HTTP 403 Access Denied | Permission level set to `off` on the client | "请在 Windows 托盘菜单把权限级别从 OFF 切到 readonly 或 full。" |
| HTTP 401 Unauthorized | `CUACTL_TOKEN` mismatch between server and client | "Token 不匹配。重新生成客户端 Token 并更新服务端 `.env` 的 `CUACTL_TOKEN`，然后 `docker compose up -d` 重启。" |
| `health` returns `token_configured: false` | `CUACTL_TOKEN` env not set in cuactl container | "cuactl 容器没配 token。检查 `.env` 里 `CUACTL_TOKEN` 是否设置，然后 `docker compose up -d cuactl`。" |
| Screenshot returns but looks wrong / all black | Screen locked / UAC dialog foreground / multi-monitor coords off | Ask the user to unlock the screen or use `app-position` to find the window first. |

**Never** respond to a failure by installing packages, switching hosts, or
inventing alternative commands. Diagnose with the table above, or surface
the raw error to the user.

## Quick self-check (run when asked "can you control my PC?")

Instead of claiming readiness, verify each layer:

```bash
# 1. cuactl service alive?
curl -s http://cuactl:8000/health

# 2. Windows PC reachable + Control Plane running?
curl -s -X POST http://cuactl:8000/cuactl/list-apps
```

- If step 1 fails → cuactl service layer broken. Tell user to restart it.
- If step 1 ok but step 2 returns `{"success": false}` → client PC layer
  broken. Tell user the specific error from the table above.
- If both ok → report the actual endpoint and permission level, then
  proceed with the user's requested action.

**Do not claim "已就绪" without running these checks.** Honest diagnostics
beat confident-sounding fabrication.
