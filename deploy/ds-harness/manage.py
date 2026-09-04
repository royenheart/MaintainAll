#!/usr/bin/env python3
"""Standalone management backend for deploy/ds-harness.

Serves the /manage single-page UI and a JSON API for monitoring dsh web
instances and controlling their profile's external plugin loading. The
backend is intentionally independent from dsh: every metric is collected
best-effort, a failed metric only degrades its own card, and the control
paths edit dsh profile files on disk (`package.json` bundle lists and the
live `cordis.patch.yml` patch layer) without booting dsh — so a dsh instance
that cannot start because of a broken plugin can still be recovered from
/manage.

Usage:
    python3 manage.py --port 9097
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    import fcntl
except ImportError:  # non-POSIX fallback: atomic replace still prevents torn files
    fcntl = None

BASE_DIR = Path(__file__).resolve().parent
CADDYFILE_PATH = BASE_DIR / 'Caddyfile'
INSTANCES_YML_PATH = BASE_DIR / 'instances.yml'
DATA_DIR = BASE_DIR / 'data'
LOGS_DIR = DATA_DIR / 'logs'
STATE_PATH = DATA_DIR / 'manage-state.json'
PID_FILE_PATH = DATA_DIR / 'manage.pid'

DEFAULT_PORT = 9097
DEFAULT_DSH_PORT = 3080
DEFAULT_CADDY_CONTAINER = 'dsh-proxy'
CADDY_CONTAINER = DEFAULT_CADDY_CONTAINER
DSH_MARKER = '__DSH_BOOT__'
DSH_AUTH_CHALLENGE = 'dsh web authentication required'
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


def parse_caddyfile_injected_ports() -> set[int]:
    """Return dsh ports whose generated reverse_proxy block injects a session cookie.

    deploy.py writes `header_up Cookie ...` inside the final dsh upstream block
    when plan-B auth injection is active; the manage UI uses this to stop
    telling proxy users to paste a token.
    """
    injected: set[int] = set()
    if not CADDYFILE_PATH.is_file():
        return injected
    content = CADDYFILE_PATH.read_text(encoding='utf-8')
    current_dsh: int | None = None
    in_manage_block = False
    manage_depth = 0
    in_upstream_block = False
    upstream_depth = 0
    for line in content.splitlines():
        stripped = line.strip()
        site = re.match(r'^https?://(?:\[?[0-9a-fA-F.:]+\]?|):(\d+)\s*\{', stripped)
        if site is not None:
            current_dsh = None
            in_manage_block = False
            manage_depth = 0
            in_upstream_block = False
            upstream_depth = 0
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
        if in_upstream_block:
            if current_dsh is not None and stripped.startswith('header_up Cookie '):
                injected.add(current_dsh)
            upstream_depth += stripped.count('{') - stripped.count('}')
            if upstream_depth <= 0:
                in_upstream_block = False
                current_dsh = None
            continue
        match = re.match(r'^reverse_proxy\s+127\.0\.0\.1:(\d+)\s*\{?', stripped)
        if match is not None and stripped.endswith('{'):
            current_dsh = int(match.group(1))
            in_upstream_block = True
            upstream_depth = stripped.count('{') - stripped.count('}')
            if upstream_depth <= 0:
                in_upstream_block = False
                current_dsh = None
    return injected


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


def package_dir_candidates(instance: dict, package_name: str):
    """Yield node_modules dirs dsh would probe for `package_name`.

    dsh resolves profile bundles through Node's normal `node_modules` lookup
    from the profile directory, so the shared `$DSH_HOME/profiles/node_modules`
    is a valid location too — not just `<profile>/node_modules`.
    """
    profile = profile_dir(instance.get('home', '~/.dsh'), instance.get('profile', 'web'))
    seen: set[Path] = set()
    for base in [profile, *profile.parents]:
        candidate = base / 'node_modules' / package_name
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_dir():
            yield candidate


def package_dir(instance: dict, package_name: str) -> Path | None:
    """Resolve an installed package directory the same way dsh's resolution would."""
    for candidate in package_dir_candidates(instance, package_name):
        if (candidate / 'package.json').is_file():
            return candidate
    return None


def profile_lock_path(instance: dict) -> Path:
    """One lock file per instance profile, so multi-home/multi-profile never share a lock."""
    return profile_dir(instance.get('home', '~/.dsh'), instance.get('profile', 'web')) / '.manage-write.lock'


