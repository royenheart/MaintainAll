#!/usr/bin/env python3
"""Standalone management backend for deploy/ds-harness.

Serves the /manage single-page UI and a JSON API for monitoring dsh web
instances and controlling their profile's external plugin loading. The
backend is intentionally independent from dsh: every metric is collected
best-effort, a failed metric only degrades its own card, and the control
paths edit dsh profile files on disk (`package.json` bundle lists) without
booting dsh — so a dsh instance that cannot start because of a broken plugin
can still be recovered from /manage.

Usage:
    python3 manage.py --port 9097
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CADDYFILE_PATH = BASE_DIR / 'Caddyfile'
INSTANCES_YML_PATH = BASE_DIR / 'instances.yml'
DATA_DIR = BASE_DIR / 'data'
LOGS_DIR = DATA_DIR / 'logs'
STATE_PATH = DATA_DIR / 'manage-state.json'

DEFAULT_PORT = 9097
DEFAULT_DSH_PORT = 3080
DEFAULT_CADDY_CONTAINER = 'dsh-proxy'
CADDY_CONTAINER = DEFAULT_CADDY_CONTAINER
DSH_MARKER = '__DSH_BOOT__'
PROBE_TIMEOUT_SECONDS = 2.0
LOG_TAIL_BYTES = 256 * 1024

INBOX_BUNDLES: dict[str, list[str]] = {
    'web': ['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-web-app'],
    'headless': ['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-headless'],
}
DEFAULT_INBOX = ['@deepseek-ai/dsh-base']


def expand(path: str) -> Path:
    return Path(path).expanduser()


def read_json(path: Path) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.json.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    os.replace(tmp, path)


# ---------------------------------------------------------------- instances

def parse_caddyfile_mappings() -> list[tuple[int, int]]:
    """Return [(proxy_port, dsh_port), ...] from the generated Caddyfile.

    Only the `reverse_proxy` inside the final `handle` block of a site is a dsh
    upstream; the `reverse_proxy` inside `handle_path /manage/*` points at the
    manage backend and must be skipped, otherwise the manage backend shows up
    as a dsh instance.
    """
    mappings: list[tuple[int, int]] = []
    if not CADDYFILE_PATH.is_file():
        return mappings
    content = CADDYFILE_PATH.read_text(encoding='utf-8')
    current_proxy: int | None = None
    in_manage_block = False
    manage_depth = 0
    for line in content.splitlines():
        stripped = line.strip()
        site = re.match(r'^https?://(?:\[?[0-9a-fA-F.:]+\]?|):(\d+)\s*\{', stripped)
        if site is not None:
            current_proxy = int(site.group(1))
            in_manage_block = False
            manage_depth = 0
            continue
        if current_proxy is None:
            continue
        if in_manage_block:
            manage_depth += stripped.count('{') - stripped.count('}')
            if manage_depth <= 0:
                in_manage_block = False
            continue
        if stripped.startswith('handle_path /manage/*'):
            in_manage_block = True
            manage_depth = stripped.count('{') - stripped.count('}')
            if manage_depth <= 0:
                in_manage_block = False
            continue
        match = re.match(r'^reverse_proxy\s+127\.0\.0\.1:(\d+)\s*\{?', stripped)
        if match is not None:
            dsh_port = int(match.group(1))
            if (current_proxy, dsh_port) not in mappings:
                mappings.append((current_proxy, dsh_port))
    return mappings


def parse_instances_yml() -> list[dict]:
    """Return instance definitions from instances.yml (best-effort)."""
    if not INSTANCES_YML_PATH.is_file():
        return []
    try:
        import yaml
    except ImportError:
        return []
    try:
        data = yaml.safe_load(INSTANCES_YML_PATH.read_text(encoding='utf-8')) or {}
    except Exception:
        return []
    if not isinstance(data, dict):
        return []
    items = data.get('instances') or []
    if not isinstance(items, list):
        return []
    result: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        port = item.get('port')
        if not isinstance(port, int) or not 1 <= port <= 65535:
            continue
        result.append({
            'name': str(item.get('name') or f'dsh-{port}'),
            'port': port,
            'profile': str(item.get('profile') or 'web'),
            'home': str(item.get('home') or '~/.dsh'),
        })
    return result


def resolve_instances() -> tuple[list[dict], list[str]]:
    """Merge Caddyfile mappings with instances.yml into monitorable instances."""
    warnings: list[str] = []
    mappings = parse_caddyfile_mappings()
    defined = {item['port']: item for item in parse_instances_yml()}
    instances: list[dict] = []
    seen_ports: set[int] = set()
    for proxy_port, dsh_port in mappings:
        base = defined.get(dsh_port)
        if base is None:
            base = {
                'name': f'dsh-{dsh_port}',
                'port': dsh_port,
                'profile': 'web',
                'home': '~/.dsh',
            }
        instance = {**base, 'proxy_port': proxy_port}
        instances.append(instance)
        seen_ports.add(dsh_port)
    for dsh_port, base in defined.items():
        if dsh_port in seen_ports:
            continue
        instances.append({**base, 'proxy_port': dsh_port})
        seen_ports.add(dsh_port)
    if not instances:
        instances.append({
            'name': 'dsh-3080',
            'port': DEFAULT_DSH_PORT,
            'profile': 'web',
            'home': '~/.dsh',
            'proxy_port': DEFAULT_DSH_PORT,
        })
    if not INSTANCES_YML_PATH.is_file():
        warnings.append('instances.yml 不存在，使用默认实例（端口 3080，profile web，~/.dsh）')
    else:
        try:
            import yaml  # noqa: F401
        except ImportError:
            warnings.append('PyYAML 不可用，instances.yml 未解析，使用默认实例')
    return instances, warnings


# ---------------------------------------------------------------- state

def read_state() -> dict:
    if STATE_PATH.is_file():
        try:
            data = read_json(STATE_PATH)
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {'instances': {}}


def write_state(data: dict) -> None:
    write_json_atomic(STATE_PATH, data)


def state_for(port: int, state: dict | None = None) -> dict:
    state = state if state is not None else read_state()
    instances = state.setdefault('instances', {})
    return instances.setdefault(str(port), {})


# ---------------------------------------------------------------- profile control

def profile_dir(home: str, profile: str) -> Path:
    return expand(home) / 'profiles' / profile


def read_profile_manifest(instance: dict) -> tuple[dict | None, Path, str | None]:
    """Return (manifest, manifest_path, error)."""
    path = profile_dir(instance.get('home', '~/.dsh'), instance.get('profile', 'web')) / 'package.json'
    if not path.is_file():
        return None, path, 'profile 不存在（package.json 未找到）'
    try:
        return read_json(path), path, None
    except (OSError, json.JSONDecodeError) as error:
        return None, path, f'profile package.json 读取失败: {error}'


def write_profile_manifest(path: Path, data: dict) -> str | None:
    try:
        write_json_atomic(path, data)
        return None
    except OSError as error:
        return f'profile package.json 写入失败: {error}'


def inbox_bundles(profile: str) -> list[str]:
    return list(INBOX_BUNDLES.get(profile, DEFAULT_INBOX))


def current_bundles(manifest: dict | None) -> list[str]:
    if manifest is None:
        return []
    profile = (manifest.get('dsh') or {}).get('profile') or {}
    return list(profile.get('bundles') or [])


def package_declares_bundle(instance: dict, package_name: str) -> bool:
    path = profile_dir(instance.get('home', '~/.dsh'), instance.get('profile', 'web')) / 'node_modules' / package_name / 'package.json'
    try:
        data = read_json(path)
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(((data.get('dsh') or {}).get('bundle') or {}).get('patch'), str)


def plugin_items(instance: dict, manifest: dict | None, state: dict) -> list[dict]:
    bundles = current_bundles(manifest)
    in_box = set(inbox_bundles(instance.get('profile', 'web')))
    deps = (manifest or {}).get('dependencies') or {}
    saved = state_for(instance['port'], state).get('saved_bundles') or []
    names: set[str] = set()
    for name in [*bundles, *saved, *deps.keys()]:
        if name and name not in in_box:
            names.add(name)
    items: list[dict] = []
    for name in sorted(names):
        items.append({
            'name': name,
            'enabled': name in bundles,
            'installed': name in deps,
            'spec': deps.get(name, ''),
            'declares_bundle': package_declares_bundle(instance, name),
        })
    return items


def safe_mode_active(instance: dict, manifest: dict | None, state: dict) -> bool:
    st = state_for(instance['port'], state)
    if not st.get('saved_bundles'):
        return False
    bundles = current_bundles(manifest)
    in_box = inbox_bundles(instance.get('profile', 'web'))
    return bundles == in_box


def set_plugin_enabled(instance: dict, package: str, enabled: bool) -> dict:
    manifest, path, error = read_profile_manifest(instance)
    if error is not None:
        return {'ok': False, 'error': error}
    state = read_state()
    st = state_for(instance['port'], state)
    bundles = current_bundles(manifest)
    in_box = inbox_bundles(instance.get('profile', 'web'))

    # A per-plugin toggle always leaves safe mode: restore the saved bundles
    # first so the user's explicit per-plugin choice is not silently absorbed
    # by the safe-mode snapshot.
    if safe_mode_active(instance, manifest, state) and st.get('saved_bundles'):
        bundles = list(st['saved_bundles'])
        st['saved_bundles'] = []
        write_state(state)

    if enabled:
        if package in bundles:
            return {'ok': True, 'note': '插件已启用'}
        deps = (manifest or {}).get('dependencies') or {}
        if package not in deps:
            return {'ok': False, 'error': f'{package} 不在 profile dependencies 中，先通过 `dsh plugin add` 安装'}
        if not package_declares_bundle(instance, package):
            return {'ok': False, 'error': f'{package} 未声明 dsh.bundle，不能作为 bundle 启用'}
        # Insert after in-box bundles, preserving a stable layer order.
        insert_at = len([b for b in bundles if b in in_box])
        bundles.insert(insert_at, package)
    else:
        if package in bundles:
            bundles.remove(package)
        else:
            return {'ok': True, 'note': '插件已停用'}

    if manifest is None:
        return {'ok': False, 'error': 'profile manifest missing'}
    dsh = manifest.setdefault('dsh', {})
    prof = dsh.setdefault('profile', {})
    prof['bundles'] = bundles
    error = write_profile_manifest(path, manifest)
    if error is not None:
        return {'ok': False, 'error': error}
    state = read_state()
    return {
        'ok': True,
        'bundles': bundles,
        'plugins': plugin_items(instance, manifest, state),
        'safe_mode': safe_mode_active(instance, manifest, state),
        'note': '已写入 dsh.profile.bundles；dsh 重启后生效（运行中的 dsh 不会热加载 bundle 列表）',
    }


def set_safe_mode(instance: dict, enabled: bool) -> dict:
    manifest, path, error = read_profile_manifest(instance)
    if error is not None:
        return {'ok': False, 'error': error}
    if manifest is None:
        return {'ok': False, 'error': 'profile manifest missing'}
    state = read_state()
    st = state_for(instance['port'], state)
    bundles = current_bundles(manifest)
    in_box = inbox_bundles(instance.get('profile', 'web'))

    if enabled:
        if safe_mode_active(instance, manifest, state):
            return {'ok': True, 'note': '安全模式已启用'}
        st['saved_bundles'] = list(bundles)
        prof_bundles = list(in_box)
        note = '安全模式已启用：外部插件已从 dsh.profile.bundles 移除并记录；重启 dsh 后生效'
    else:
        saved = st.get('saved_bundles')
        if not saved:
            return {'ok': False, 'error': '没有已保存的 bundles 记录，无法退出安全模式'}
        prof_bundles = list(saved)
        st['saved_bundles'] = []
        note = '安全模式已关闭：已恢复之前的 dsh.profile.bundles；重启 dsh 后生效'

    dsh = manifest.setdefault('dsh', {})
    prof = dsh.setdefault('profile', {})
    prof['bundles'] = prof_bundles
    write_state(state)
    error = write_profile_manifest(path, manifest)
    if error is not None:
        return {'ok': False, 'error': error}
    state = read_state()
    return {
        'ok': True,
        'bundles': prof_bundles,
        'plugins': plugin_items(instance, manifest, state),
        'safe_mode': safe_mode_active(instance, manifest, state),
        'note': note,
    }


# ---------------------------------------------------------------- monitoring

def probe_dsh(port: int) -> dict:
    import urllib.error
    import urllib.request
    url = f'http://127.0.0.1:{port}/'
    request = urllib.request.Request(
        url,
        headers={'Host': f'127.0.0.1:{port}', 'User-Agent': 'dsh-manage/1'},
    )
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=PROBE_TIMEOUT_SECONDS) as response:
            body = response.read(131072).decode('utf-8', 'replace')
            return {
                'ok': True,
                'latency_ms': round((time.time() - started) * 1000, 1),
                'marker': DSH_MARKER in body,
                'status': response.status,
            }
    except Exception as error:
        return {'ok': False, 'error': f'{type(error).__name__}: {error}'}


def count_sessions(home: str) -> dict:
    sessions_dir = expand(home) / 'sessions'
    if not sessions_dir.is_dir():
        return {'ok': True, 'count': 0, 'note': f'没有 sessions 目录（{sessions_dir}）'}
    try:
        count = sum(1 for child in sessions_dir.iterdir() if child.is_dir())
        return {'ok': True, 'count': count}
    except OSError as error:
        return {'ok': False, 'error': f'读取 sessions 目录失败: {error}'}


def pid_for_socket_inode(inode: str) -> int | None:
    proc = Path('/proc')
    if not proc.is_dir():
        return None
    for pid_dir in proc.iterdir():
        if not pid_dir.name.isdigit():
            continue
        fd_dir = pid_dir / 'fd'
        try:
            fds = list(fd_dir.iterdir())
        except OSError:
            continue
        for fd in fds:
            try:
                target = os.readlink(fd)
            except OSError:
                continue
            if target == f'socket:[{inode}]':
                return int(pid_dir.name)
    return None


def pid_from_proc_net(port: int) -> int | None:
    for proto in ('tcp', 'tcp6'):
        path = Path('/proc/net') / proto
        try:
            lines = path.read_text(encoding='utf-8').splitlines()
        except OSError:
            continue
        for line in lines[1:]:
            parts = line.split()
            if len(parts) < 10:
                continue
            local = parts[1]
            try:
                port_hex = local.rsplit(':', 1)[1]
                if int(port_hex, 16) != port:
                    continue
            except (ValueError, IndexError):
                continue
            pid = pid_for_socket_inode(parts[9])
            if pid is not None:
                return pid
    return None


def find_listener_pid(port: int) -> int | None:
    if shutil.which('ss') is not None:
        try:
            completed = subprocess.run(['ss', '-ltnpH'], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            completed = None
        if completed is not None and completed.returncode == 0:
            for line in completed.stdout.splitlines():
                parts = line.split()
                if len(parts) < 6:
                    continue
                local = parts[3]
                match = re.match(r'^(?:\[?[0-9a-fA-F.:]+\]?|\*):(\d+)$', local)
                if match is None or int(match.group(1)) != port:
                    continue
                pid_match = re.search(r'pid=(\d+)', parts[-1])
                if pid_match is not None:
                    return int(pid_match.group(1))
    # ss may not show pid= (privilege/iproute build); /proc is the fallback.
    return pid_from_proc_net(port)


def parse_ps_line(line: str) -> dict | None:
    fields = line.split(None, 5)
    if len(fields) < 6:
        return None
    try:
        return {
            'pid': int(fields[0]),
            'cpu_percent': float(fields[1]),
            'mem_percent': float(fields[2]),
            'rss_mb': round(int(fields[3]) / 1024, 1),
            'elapsed': fields[4],
            'cmd': fields[5],
        }
    except ValueError:
        return None


def ps_info_for_pid(pid: int) -> dict:
    if shutil.which('ps') is None:
        return {'ok': False, 'error': 'ps 不可用', 'pid': pid}
    try:
        completed = subprocess.run(
            ['ps', '-o', 'pid=,pcpu=,pmem=,rss=,etime=,cmd=', '-p', str(pid)],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {'ok': False, 'error': f'ps 失败: {error}', 'pid': pid}
    if completed.returncode != 0:
        return {'ok': False, 'error': f'ps 失败: {completed.stderr.strip() or completed.returncode}', 'pid': pid}
    lines = completed.stdout.strip().splitlines()
    if not lines:
        return {'ok': False, 'error': '进程已退出', 'pid': pid}
    parsed = parse_ps_line(lines[-1])
    if parsed is None:
        return {'ok': False, 'error': '无法解析 ps 输出', 'pid': pid}
    return {'ok': True, **parsed}


def dsh_web_processes() -> list[dict]:
    """Best-effort list of running `dsh web` processes from ps."""
    if shutil.which('ps') is None:
        return []
    try:
        completed = subprocess.run(
            ['ps', '-eo', 'pid=,pcpu=,pmem=,rss=,etime=,args='],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []
    processes: list[dict] = []
    for line in completed.stdout.splitlines():
        parsed = parse_ps_line(line)
        if parsed is None:
            continue
        if re.search(r'(?:^|\s)dsh\s+web(?:\s|$)', parsed['cmd']):
            processes.append(parsed)
    return processes


def process_info(port: int) -> dict:
    pid = find_listener_pid(port)
    if pid is not None:
        info = ps_info_for_pid(pid)
        if info.get('ok'):
            info['source'] = 'port'
        return info
    # Some dsh launchers make the listening socket unreadable through
    # /proc/<pid>/fd (non-dumpable), so ss and the /proc fallback cannot map
    # the port back to a pid. If exactly one `dsh web` process exists, show
    # that process and mark it as a command-line match rather than failing the
    # whole card.
    fallback = dsh_web_processes()
    if len(fallback) == 1:
        info = {'ok': True, **fallback[0], 'source': 'cmdline'}
        info['note'] = f'按 dsh web 命令行匹配（无法关联到端口 {port}）'
        return info
    if len(fallback) > 1:
        return {
            'ok': False,
            'error': f'检测到 {len(fallback)} 个 dsh web 进程，但无法关联到端口 {port}',
            'candidates': [{'pid': p['pid'], 'cmd': p['cmd']} for p in fallback],
        }
    return {'ok': False, 'error': f'没有找到监听 127.0.0.1:{port} 的进程'}


def read_log_lines_from_files(proxy_port: int) -> list[str]:
    if not LOGS_DIR.is_dir():
        return []
    lines: list[str] = []
    for log_file in sorted(LOGS_DIR.glob(f'access-{proxy_port}*.json')):
        try:
            with open(log_file, 'rb') as f:
                f.seek(0, 2)
                size = f.tell()
                start = max(0, size - LOG_TAIL_BYTES)
                f.seek(start)
                lines.extend(f.read().decode('utf-8', 'replace').splitlines())
        except OSError:
            continue
    return lines


def read_log_lines_via_docker(proxy_port: int) -> list[str]:
    """Fallback for a root-run Caddy whose log files are unreadable on the host."""
    if shutil.which('docker') is None:
        return []
    pattern = f'/data/logs/access-{proxy_port}*.json'
    try:
        completed = subprocess.run(
            ['docker', 'exec', CADDY_CONTAINER, 'sh', '-c', f'tail -c {LOG_TAIL_BYTES} {pattern}'],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0:
        return []
    return completed.stdout.splitlines()


def summarize_log_lines(lines: list[str]) -> dict:
    now = time.time()
    total = 0
    last_60s = 0
    statuses: Counter[str] = Counter()
    for raw in lines:
        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            continue
        total += 1
        try:
            if now - float(entry.get('ts', 0)) <= 60:
                last_60s += 1
        except (TypeError, ValueError):
            pass
        status = str(entry.get('status', '?'))
        statuses[status] += 1
    return {
        'total_tail': total,
        'last_60s': last_60s,
        'statuses': dict(statuses.most_common(8)),
    }


def traffic_info(proxy_port: int) -> dict:
    lines = read_log_lines_from_files(proxy_port)
    source = 'file'
    if not lines:
        lines = read_log_lines_via_docker(proxy_port)
        source = 'docker-exec'
    if not lines:
        return {'ok': False, 'error': '访问日志为空（还没有请求，或当前 Caddy 容器以 root 运行导致日志不可读）'}
    return {'ok': True, 'source': source, **summarize_log_lines(lines)}


def instance_monitor(instance: dict) -> dict:
    port = instance['port']
    proxy_port = instance.get('proxy_port', port)
    return {
        'web': probe_dsh(port),
        'sessions': count_sessions(instance.get('home', '~/.dsh')),
        'process': process_info(port),
        'traffic': traffic_info(proxy_port),
    }


# ---------------------------------------------------------------- API

def build_state() -> dict:
    instances, warnings = resolve_instances()
    state = read_state()
    result_instances = []
    online = 0
    for instance in instances:
        manifest, _path, manifest_error = read_profile_manifest(instance)
        monitor = instance_monitor(instance)
        if monitor['web'].get('ok'):
            online += 1
        result_instances.append({
            'name': instance.get('name', f"dsh-{instance['port']}"),
            'port': instance['port'],
            'proxy_port': instance.get('proxy_port', instance['port']),
            'profile': instance.get('profile', 'web'),
            'home': instance.get('home', '~/.dsh'),
            'manifest_error': manifest_error,
            'plugins': plugin_items(instance, manifest, state),
            'safe_mode': safe_mode_active(instance, manifest, state),
            'monitor': monitor,
        })
    return {
        'ok': True,
        'now': time.time(),
        'warnings': warnings,
        'online': online,
        'total': len(result_instances),
        'instances': result_instances,
    }


def handle_api_post(path: str, body: bytes) -> dict:
    try:
        payload = json.loads(body.decode('utf-8')) if body else {}
    except json.JSONDecodeError as error:
        return {'ok': False, 'error': f'invalid JSON: {error}'}
    instances, _ = resolve_instances()
    if path == '/api/plugin':
        port = payload.get('port')
        package = payload.get('package')
        enabled = payload.get('enabled')
        if not isinstance(port, int) or not isinstance(package, str) or not package:
            return {'ok': False, 'error': 'body 需要 {port: int, package: str, enabled: bool}'}
        instance = next((i for i in instances if i['port'] == port), None)
        if instance is None:
            return {'ok': False, 'error': f'没有端口 {port} 对应的实例'}
        return set_plugin_enabled(instance, package, bool(enabled))
    if path == '/api/safe-mode':
        port = payload.get('port')
        enabled = payload.get('enabled')
        if not isinstance(port, int) or not isinstance(enabled, bool):
            return {'ok': False, 'error': 'body 需要 {port: int, enabled: bool}'}
        instance = next((i for i in instances if i['port'] == port), None)
        if instance is None:
            return {'ok': False, 'error': f'没有端口 {port} 对应的实例'}
        return set_safe_mode(instance, enabled)
    return {'ok': False, 'error': f'unknown endpoint {path}'}


# ---------------------------------------------------------------- HTTP server

PAGE = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>dsh manage</title>
<style>
:root {
  color-scheme: light dark;
  --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Helvetica Neue', Helvetica, Arial, sans-serif;
  --mono: 'SF Mono', 'JetBrains Mono', 'Fira Code', Consolas, 'Liberation Mono', Menlo, Courier, 'PingFang SC', 'Microsoft YaHei';
  --bg: #f5f6f8;
  --panel: #ffffff;
  --panel-2: #fafbfc;
  --text: #1a1a1a;
  --text-2: #55575c;
  --text-3: #8a8d93;
  --border: #e4e7ec;
  --accent: #4176e6;
  --accent-strong: #2f5fc9;
  --green: #22c55e;
  --red: #ef4444;
  --amber: #f59e0b;
  --radius: 12px;
  --shadow: 0 1px 2px rgba(15,17,21,.05), 0 4px 16px rgba(15,17,21,.06);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #141417;
    --panel: #1c1c20;
    --panel-2: #222227;
    --text: #f0f1f3;
    --text-2: #b9bcc4;
    --text-3: #858991;
    --border: #2c2c32;
    --accent: #679afe;
    --accent-strong: #86b4fe;
    --green: #34d06f;
    --red: #f26666;
    --amber: #f7ad31;
    --shadow: 0 1px 2px rgba(0,0,0,.4), 0 4px 18px rgba(0,0,0,.5);
  }
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: var(--font);
  background: var(--bg);
  color: var(--text);
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 1080px; margin: 0 auto; padding: 24px 16px 48px; }
header.top {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 8px 0 20px;
}
header.top h1 { font-size: 20px; margin: 0; letter-spacing: .3px; }
header.top .sub { color: var(--text-3); font-size: 12px; }
.badge {
  display: inline-flex; align-items: center; gap: 6px;
  border: 1px solid var(--border); border-radius: 999px; padding: 4px 10px;
  font-size: 12px; color: var(--text-2); background: var(--panel);
}
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-3); display: inline-block; }
.dot.ok { background: var(--green); }
.dot.bad { background: var(--red); }
.banner {
  border: 1px solid var(--amber); color: var(--amber); background: color-mix(in srgb, var(--amber) 10%, var(--panel));
  border-radius: 10px; padding: 10px 12px; margin-bottom: 16px; font-size: 13px;
}
.card {
  background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius);
  box-shadow: var(--shadow); padding: 16px; margin-bottom: 16px;
}
.card h2 { margin: 0 0 2px; font-size: 16px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.card h2 .port { font-family: var(--mono); color: var(--accent); }
.card .meta { color: var(--text-3); font-size: 12px; margin-bottom: 12px; font-family: var(--mono); }
.grid { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); margin-bottom: 14px; }
.metric {
  background: var(--panel-2); border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px;
  min-height: 76px; display: flex; flex-direction: column; gap: 2px;
}
.metric .label { color: var(--text-3); font-size: 12px; }
.metric .value { font-size: 18px; font-weight: 600; }
.metric .value small { font-size: 12px; font-weight: 400; color: var(--text-3); }
.metric .err { color: var(--red); font-size: 12px; }
.metric .sub { color: var(--text-3); font-size: 11px; font-family: var(--mono); word-break: break-all; }
.actions { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin-bottom: 14px; }
button {
  font-family: var(--font); font-size: 13px; border-radius: 8px; border: 1px solid var(--border);
  background: var(--panel-2); color: var(--text); padding: 7px 12px; cursor: pointer;
  transition: background .15s ease, border-color .15s ease, color .15s ease;
}
button:hover { border-color: var(--accent); color: var(--accent); }
button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
button.primary:hover { background: var(--accent-strong); color: #fff; }
button.danger { color: var(--red); }
button.danger:hover { border-color: var(--red); color: var(--red); }
button:disabled { opacity: .5; cursor: not-allowed; }
.plugins { border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
.plugin-row {
  display: flex; align-items: center; gap: 10px; padding: 10px 12px;
  border-bottom: 1px solid var(--border); flex-wrap: wrap;
}
.plugin-row:last-child { border-bottom: 0; }
.plugin-row .pname { font-family: var(--mono); font-size: 13px; flex: 1 1 220px; word-break: break-all; }
.plugin-row .pspec { color: var(--text-3); font-size: 11px; font-family: var(--mono); word-break: break-all; }
.plugin-row .state { font-size: 12px; }
.plugin-row .state.on { color: var(--green); }
.plugin-row .state.off { color: var(--text-3); }
.section-title { font-size: 13px; color: var(--text-2); margin: 0 0 8px; display: flex; align-items: center; gap: 8px; }
.switch {
  position: relative; width: 40px; height: 22px; flex: 0 0 auto; appearance: none;
  background: var(--border); border-radius: 999px; border: 0; cursor: pointer; transition: background .15s ease; padding: 0;
}
.switch::after {
  content: ''; position: absolute; top: 2px; left: 2px; width: 18px; height: 18px; border-radius: 50%;
  background: #fff; transition: transform .15s ease; box-shadow: 0 1px 2px rgba(0,0,0,.3);
}
.switch[aria-checked="true"] { background: var(--accent); }
.switch[aria-checked="true"]::after { transform: translateX(18px); }
.enter-link { text-decoration: none; }
.note { color: var(--text-3); font-size: 12px; margin-top: 8px; }
@media (max-width: 560px) {
  .wrap { padding: 16px 10px 40px; }
  .grid { grid-template-columns: 1fr 1fr; }
  .card { padding: 12px; }
  .plugin-row { align-items: flex-start; }
}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div>
      <h1>dsh manage</h1>
      <div class="sub">DeepSeek Harness 实例监控与外部插件控制</div>
    </div>
    <div style="display:flex;gap:8px;align-items:center">
      <span class="badge"><span class="dot" id="summary-dot"></span><span id="summary-text">加载中…</span></span>
      <button id="refresh" class="primary">刷新</button>
    </div>
  </header>
  <div id="banners"></div>
  <div id="root"></div>
  <div class="note" id="footer">每 10 秒自动刷新 · 配置修改写入 profile，重启对应 dsh 后生效。</div>
</div>
<script>
const root = document.getElementById('root');
const bannersEl = document.getElementById('banners');
const summaryDot = document.getElementById('summary-dot');
const summaryText = document.getElementById('summary-text');
let state = null;

function entryUrl(inst) {
  const loc = location;
  const scheme = loc.protocol; // http: or https:
  const hostname = loc.hostname || '127.0.0.1';
  const proxyPort = String(inst.proxy_port);
  if (proxyPort === (loc.port || (scheme === 'https:' ? '443' : '80'))) {
    return scheme + '//' + hostname + (loc.port ? ':' + loc.port : '') + '/';
  }
  return scheme + '//' + hostname + ':' + proxyPort + '/';
}

function esc(text) {
  return String(text ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function metricCard(label, value, sub, ok, error) {
  if (ok) {
    return '<div class="metric"><div class="label">' + esc(label) + '</div><div class="value">' + value + '</div>'
      + (sub ? '<div class="sub">' + esc(sub) + '</div>' : '') + '</div>';
  }
  return '<div class="metric"><div class="label">' + esc(label) + '</div><div class="value">—</div>'
    + '<div class="err">' + esc(error || '不可用') + '</div></div>';
}

function pluginRow(inst, p) {
  const stateClass = p.enabled ? 'on' : 'off';
  const stateText = p.enabled ? '已启用' : (p.installed ? (p.declares_bundle ? '已停用' : '非 bundle') : '未安装');
  const badge = '<span class="state ' + stateClass + '">' + stateText + '</span>';
  let action;
  if (p.enabled) {
    action = '<button class="danger" data-action="plugin" data-port="' + inst.port + '" data-package="' + esc(p.name) + '" data-enabled="false">停用</button>';
  } else if (!p.installed) {
    action = '<button disabled title="未安装：先通过 dsh plugin add 安装">启用</button>';
  } else if (!p.declares_bundle) {
    action = '<button disabled title="该包未声明 dsh.bundle，不能作为 bundle 加载">启用</button>';
  } else {
    action = '<button data-action="plugin" data-port="' + inst.port + '" data-package="' + esc(p.name) + '" data-enabled="true">启用</button>';
  }
  return '<div class="plugin-row"><div class="pname">' + esc(p.name) + '</div>'
    + '<div class="pspec">' + esc(p.spec || '') + '</div>' + badge + action + '</div>';
}

function instanceCard(inst) {
  const m = inst.monitor || {};
  const web = m.web || {};
  const webOk = web.ok && web.marker !== false;
  const sessions = m.sessions || {};
  const proc = m.process || {};
  const traffic = m.traffic || {};
  const safe = inst.safe_mode;
  const plugins = (inst.plugins || []);
  const manifestError = inst.manifest_error
    ? '<div class="banner">profile 读取异常：' + esc(inst.manifest_error) + '</div>' : '';
  const safeToggle = '<button class="switch" role="switch" aria-checked="' + (safe ? 'true' : 'false') + '" '
    + 'data-action="safe" data-port="' + inst.port + '" data-enabled="' + (!safe) + '" title="安全模式：只加载内置 bundle"></button>';
  const pluginHtml = plugins.length
    ? plugins.map(p => pluginRow(inst, p)).join('')
    : '<div class="plugin-row"><div class="pname">没有检测到外部插件</div></div>';

  return '<section class="card">'
    + '<h2><span class="dot ' + (webOk ? 'ok' : 'bad') + '"></span>' + esc(inst.name) + ' <span class="port">127.0.0.1:' + inst.port + '</span></h2>'
    + '<div class="meta">profile: ' + esc(inst.profile) + ' · DSH_HOME: ' + esc(inst.home) + ' · proxy: ' + inst.proxy_port + '</div>'
    + manifestError
    + '<div class="grid">'
    + metricCard('dsh web', webOk ? '在线' : '不可达',
        webOk ? (web.latency_ms ?? '') + ' ms · HTTP ' + (web.status ?? '?') + ' · 127.0.0.1:' + inst.port : null,
        webOk, web.error)
    + metricCard('sessions', sessions.ok ? String(sessions.count) : '—',
        sessions.ok ? (sessions.note || '') : null, sessions.ok, sessions.error)
    + metricCard('进程', proc.ok ? (proc.rss_mb + ' MB · ' + proc.cpu_percent + '% CPU') : '—',
        proc.ok ? 'PID ' + proc.pid + ' · ' + proc.elapsed + (proc.note ? ' · ' + proc.note : '') : null,
        proc.ok, proc.error)
    + metricCard('流量(60s)', traffic.ok ? String(traffic.last_60s) + ' 请求' : '—',
        traffic.ok ? '尾部共 ' + traffic.total_tail + ' 条 · ' + JSON.stringify(traffic.statuses || {}) : null,
        traffic.ok, traffic.error)
    + '</div>'
    + '<div class="actions">'
    + '<a class="enter-link" href="' + entryUrl(inst) + '"><button class="primary">进入 dsh</button></a>'
    + '<span class="section-title">安全模式（禁用全部外部插件）</span>' + safeToggle
    + '</div>'
    + '<div class="section-title">外部插件加载</div>'
    + '<div class="plugins">' + pluginHtml + '</div>'
    + '<div class="note">' + (safe ? '安全模式已开启：重启 dsh 后仅加载内置 bundle。' : '') + '插件开关写入 dsh.profile.bundles，重启 dsh 后生效。</div>'
    + '</section>';
}

function render() {
  if (!state) return;
  const ok = state.ok;
  if (!ok) {
    root.innerHTML = '<div class="banner">' + esc(state.error || '状态读取失败') + '</div>';
    return;
  }
  summaryDot.className = 'dot ' + (state.online > 0 ? 'ok' : 'bad');
  summaryText.textContent = state.online + ' / ' + state.total + ' 在线';
  bannersEl.innerHTML = (state.warnings || []).map(w => '<div class="banner">' + esc(w) + '</div>').join('');
  root.innerHTML = (state.instances || []).map(instanceCard).join('')
    || '<div class="card">没有可管理的 dsh 实例：运行 deploy.py up 生成代理，或编辑 instances.yml。</div>';
  document.getElementById('footer').textContent = '更新于 ' + new Date((state.now || 0) * 1000).toLocaleTimeString() + ' · 每 10 秒自动刷新 · 配置修改写入 profile，重启对应 dsh 后生效。';
}

async function loadState() {
  try {
    const resp = await fetch('api/state', { cache: 'no-store' });
    state = await resp.json();
    render();
  } catch (err) {
    bannersEl.innerHTML = '<div class="banner">无法连接 manage 后端：' + esc(err) + '</div>';
  }
}

async function postJSON(url, body) {
  const resp = await fetch(url, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body), cache: 'no-store',
  });
  return resp.json();
}

document.addEventListener('click', async (event) => {
  const button = event.target.closest('button');
  if (!button) return;
  const action = button.dataset.action;
  if (action === 'plugin') {
    button.disabled = true;
    try {
      const result = await postJSON('api/plugin', {
        port: Number(button.dataset.port),
        package: button.dataset.package,
        enabled: button.dataset.enabled === 'true',
      });
      if (result.ok) bannersEl.innerHTML = '<div class="banner" style="border-color:var(--green);color:var(--green)">' + esc(result.note || '已更新') + '</div>';
      else bannersEl.innerHTML = '<div class="banner">' + esc(result.error || '操作失败') + '</div>';
      await loadState();
    } finally {
      button.disabled = false;
    }
  } else if (action === 'safe') {
    button.disabled = true;
    try {
      const result = await postJSON('api/safe-mode', {
        port: Number(button.dataset.port),
        enabled: button.dataset.enabled === 'true',
      });
      if (result.ok) bannersEl.innerHTML = '<div class="banner" style="border-color:var(--green);color:var(--green)">' + esc(result.note || '已更新') + '</div>';
      else bannersEl.innerHTML = '<div class="banner">' + esc(result.error || '操作失败') + '</div>';
      await loadState();
    } finally {
      button.disabled = false;
    }
  } else if (button.id === 'refresh') {
    await loadState();
  }
});

loadState();
setInterval(loadState, 10000);
</script>
</body>
</html>
'''


class Handler(BaseHTTPRequestHandler):
    server_version = 'dsh-manage/1'

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == '/api/state':
            try:
                self._send_json(build_state())
            except Exception as error:  # never take the whole manage UI down
                self._send_json({'ok': False, 'error': f'state build failed: {type(error).__name__}: {error}'})
            return
        if self.path in ('/', '/index.html'):
            body = PAGE.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
            return
        self._send_json({'ok': False, 'error': f'unknown path {self.path}'}, 404)

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get('Content-Length', '0'))
            body = self.rfile.read(length) if length > 0 else b''
            self._send_json(handle_api_post(self.path, body))
        except Exception as error:
            self._send_json({'ok': False, 'error': f'{type(error).__name__}: {error}'})

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write(f'{self.address_string()} {fmt % args}\n')


def main() -> None:
    global CADDY_CONTAINER
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=int(os.environ.get('DSH_MANAGE_PORT', str(DEFAULT_PORT))))
    parser.add_argument('--container', default=os.environ.get('DSH_MANAGE_CADDY_CONTAINER', DEFAULT_CADDY_CONTAINER))
    args = parser.parse_args()
    CADDY_CONTAINER = args.container
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    except OSError as error:
        print(f'dsh-manage: failed to bind 127.0.0.1:{args.port}: {error}', file=sys.stderr)
        sys.exit(1)
    server.daemon_threads = True
    print(f'dsh-manage listening on http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