@contextmanager
def profile_write_lock(instance: dict):
    """Serialize profile-file read-modify-write transactions between processes.

    Advisory `flock` + atomic `os.replace` writes: every manage.py instance
    that follows this protocol waits, while dsh's own live patch watcher only
    reads the files and always sees a complete old or new version.
    """
    path = profile_lock_path(instance)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def profile_write_locked(fn):
    """Decorate a control function so its read-modify-write runs under the profile lock."""
    @functools.wraps(fn)
    def wrapper(instance: dict, *args, **kwargs):
        with profile_write_lock(instance):
            return fn(instance, *args, **kwargs)
    return wrapper


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
    base = package_dir(instance, package_name)
    if base is None:
        return False
    try:
        data = read_json(base / 'package.json')
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(((data.get('dsh') or {}).get('bundle') or {}).get('patch'), str)


def profile_patch_path(instance: dict) -> Path:
    return profile_dir(instance.get('home', '~/.dsh'), instance.get('profile', 'web')) / 'cordis.patch.yml'


def home_patch_path(instance: dict) -> Path:
    """The home-level patch layer, applied over every profile."""
    return expand(instance.get('home', '~/.dsh')) / 'cordis.patch.yml'


def load_dsh_yaml_text(text: str):
    """Parse dsh YAML (the loader dialect allows `!!js` expressions)."""
    import yaml

    class Loader(yaml.SafeLoader):
        pass

    def construct_js(loader: yaml.SafeLoader, tag_suffix: str, node: yaml.Node):
        if isinstance(node, yaml.ScalarNode):
            return {'__jsExpr': loader.construct_scalar(node)}
        if isinstance(node, yaml.SequenceNode):
            return loader.construct_sequence(node, deep=True)
        if isinstance(node, yaml.MappingNode):
            return loader.construct_mapping(node, deep=True)
        return None

    Loader.add_multi_constructor('tag:yaml.org,2002:js', construct_js)
    return yaml.load(text, Loader=Loader)


def read_patch_file(path: Path) -> tuple[list | None, str | None]:
    """Read one `cordis.patch.yml` file; missing means an empty layer."""
    if not path.is_file():
        return [], None
    try:
        data = load_dsh_yaml_text(path.read_text(encoding='utf-8')) or []
    except Exception as error:
        return None, f'{path.name} 读取失败: {error}'
    if not isinstance(data, list):
        return None, f'{path.name} 必须是顶层数组'
    return data, None


def read_profile_patches(instance: dict) -> tuple[list | None, Path, str | None]:
    """Return (patches, patch_path, error) for the profile's live user patch layer."""
    path = profile_patch_path(instance)
    patches, error = read_patch_file(path)
    return patches, path, error


def read_home_patches(instance: dict) -> tuple[list | None, Path, str | None]:
    """Return (patches, patch_path, error) for the home-level live patch layer."""
    path = home_patch_path(instance)
    patches, error = read_patch_file(path)
    return patches, path, error


def _contains_js_expr(value) -> bool:
    if isinstance(value, dict):
        if '__jsExpr' in value:
            return True
        return any(_contains_js_expr(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_js_expr(v) for v in value)
    return False


def write_profile_patches(path: Path, patches: list) -> str | None:
    if _contains_js_expr(patches):
        return 'cordis.patch.yml 含 !!js 表达式，manage 暂不能安全重写该文件；请手动编辑或移除表达式后再用 manage 开关插件'
    import yaml
    try:
        text = yaml.safe_dump(patches, allow_unicode=True, sort_keys=False, default_flow_style=False)
    except Exception as error:
        return f'cordis.patch.yml 序列化失败: {error}'
    tmp = path.with_name(path.name + '.tmp')
    try:
        tmp.write_text(text, encoding='utf-8')
        os.replace(tmp, path)
    except OSError as error:
        return f'cordis.patch.yml 写入失败: {error}'
    return None


def bundle_row_ids(instance: dict, package_name: str) -> tuple[list[str], str | None]:
    """Return the loader row ids a bundle patch inserts for package_name.

    The profile user patch layer targets rows by the `id` declared in the
    bundle's own `cordis.patch.yml` insert row (for these plugins that is the
    package short name: `maintainall`, `skills-manager`, ...). Reading the
    installed bundle patch keeps manage.py independent from dsh internals.
    """
    base = package_dir(instance, package_name)
    if base is None:
        return [], f'{package_name} 未安装（在 profile 或共享 profiles/node_modules 下都找不到）'
    try:
        data = read_json(base / 'package.json')
    except (OSError, json.JSONDecodeError) as error:
        return [], f'{package_name} 的 package.json 读取失败: {error}'
    patch_rel = ((data.get('dsh') or {}).get('bundle') or {}).get('patch')
    if not isinstance(patch_rel, str):
        return [], f'{package_name} 未声明 dsh.bundle.patch'
    try:
        import yaml
        patch_data = yaml.safe_load((base / patch_rel).read_text(encoding='utf-8')) or []
    except Exception as error:
        return [], f'{package_name} 的 bundle patch 读取失败: {error}'
    if not isinstance(patch_data, list):
        return [], f'{package_name} 的 bundle patch 必须是顶层数组'
    ids: list[str] = []
    for patch in patch_data:
        if not isinstance(patch, dict):
            continue
        inserts = patch.get('insert')
        if not isinstance(inserts, list):
            continue
        for row in inserts:
            if not isinstance(row, dict):
                continue
            if row.get('name') != package_name:
                continue
            row_id = row.get('id')
            if isinstance(row_id, str) and row_id:
                ids.append(row_id)
    if not ids:
        return [], f'{package_name} 的 bundle patch 中没有 name 等于包名且带 id 的 insert 行'
    return ids, None


def package_name_of(spec: str) -> str | None:
    """Return the package name for a module spec (bare package or package/subpath)."""
    parts = spec.split('/')
    if spec.startswith('@'):
        return '/'.join(parts[:2]) if len(parts) >= 2 else None
    return parts[0] if parts and parts[0] else None


def package_spec(instance: dict, package_name: str) -> str:
    """Best-effort install spec for a resolved package directory."""
    base = package_dir(instance, package_name)
    if base is None:
        return ''
    real = os.path.realpath(base)
    return f'link:{real}' if real != str(base) else str(base)


def is_external_preset_row(name: str) -> bool:
    """True for preset rows that reference a third-party package (not dsh builtins)."""
    if name.startswith('cordis:') or name.startswith('./') or name.startswith('../'):
        return False
    if name.startswith('@deepseek-ai/'):
        return False
    return True


def walk_preset_rows(entries: list) -> list[dict]:
    """Flatten a preset entry list, descending into group config lists."""
    rows: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        rows.append(entry)
        config = entry.get('config')
        if entry.get('group') and isinstance(config, list):
            rows.extend(walk_preset_rows(config))
    return rows


def patch_insert_items(instance: dict, patches: list, scope: str) -> list[dict]:
    """List third-party rows a patch layer inserts directly.

    `cordis.patch.yml` may also `insert` new rows (not just patch bundle rows).
    These are shown read-only: they belong to the patch file itself, not to
    `dsh.profile.bundles`, so manage does not toggle them here.
    """
    items: list[dict] = []
    for patch in patches:
        if not isinstance(patch, dict):
            continue
        inserts = patch.get('insert')
        if not isinstance(inserts, list):
            continue
        for row in inserts:
            if not isinstance(row, dict):
                continue
            name = row.get('name')
            if not isinstance(name, str) or not name:
                continue
            if not is_external_preset_row(name):
                continue
            package_name = package_name_of(name)
            if package_name is None:
                continue
            items.append({
                'name': name,
                'enabled': row.get('disabled') is not True,
                'installed': package_dir(instance, package_name) is not None,
                'spec': package_spec(instance, package_name),
                'declares_bundle': package_declares_bundle(instance, package_name),
                'scope': scope,
                'toggleable': False,
            })
    return items


def preset_plugin_items(instance: dict) -> list[dict]:
    """Read user agent presets (`$DSH_HOME/.agent-presets/*/agent.cordis.yml`).

    Emits one synthetic row for the preset itself (so users see the preset
    exists, even when every row inside is local/builtin), then one read-only
    row per third-party package row inside the composition.
    """
    import yaml
    root = expand(instance.get('home', '~/.dsh')) / '.agent-presets'
    if not root.is_dir():
        return []
    items: list[dict] = []
    for preset_dir in sorted(root.iterdir()):
        if not preset_dir.is_dir():
            continue
        active_file = preset_dir / 'agent.cordis.yml'
        disabled_file = preset_dir / 'agent.cordis.yml.disabled'
        if active_file.is_file():
            preset_file = active_file
            preset_enabled = True
        elif disabled_file.is_file():
            preset_file = disabled_file
            preset_enabled = False
        else:
            continue
        try:
            data = load_dsh_yaml_text(preset_file.read_text(encoding='utf-8')) or []
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        # Preset itself as a roster row. dsh has no per-preset enable switch,
        # so manage models one by renaming agent.cordis.yml <-> .disabled
        # (a directory without agent.cordis.yml is not discovered by dsh).
        display = preset_dir.name
        metadata_file = preset_dir / 'preset.yml'
        try:
            meta = load_dsh_yaml_text(metadata_file.read_text(encoding='utf-8')) if metadata_file.is_file() else {}
        except Exception:
            meta = {}
        if isinstance(meta, dict) and isinstance(meta.get('name'), str) and meta['name']:
            display = meta['name']
        items.append({
            'name': preset_dir.name,
            'display': display,
            'enabled': preset_enabled,
            'installed': True,
            'spec': str(preset_file),
            'declares_bundle': False,
            'scope': f'preset:{preset_dir.name}',
            'toggleable': True,
            'kind': 'preset',
        })
        for row in walk_preset_rows(data):
            name = row.get('name')
            if not isinstance(name, str) or not name:
                continue
            if not is_external_preset_row(name):
                continue
            package_name = package_name_of(name)
            if package_name is None:
                continue
            items.append({
                'name': name,
                'enabled': preset_enabled and row.get('disabled') is not True,
                'installed': package_dir(instance, package_name) is not None,
                'spec': package_spec(instance, package_name),
                'declares_bundle': package_declares_bundle(instance, package_name),
                'scope': f'preset:{preset_dir.name}',
                'toggleable': False,
                'kind': 'plugin',
            })
    return items


@profile_write_locked
def set_preset_enabled(instance: dict, preset_id: str, enabled: bool) -> dict:
    """Enable/disable a USER agent preset by renaming its composition file.

    dsh discovers a preset only when its directory holds `agent.cordis.yml`;
    renaming it to `agent.cordis.yml.disabled` unpublishes the whole preset
    without deleting it, and renaming back re-publishes it. Built-in shipped
    presets live outside `$DSH_HOME/.agent-presets` and are never touched.
    """
    if Path(preset_id).name != preset_id or not preset_id:
        return {'ok': False, 'error': 'preset id 非法'}
    root = expand(instance.get('home', '~/.dsh')) / '.agent-presets'
    preset_dir = root / preset_id
    if not preset_dir.is_dir():
        return {'ok': False, 'error': f'没有找到 preset 目录 {preset_dir}'}
    active_file = preset_dir / 'agent.cordis.yml'
    disabled_file = preset_dir / 'agent.cordis.yml.disabled'
    if enabled:
        if active_file.is_file():
            return {'ok': True, 'note': f'preset {preset_id} 已启用'}
        if not disabled_file.is_file():
            return {'ok': False, 'error': f'找不到 {disabled_file.name}，无法启用'}
        try:
            os.rename(disabled_file, active_file)
        except OSError as error:
            return {'ok': False, 'error': f'重命名失败: {error}'}
        note = f'preset {preset_id} 已启用（agent.cordis.yml 已恢复，dsh 下次读取即可见）'
    else:
        if disabled_file.is_file():
            return {'ok': True, 'note': f'preset {preset_id} 已禁用'}
        if not active_file.is_file():
            return {'ok': False, 'error': f'找不到 {active_file.name}，无法禁用'}
        try:
            os.rename(active_file, disabled_file)
        except OSError as error:
            return {'ok': False, 'error': f'重命名失败: {error}'}
        note = f'preset {preset_id} 已禁用（agent.cordis.yml 已改名，dsh 下次读取即不再发现）'
    return {'ok': True, 'note': note}


def all_plugin_items(instance: dict, manifest: dict | None, state: dict) -> list[dict]:
    """Every plugin row manage can see, across all file-backed scopes.

    Scopes:
      profile       dsh.profile.bundles + dependencies + profile patch toggles
      patch:profile rows inserted directly by the profile cordis.patch.yml
      patch:home    rows inserted directly by $DSH_HOME/cordis.patch.yml
      preset:<name> rows composed by a user agent preset
    """
    profile_patches, _pp, _pe = read_profile_patches(instance)
    home_patches, _hp, _he = read_home_patches(instance)
    items = [
        *plugin_items(instance, manifest, state),
        *patch_insert_items(instance, profile_patches or [], 'patch:profile'),
        *patch_insert_items(instance, home_patches or [], 'patch:home'),
        *preset_plugin_items(instance),
    ]
    seen: set[tuple[str, str]] = set()
    merged: list[dict] = []
    for item in items:
        key = (item['scope'], item['name'])
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def patch_disables_row(patch: dict, row_ids: list[str]) -> bool:
    return patch.get('disabled') is True and patch.get('id') in row_ids


def plugin_items(instance: dict, manifest: dict | None, state: dict) -> list[dict]:
    bundles = current_bundles(manifest)
    in_box = set(inbox_bundles(instance.get('profile', 'web')))
    deps = (manifest or {}).get('dependencies') or {}
    saved = state_for(instance['port'], state).get('saved_bundles') or []
    patches, _patch_path, _patch_error = read_profile_patches(instance)
    home_patches, _home_path, _home_error = read_home_patches(instance)
    patches = (patches or []) + (home_patches or [])
    names: set[str] = set()
    for name in [*bundles, *saved, *deps.keys()]:
        if name and name not in in_box:
            names.add(name)
    items: list[dict] = []
    for name in sorted(names):
        row_ids, _row_error = bundle_row_ids(instance, name)
        disabled = any(patch_disables_row(patch, row_ids) for patch in patches if isinstance(patch, dict))
        items.append({
            'name': name,
            'enabled': name in bundles and not disabled,
            'installed': name in deps,
            'spec': deps.get(name, ''),
            'declares_bundle': package_declares_bundle(instance, name),
            'scope': 'profile',
            'toggleable': True,
        })
    return items


def safe_mode_active(instance: dict, manifest: dict | None, state: dict) -> bool:
    st = state_for(instance['port'], state)
    if not st.get('saved_bundles'):
        return False
    bundles = current_bundles(manifest)
    in_box = inbox_bundles(instance.get('profile', 'web'))
    return bundles == in_box


def leave_safe_mode_for_toggle(instance: dict, manifest: dict, state: dict, st: dict, bundles: list, patches: list) -> bool:
    """Restore the safe-mode snapshot before a per-plugin toggle.

    Returns True when the snapshot was restored and must be persisted.
    Per-plugin choices are never silently absorbed by the safe-mode snapshot:
    first restore both the startup bundle list and the live patch layer, then
    apply the user's explicit choice on top.
    """
    if not (safe_mode_active(instance, manifest, state) and st.get('saved_bundles')):
        return False
    bundles[:] = list(st['saved_bundles'])
    saved_patches = st.get('saved_patches')
    patches[:] = list(saved_patches) if isinstance(saved_patches, list) else []
    st['saved_bundles'] = []
    st['saved_patches'] = []
    return True


@profile_write_locked
def set_plugin_enabled(instance: dict, package: str, enabled: bool) -> dict:
    manifest, manifest_path, error = read_profile_manifest(instance)
    if error is not None:
        return {'ok': False, 'error': error}
    if manifest is None:
        return {'ok': False, 'error': 'profile manifest missing'}
    patches, patch_path, patch_error = read_profile_patches(instance)
    if patch_error is not None:
        return {'ok': False, 'error': patch_error}
    home_patches, _home_path, home_error = read_home_patches(instance)
    if home_error is not None:
        return {'ok': False, 'error': home_error}
    home_patches = home_patches or []
    state = read_state()
    st = state_for(instance['port'], state)
    bundles = current_bundles(manifest)
    in_box = inbox_bundles(instance.get('profile', 'web'))
    row_ids, row_error = bundle_row_ids(instance, package)
    if row_error is not None:
        return {'ok': False, 'error': row_error}

    # A per-plugin toggle always leaves safe mode: restore the saved snapshot
    # first so the user's explicit choice is not silently absorbed.
    leave_safe_mode_for_toggle(instance, manifest, state, st, bundles, patches)
    # Whether the running dsh already has this bundle entry. A package absent
    # from dsh.profile.bundles cannot be hot-enabled: the live patch layer can
    # only toggle rows that were composed at boot.
    was_in_bundles = package in bundles
    home_disabled = any(patch_disables_row(p, row_ids) for p in home_patches if isinstance(p, dict))

    if enabled:
        if home_disabled:
            return {'ok': False, 'error': f'{package} 被 $DSH_HOME/cordis.patch.yml 停用（id: {row_ids[0]}），先编辑 home patch 移除该条再启用'}
        deps = (manifest or {}).get('dependencies') or {}
        if package not in deps:
            return {'ok': False, 'error': f'{package} 不在 profile dependencies 中，先通过 `dsh plugin add` 安装'}
        if package not in bundles:
            if not package_declares_bundle(instance, package):
                return {'ok': False, 'error': f'{package} 未声明 dsh.bundle，不能作为 bundle 启用'}
            # Insert after in-box bundles, preserving a stable layer order.
            insert_at = len([b for b in bundles if b in in_box])
            bundles.insert(insert_at, package)
        # Remove the user patch entries that disable this row set.
        patches = [p for p in patches if not (isinstance(p, dict) and patch_disables_row(p, row_ids))]
        if was_in_bundles:
            note = '已移除 cordis.patch.yml 停用补丁；host 侧热生效（无需重启 dsh），浏览器刷新后客户端侧生效'
        else:
            note = '已将插件加入 dsh.profile.bundles 并移除停用补丁；重启 dsh 后生效（当前 dsh 进程没有该 bundle 条目）'
    else:
        if home_disabled:
            return {'ok': True, 'note': f'{package} 已被 $DSH_HOME/cordis.patch.yml 停用，无需写入 profile patch'}
        if package not in bundles:
            return {'ok': True, 'note': '插件已停用（不在 dsh.profile.bundles 中）'}
        for row_id in row_ids:
            if not any(isinstance(p, dict) and p.get('id') == row_id and p.get('disabled') is True for p in patches):
                patches.append({'id': row_id, 'disabled': True})
        note = '已写入 cordis.patch.yml 停用补丁；host 侧热生效（无需重启 dsh），浏览器刷新后客户端侧生效'

    dsh = manifest.setdefault('dsh', {})
    prof = dsh.setdefault('profile', {})
    prof['bundles'] = bundles
    write_state(state)
    error = write_profile_manifest(manifest_path, manifest)
    if error is not None:
        return {'ok': False, 'error': error}
    error = write_profile_patches(patch_path, patches)
    if error is not None:
        return {'ok': False, 'error': error}
    state = read_state()
    return {
        'ok': True,
        'bundles': bundles,
        'plugins': plugin_items(instance, manifest, state),
        'safe_mode': safe_mode_active(instance, manifest, state),
        'note': note,
    }


@profile_write_locked
def set_safe_mode(instance: dict, enabled: bool) -> dict:
    manifest, manifest_path, error = read_profile_manifest(instance)
    if error is not None:
        return {'ok': False, 'error': error}
    if manifest is None:
        return {'ok': False, 'error': 'profile manifest missing'}
    patches, patch_path, patch_error = read_profile_patches(instance)
    if patch_error is not None:
        return {'ok': False, 'error': patch_error}
    state = read_state()
    st = state_for(instance['port'], state)
    bundles = current_bundles(manifest)
    in_box = inbox_bundles(instance.get('profile', 'web'))

    if enabled:
        if safe_mode_active(instance, manifest, state):
            return {'ok': True, 'note': '安全模式已启用'}
        # Snapshot both layers: bundles keep the startup composition (editing
        # bundles is the only recovery when a bundle layer itself is broken),
        # patches make the same change live for a running dsh web.
        st['saved_bundles'] = list(bundles)
        st['saved_patches'] = [dict(p) if isinstance(p, dict) else p for p in patches]
        prof_bundles = list(in_box)
        for package in list(st['saved_bundles']):
            if package in in_box:
                continue
            row_ids, row_error = bundle_row_ids(instance, package)
            if row_error is not None:
                continue
            for row_id in row_ids:
                if not any(isinstance(p, dict) and p.get('id') == row_id and p.get('disabled') is True for p in patches):
                    patches.append({'id': row_id, 'disabled': True})
        note = '安全模式已启用：已收窄 dsh.profile.bundles 并写入 cordis.patch.yml 停用补丁；host 侧热生效（无需重启 dsh），重启 dsh 也保持安全模式'
    else:
        saved = st.get('saved_bundles')
        if not saved:
            return {'ok': False, 'error': '没有已保存的 bundles 记录，无法退出安全模式'}
        prof_bundles = list(saved)
        saved_patches = st.get('saved_patches')
        patches = list(saved_patches) if isinstance(saved_patches, list) else []
        st['saved_bundles'] = []
        st['saved_patches'] = []
        note = '安全模式已关闭：已恢复 dsh.profile.bundles 与 cordis.patch.yml'

    dsh = manifest.setdefault('dsh', {})
    prof = dsh.setdefault('profile', {})
    prof['bundles'] = prof_bundles
    write_state(state)
    error = write_profile_manifest(manifest_path, manifest)
    if error is not None:
        return {'ok': False, 'error': error}
    error = write_profile_patches(patch_path, patches)
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
    except urllib.error.HTTPError as error:
        # Newer dsh web guards `/` with the process launch token; a 401 with
        # the auth-challenge body still proves the instance is up and serving.
        if error.code == 401:
            body = error.read(131072).decode('utf-8', 'replace')
            if DSH_AUTH_CHALLENGE in body:
                return {
                    'ok': True,
                    'latency_ms': round((time.time() - started) * 1000, 1),
                    'marker': False,
                    'auth_required': True,
                    'status': error.code,
                }
        return {'ok': False, 'error': f'{type(error).__name__}: {error}'}
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


def proc_cpu_ticks(pid: int) -> int | None:
    """Sum of utime+stime from /proc/<pid>/stat, in clock ticks."""
    try:
        stat = Path(f'/proc/{pid}/stat').read_text(encoding='utf-8')
    except OSError:
        return None
    # The comm field may contain spaces; everything after the last ')' is the
    # numeric field list starting at field 3 (state).
    rest = stat[stat.rfind(')') + 2:].split()
    if len(rest) < 13:
        return None
    try:
        # rest[11] = utime (field 14), rest[12] = stime (field 15)
        return int(rest[11]) + int(rest[12])
    except (ValueError, IndexError):
        return None


def instant_cpu_percent(pid: int, interval: float = 0.6) -> float | None:
    """Short-interval CPU% like top/ps would show right now.

    `ps %cpu` is a lifetime average, which reads 0.0 for a long-running but
    mostly idle dsh process. Two /proc/<pid>/stat samples over a short
    interval give an instantaneous value instead.
    """
    try:
        hz = os.sysconf('SC_CLK_TCK')
    except (ValueError, OSError):
        hz = 100
    first = proc_cpu_ticks(pid)
    if first is None:
        return None
    time.sleep(interval)
    second = proc_cpu_ticks(pid)
    if second is None:
        return None
    if hz <= 0:
        return None
    return round((second - first) / (interval * hz) * 100, 1)


def with_instant_cpu(info: dict) -> dict:
    """Attach an instantaneous CPU reading when the process is readable."""
    if not info.get('ok'):
        return info
    try:
        cpu = instant_cpu_percent(int(info['pid']))
    except (ValueError, TypeError):
        return info
    if cpu is not None:
        info['cpu_percent'] = cpu
        info['cpu_source'] = 'instant'
    return info


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
        return with_instant_cpu(info)
    # Some dsh launchers make the listening socket unreadable through
    # /proc/<pid>/fd (non-dumpable), so ss and the /proc fallback cannot map
    # the port back to a pid. If exactly one `dsh web` process exists, show
    # that process and mark it as a command-line match rather than failing the
    # whole card.
    fallback = dsh_web_processes()
    if len(fallback) == 1:
        info = {'ok': True, **fallback[0], 'source': 'cmdline'}
        info['note'] = f'端口→PID 关联不可用，按 dsh web 命令行匹配'
        return with_instant_cpu(info)
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
    injected_ports = parse_caddyfile_injected_ports()
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
            'auth_injected': instance['port'] in injected_ports,
            'manifest_error': manifest_error,
            'plugins': all_plugin_items(instance, manifest, state),
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
    if path == '/api/preset':
        port = payload.get('port')
        preset = payload.get('preset')
        enabled = payload.get('enabled')
        if not isinstance(port, int) or not isinstance(preset, str) or not preset:
            return {'ok': False, 'error': 'body 需要 {port: int, preset: str, enabled: bool}'}
        instance = next((i for i in instances if i['port'] == port), None)
        if instance is None:
            return {'ok': False, 'error': f'没有端口 {port} 对应的实例'}
        return set_preset_enabled(instance, preset, bool(enabled))
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
  <div class="note" id="footer">每 10 秒自动刷新 · 插件开关写入 cordis.patch.yml，host 侧热生效；浏览器刷新后客户端侧生效。</div>
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
  let stateClass, stateText;
  if (p.kind === 'preset') {
    stateClass = p.enabled ? 'on' : 'off';
    stateText = p.enabled ? '可用' : '已禁用';
  } else {
    stateClass = p.enabled ? 'on' : 'off';
    stateText = p.enabled ? '已启用' : (p.installed ? (p.declares_bundle ? '已停用' : '非 bundle') : '未安装');
  }
  const badge = '<span class="state ' + stateClass + '">' + stateText + '</span>';
  const scopeBadge = p.scope && p.scope !== 'profile'
    ? '<span class="state off" title="该行来自 agent preset，不在 manage 的 profile bundle 控制范围">' + esc(p.scope) + '</span>'
    : '';
  const title = p.kind === 'preset'
    ? esc(p.display || p.name)
    : esc(p.name);
  let action;
  if (p.kind === 'preset') {
    if (p.enabled) {
      action = '<button class="danger" data-action="preset" data-port="' + inst.port + '" data-preset="' + esc(p.name) + '" data-enabled="false">停用</button>';
    } else {
      action = '<button data-action="preset" data-port="' + inst.port + '" data-preset="' + esc(p.name) + '" data-enabled="true">启用</button>';
    }
  } else if (p.toggleable === false) {
    action = '<button disabled title="agent preset 内部行：manage 不在此控制，请编辑对应 agent.cordis.yml 的 disabled 字段">只读</button>';
  } else if (p.enabled) {
    action = '<button class="danger" data-action="plugin" data-port="' + inst.port + '" data-package="' + esc(p.name) + '" data-enabled="false">停用</button>';
  } else if (!p.installed) {
    action = '<button disabled title="未安装：先通过 dsh plugin add 安装">启用</button>';
  } else if (!p.declares_bundle) {
    action = '<button disabled title="该包未声明 dsh.bundle，不能作为 bundle 加载">启用</button>';
  } else {
    action = '<button data-action="plugin" data-port="' + inst.port + '" data-package="' + esc(p.name) + '" data-enabled="true">启用</button>';
  }
  return '<div class="plugin-row"><div class="pname" title="' + title + '">' + esc(p.name) + '</div>'
    + '<div class="pspec">' + esc(p.spec || '') + '</div>' + scopeBadge + badge + action + '</div>';
}

function instanceCard(inst) {
  const m = inst.monitor || {};
  const web = m.web || {};
  const injected = inst.auth_injected === true;
  const webOk = web.ok && (web.marker !== false || web.auth_required === true);
  const webValue = webOk
    ? (injected ? '在线 · 代理免token' : (web.auth_required ? '在线 · 需 token' : '在线'))
    : '不可达';
  const webSub = webOk
    ? (web.latency_ms ?? '') + ' ms · HTTP ' + (web.status ?? '?')
      + (web.auth_required ? ' · 401 认证挑战' : '') + ' · 127.0.0.1:' + inst.port
    : null;
  const sessions = m.sessions || {};
  const proc = m.process || {};
  const traffic = m.traffic || {};
  const safe = inst.safe_mode;
  const plugins = (inst.plugins || []);
  const manifestError = inst.manifest_error
    ? '<div class="banner">profile 读取异常：' + esc(inst.manifest_error) + '</div>' : '';
  const safeButton = '<button class="' + (safe ? 'danger' : 'primary') + '" '
    + 'data-action="safe" data-port="' + inst.port + '" data-enabled="' + (!safe) + '" '
    + 'title="安全模式：收窄 bundles 并写入停用补丁，host 侧热生效">'
    + (safe ? '退出安全模式' : '进入安全模式') + '</button>';
  const loginHint = injected
    ? '<div class="note">Caddy 已为该实例注入 dsh web 会话 Cookie，通过代理访问无需 token；'
      + '直连 127.0.0.1:' + inst.port + ' 仍需 dsh 启动行里的 token。</div>'
    : (web.auth_required
      ? '<div class="note">该实例已启用 web 认证：请把 dsh web 启动行里的 token 填到 '
        + '<code>' + esc(entryUrl(inst)) + '?token=&lt;TOKEN&gt;</code> 完成首次登录；'
        + '之后浏览器持有 Cookie，直接进入即可。</div>'
      : '');
  const pluginHtml = plugins.length
    ? plugins.map(p => pluginRow(inst, p)).join('')
    : '<div class="plugin-row"><div class="pname">没有检测到外部插件</div></div>';

  return '<section class="card">'
    + '<h2><span class="dot ' + (webOk ? 'ok' : 'bad') + '"></span>' + esc(inst.name) + ' <span class="port">127.0.0.1:' + inst.port + '</span></h2>'
    + '<div class="meta">profile: ' + esc(inst.profile) + ' · DSH_HOME: ' + esc(inst.home) + ' · proxy: ' + inst.proxy_port + '</div>'
    + manifestError
    + '<div class="grid">'
    + metricCard('dsh web', webValue, webSub, webOk, web.error)
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
    + safeButton
    + '</div>'
    + '<div class="section-title">外部插件加载</div>'
    + '<div class="plugins">' + pluginHtml + '</div>'
    + loginHint
    + '<div class="note">' + (safe ? '安全模式已开启：仅加载内置 bundle，host 侧热生效。' : '') + '插件开关写入 cordis.patch.yml，host 侧热生效；浏览器刷新后客户端侧生效。preset 本身可停用/启用（重命名 agent.cordis.yml），preset 内的第三方行只读。</div>'
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
  document.getElementById('footer').textContent = '更新于 ' + new Date((state.now || 0) * 1000).toLocaleTimeString() + ' · 每 10 秒自动刷新 · 插件开关写入 cordis.patch.yml，host 侧热生效；浏览器刷新后客户端侧生效。';
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
  } else if (action === 'preset') {
    button.disabled = true;
    try {
      const result = await postJSON('api/preset', {
        port: Number(button.dataset.port),
        preset: button.dataset.preset,
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
    parser.add_argument('--pid-file', default=os.environ.get('DSH_MANAGE_PID_FILE', str(PID_FILE_PATH)))
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
    try:
        Path(args.pid_file).parent.mkdir(parents=True, exist_ok=True)
        Path(args.pid_file).write_text(str(os.getpid()), encoding='utf-8')
    except OSError as error:
        print(f'dsh-manage: warning: failed to write pid file {args.pid_file}: {error}', file=sys.stderr)
    print(f'dsh-manage listening on http://127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
