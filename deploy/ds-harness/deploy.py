#!/usr/bin/env python3
"""Deploy the ds-harness reverse proxy (Caddy, Docker) and manage dsh plugins.

One invocation does exactly one thing — either a deployment action or a
plugin-management action. Deployment and plugin management never mix.

Deployment (Caddy reverse proxy)
--------------------------------
Takes one or more port mappings and turns them into a Caddyfile that forwards
public proxy ports to loopback dsh web instances.

Port mappings
  PORT          proxy listens on PORT and forwards to 127.0.0.1:PORT
  PROXY:DSH     proxy listens on PROXY and forwards to 127.0.0.1:DSH

By default the generated Caddyfile rewrites Host and Origin to the loopback
upstream authority. dsh's /api browser-trust fence rejects non-loopback Hosts,
and privileged methods (settings, credentials, path openers) are loopback-only
even with --trusted-host. Rewriting makes the dsh web API work through the
proxy.

Newer dsh web also mints a browser session from the startup token printed by
`dsh web` (the `?token=...` URL). The proxy forwards that exchange unchanged,
so the first visit through the proxy must be `<proxy-url>/?token=<token>`;
afterwards dsh's HttpOnly cookie authenticates the browser. The proxy remains
the trust boundary for everyone who holds the token, so bind it to a trusted
network only (see --listen and the README).

One dsh-client-side fence remains even after Host/Origin rewriting: the
settings domain disables itself in any browser whose page URL is not loopback
(the models settings page then reports "settings are unavailable in this
browser"). For settings through a remote browser, keep the proxy on loopback
(`--listen 127.0.0.1`) and access it through an SSH local forward; see the
README.

The default listen host is the machine's first non-loopback IPv4 (the
default-route source address). That lets `up` with no arguments share dsh's
port: caddy binds only <LAN-IP>:3080, which does not conflict with dsh
listening on 127.0.0.1:3080. A wildcard `--listen 0.0.0.0` cannot share the
port with a loopback listener and is rejected when that conflict exists.

Plugin management (plugins.yml)
-------------------------------
Reads `plugins.yml` (a list of npm package specs or git/github URLs) and
installs or updates each plugin into a dsh profile through
`dsh plugin --profile <name>`. Every entry is first installed remotely
(`dsh plugin add <spec>`). Only when remote install fails does the script
fall back to pulling the plugin into a temporary directory (git clone for a
repo spec, `npm pack` for an npm spec), installing it via `file:`, and then
deleting the temporary directory. `update` defaults to every plugin in the
list; pass plugin names to update a subset.

Usage:
  python3 deploy.py up [PORTS...] [--auto] [--listen HOST ...] [--manage-port PORT] [--auth-cookie-days DAYS] [--dry-run]
  python3 deploy.py down
  python3 deploy.py status
  python3 deploy.py scan
  python3 deploy.py reload [PORTS...] [--auto] [--listen HOST ...] [--manage-port PORT] [--auth-cookie-days DAYS] [--dry-run]
  python3 deploy.py install [--profile web] [--home ~/.dsh] [--dry-run]
  python3 deploy.py update [PLUGIN...] [--profile web] [--home ~/.dsh] [--dry-run]

Examples:
  python3 deploy.py up                      # bind LAN-IP:3080 -> 127.0.0.1:3080
  python3 deploy.py up 8080:3080            # bind LAN-IP:8080 -> 127.0.0.1:3080
  python3 deploy.py up 3080 3081            # two dsh instances on their own ports
  python3 deploy.py up 8080:3080 8081:3081  # two dsh instances, distinct proxy ports
  python3 deploy.py up --tls                # HTTPS on LAN-IP:3080 (Caddy internal CA), http://LAN-IP/ redirects
  python3 deploy.py up 8443:3080 --tls      # HTTPS on LAN-IP:8443 -> 127.0.0.1:3080, http://LAN-IP/ redirects
  python3 deploy.py up --auto               # auto-discover running dsh web services
  python3 deploy.py up 3080 --auto          # explicit ports plus discovered ones
  python3 deploy.py up --listen 192.168.1.10 --listen 10.0.0.5   # bind two IPs
  python3 deploy.py up --auth-cookie-days 3650  # inject a 10-year dsh web session cookie (see README)
  python3 deploy.py install                 # install every plugin listed in plugins.yml
  python3 deploy.py update                  # update every plugin listed in plugins.yml
  python3 deploy.py update @royenheart/dsh-plugin-foo   # update one listed plugin
  https://<LAN-IP>:<proxy-port>/manage/     # dsh manage UI, served by the deployment
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_DSH_PORT = 3080
DEFAULT_CONTAINER = 'dsh-proxy'
DEFAULT_IMAGE = 'caddy:2'
WILDCARD_LISTEN_HOST = '0.0.0.0'
DSH_MARKER = '__DSH_BOOT__'
DSH_AUTH_CHALLENGE = 'dsh web authentication required'
DEFAULT_AUTH_COOKIE_DAYS = 30
AUTH_RECORD_KEY = 'client-connection/browser-session'
AUTH_SECRET_BYTES = 32
SCAN_TIMEOUT_SECONDS = 0.8
SCAN_WORKERS = 8
SETTINGS_PROBE_TIMEOUT_SECONDS = 3.0
SETTINGS_PROBE_USER_AGENT = 'dsh-proxy-settings-probe/1'
SETTINGS_BUNDLE_SUFFIX = 'dsh-client-ui-settings'
SETTINGS_GATE_PATTERN = re.compile(
    r'isLoopback\s*\?\s*["\']host["\']\s*:\s*["\']memory["\']',
)

WILDCARD_HOSTS = {'*', '0.0.0.0', '[::]'}

CADDYFILE_PATH = Path(__file__).resolve().parent / 'Caddyfile'
PLUGINS_YML_PATH = Path(__file__).resolve().parent / 'plugins.yml'
INSTANCES_YML_PATH = Path(__file__).resolve().parent / 'instances.yml'
MANAGE_SCRIPT_PATH = Path(__file__).resolve().parent / 'manage.py'
MANAGE_DATA_DIR = Path(__file__).resolve().parent / 'data'
MANAGE_LOG_PATH = MANAGE_DATA_DIR / 'manage.log'
MANAGE_PID_PATH = MANAGE_DATA_DIR / 'manage.pid'
DEFAULT_MANAGE_PORT = 9097

PORT_SPEC_RE = re.compile(r'^(\d{1,5})(?::(\d{1,5}))?$')
GIT_SHORTHAND_RE = re.compile(r'^(?:github|gitlab|bitbucket):')
GIT_SHORTHAND_HOSTS = {'github': 'github.com', 'gitlab': 'gitlab.com', 'bitbucket': 'bitbucket.org'}


def parse_port_spec(spec: str) -> tuple[int, int]:
    """Parse PORT or PROXY:DSH into (proxy_port, dsh_port)."""
    match = PORT_SPEC_RE.match(spec.strip())
    if match is None:
        raise ValueError(f'invalid port spec {spec!r}: expected PORT or PROXY:DSH (e.g. 3080 or 8080:3080)')
    if match.group(2) is not None:
        proxy_port = int(match.group(1))
        dsh_port = int(match.group(2))
    else:
        proxy_port = dsh_port = int(match.group(1))
    for label, value in (('proxy port', proxy_port), ('dsh port', dsh_port)):
        if not 1 <= value <= 65535:
            raise ValueError(f'invalid {label} {value} in {spec!r}: must be 1-65535')
    return proxy_port, dsh_port


def print_command(command: list[str]) -> None:
    print(f'$ {" ".join(command)}')


def run(command: list[str], *, dry_run: bool) -> int:
    print_command(command)
    if dry_run:
        return 0
    return subprocess.run(command).returncode


# ---------------------------------------------------------------- plugin management

def plugin_profile(args: argparse.Namespace) -> str:
    return args.profile or os.environ.get('DSH_PROFILE', 'web')


def plugin_home(args: argparse.Namespace) -> str:
    return args.home or os.environ.get('DSH_HOME', '~/.dsh')


def plugin_dsh(args: argparse.Namespace) -> str:
    return args.dsh or 'dsh'


def profile_dir(args: argparse.Namespace) -> Path:
    return Path(plugin_home(args)).expanduser() / 'profiles' / plugin_profile(args)


def load_plugin_specs() -> list[str]:
    """Read `plugins.yml` and return the non-empty string entries under `plugins:`."""
    if not PLUGINS_YML_PATH.is_file():
        raise SystemExit(f'{PLUGINS_YML_PATH} not found - create it with a `plugins:` list first')
    try:
        import yaml
    except ImportError as error:
        raise SystemExit('plugin management needs PyYAML - install it with `pip install pyyaml`') from error
    try:
        data = yaml.safe_load(PLUGINS_YML_PATH.read_text(encoding='utf-8'))
    except Exception as error:
        raise SystemExit(f'failed to parse {PLUGINS_YML_PATH}: {error}') from error
    if data is None:
        return []
    if isinstance(data, dict):
        specs = data.get('plugins') or []
    elif isinstance(data, list):
        specs = data
    else:
        raise SystemExit(f'{PLUGINS_YML_PATH}: expected a top-level `plugins:` list of strings')
    if not isinstance(specs, list):
        raise SystemExit(f'{PLUGINS_YML_PATH}: expected a top-level `plugins:` list of strings')
    result: list[str] = []
    for item in specs:
        if not isinstance(item, str) or not item.strip():
            raise SystemExit(f'{PLUGINS_YML_PATH}: every plugin entry must be a non-empty string, got {item!r}')
        result.append(item.strip())
    return result


def is_git_spec(spec: str) -> bool:
    """Whether a remote spec points at a git repository rather than an npm artifact."""
    if spec.startswith(('git+', 'git@')) or spec.endswith('.git'):
        return True
    if GIT_SHORTHAND_RE.match(spec):
        return True
    if '://' in spec:
        # An https tarball URL is an npm artifact, not a git repo.
        if re.search(r'\.(?:tgz|tar\.gz)(?:[?#].*)?$', spec):
            return False
        # Git repos over https are overwhelmingly github/gitlab/bitbucket
        # URLs; anything else (npm registry, package pages, tarballs) is an
        # npm artifact and must not be sent to `git clone` in the fallback.
        return bool(re.search(r'(?:^|[/.@])(?:github|gitlab|bitbucket)\.(?:com|org|cn|io)', spec))
    return False


def bare_npm_name(spec: str) -> str | None:
    """Return the package name for a bare npm spec (`pkg` or `@scope/pkg@^1`), else None."""
    if spec.startswith(('file:', 'link:', 'npm:', 'git+', 'git@')) or '://' in spec:
        return None
    if GIT_SHORTHAND_RE.match(spec):
        return None
    if spec.startswith('@'):
        rest = spec[1:]
        if '/' not in rest:
            return None
        scope, tail = rest.split('/', 1)
        name = tail.split('@', 1)[0]
        if not scope or not name:
            return None
        return f'@{scope}/{name}'
    name = spec.split('@', 1)[0]
    return name or None


def to_clone_url(spec: str) -> str:
    """Normalize a git spec into a URL `git clone` accepts."""
    match = GIT_SHORTHAND_RE.match(spec)
    if match is not None:
        host, repo = spec.split(':', 1)
        return f'https://{GIT_SHORTHAND_HOSTS.get(host, host)}/{repo}.git'
    if spec.startswith('git+'):
        return spec[4:]
    return spec


def run_dsh_plugin(args: argparse.Namespace, pnpm_args: list[str]) -> int:
    """Run `dsh plugin --profile <profile> <pnpm_args...>` and return its exit code."""
    command = [plugin_dsh(args), 'plugin', '--profile', plugin_profile(args), *pnpm_args]
    print_command(command)
    if args.dry_run:
        return 0
    env = os.environ.copy()
    env['DSH_HOME'] = str(Path(plugin_home(args)).expanduser())
    try:
        return subprocess.run(command, env=env).returncode
    except FileNotFoundError as error:
        raise SystemExit(f'{plugin_dsh(args)!r} not found - install dsh or pass --dsh <path>') from error


def profile_has_dependency(args: argparse.Namespace, package_name: str) -> bool:
    """Whether the profile manifest already lists `package_name` as a dependency."""
    manifest = profile_dir(args) / 'package.json'
    if not manifest.is_file():
        return False
    try:
        data = json.loads(manifest.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return False
    return package_name in data.get('dependencies', {})


def download_tarball(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers={'User-Agent': 'dsh-deploy-plugin/1'})
    with urllib.request.urlopen(request, timeout=60) as response, dest.open('wb') as out:
        shutil.copyfileobj(response, out)


def prepare_local_spec(spec: str, tmpdir: Path, args: argparse.Namespace) -> str | None:
    """Pull `spec` into `tmpdir` and return a `file:` spec for it, or None on failure."""
    if is_git_spec(spec):
        repo_dir = tmpdir / 'repo'
        clone_url = to_clone_url(spec)
        print_command(['git', 'clone', '--depth', '1', clone_url, str(repo_dir)])
        if not args.dry_run:
            try:
                completed = subprocess.run(['git', 'clone', '--depth', '1', clone_url, str(repo_dir)])
            except FileNotFoundError:
                print('fallback failed: git not found on PATH')
                return None
            if completed.returncode != 0:
                print(f'fallback failed: git clone exited {completed.returncode}')
                return None
        return 'file:' + str(repo_dir)

    if '://' in spec:
        tarball = tmpdir / 'plugin.tgz'
        if not args.dry_run:
            print_command(['download', spec, '->', str(tarball)])
            try:
                download_tarball(spec, tarball)
            except Exception as error:
                print(f'fallback failed: could not download {spec}: {error}')
                return None
        return 'file:' + str(tarball)

    # Bare npm spec: download the publish tarball through npm pack.
    print_command(['npm', 'pack', spec, '--pack-destination', str(tmpdir)])
    if args.dry_run:
        return 'file:' + str(tmpdir / 'plugin.tgz')
    try:
        completed = subprocess.run(
            ['npm', 'pack', spec, '--pack-destination', str(tmpdir)],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        print('fallback failed: npm not found on PATH')
        return None
    if completed.returncode != 0:
        print(f'fallback failed: npm pack exited {completed.returncode}')
        if completed.stderr.strip():
            print(completed.stderr.strip())
        return None
    tarballs = sorted(tmpdir.glob('*.tgz'))
    if not tarballs:
        print('fallback failed: npm pack produced no tarball')
        return None
    return 'file:' + str(tarballs[0])


def install_local_fallback(spec: str, args: argparse.Namespace) -> bool:
    """Pull `spec` into a temporary dir, install from there, then delete it."""
    tmpdir = Path(tempfile.mkdtemp(prefix='dsh-plugin-'))
    try:
        local_spec = prepare_local_spec(spec, tmpdir, args)
        if local_spec is None:
            return False
        return run_dsh_plugin(args, ['add', local_spec]) == 0
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def install_one(spec: str, args: argparse.Namespace) -> bool:
    """Install one plugin spec: remote add first, then the local-tmp fallback."""
    if run_dsh_plugin(args, ['add', spec]) == 0:
        return True
    print(f'remote add failed for {spec!r}; falling back to local tmp install')
    return install_local_fallback(spec, args)


def update_one(spec: str, args: argparse.Namespace) -> bool:
    """Update one plugin spec.

    Bare npm specs update through `pnpm update --latest` by package name.
    Git specs and tarball URLs have no range semantics, so they re-resolve by
    running the same remote-add flow as `install`.
    """
    if is_git_spec(spec) or '://' in spec:
        return install_one(spec, args)
    name = bare_npm_name(spec)
    if name is None:
        return install_one(spec, args)
    if not profile_has_dependency(args, name):
        print(f'{name} is not installed in profile {plugin_profile(args)!r}; installing instead')
        return install_one(spec, args)
    if run_dsh_plugin(args, ['update', '--latest', name]) == 0:
        return True
    print(f'update failed for {name!r}; retrying with add {spec!r}')
    return install_one(spec, args)


def select_plugin_specs(specs: list[str], selectors: list[str]) -> list[str]:
    """Filter `specs` by selector; each selector may be a spec or a bare npm name."""
    if not selectors:
        return specs
    selected: list[str] = []
    for spec in specs:
        candidates = {spec}
        name = bare_npm_name(spec)
        if name is not None:
            candidates.add(name)
        if any(selector in candidates for selector in selectors):
            selected.append(spec)
    unmatched = [
        selector for selector in selectors
        if not any(selector == spec or selector == bare_npm_name(spec) for spec in specs)
    ]
    if unmatched:
        available = ', '.join(specs) or '(empty)'
        raise SystemExit(
            f'no plugin in {PLUGINS_YML_PATH.name} matches: {", ".join(unmatched)}; '
            f'available: {available}',
        )
    return selected


def cmd_install(args: argparse.Namespace) -> int:
    if args.ports:
        raise SystemExit('install takes no plugin names - it installs every plugin listed in plugins.yml; use `update <name...>` to target a subset')
    specs = load_plugin_specs()
    if not specs:
        print(f'{PLUGINS_YML_PATH.name} is empty - nothing to install')
        return 0
    print(f'installing {len(specs)} plugin(s) from {PLUGINS_YML_PATH.name} into profile {plugin_profile(args)!r}')
    failed: list[str] = []
    for spec in specs:
        print(f'\n==> plugin: {spec}')
        if install_one(spec, args):
            print(f'ok: {spec}')
        else:
            print(f'FAILED: {spec}')
            failed.append(spec)
    if failed:
        raise SystemExit(f'{len(failed)} plugin(s) failed: {", ".join(failed)}')
    print(f'\ninstalled {len(specs)} plugin(s)')
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    specs = load_plugin_specs()
    if not specs:
        print(f'{PLUGINS_YML_PATH.name} is empty - nothing to update')
        return 0
    selected = select_plugin_specs(specs, args.ports)
    print(f'updating {len(selected)} plugin(s) from {PLUGINS_YML_PATH.name} into profile {plugin_profile(args)!r}')
    failed: list[str] = []
    for spec in selected:
        print(f'\n==> plugin: {spec}')
        if update_one(spec, args):
            print(f'ok: {spec}')
        else:
            print(f'FAILED: {spec}')
            failed.append(spec)
    if failed:
        raise SystemExit(f'{len(failed)} plugin(s) failed: {", ".join(failed)}')
    print(f'\nupdated {len(selected)} plugin(s)')
    return 0


def docker_available() -> bool:
    return shutil.which('docker') is not None


def container_state(name: str) -> str | None:
    completed = subprocess.run(
        ['docker', 'ps', '-a', '--filter', f'name=^{name}$', '--format', '{{.State}}'],
        capture_output=True,
        text=True,
    )
    lines = completed.stdout.strip().splitlines()
    return lines[0] if lines else None


def ss_available() -> bool:
    return shutil.which('ss') is not None


def listening_tcp_rows() -> list[str]:
    if not ss_available():
        raise SystemExit('`ss` is required for port checks and auto-scan; install iproute2')
    completed = subprocess.run(['ss', '-ltnH'], capture_output=True, text=True)
    if completed.returncode != 0:
        raise SystemExit(f'ss -ltnH failed: {completed.stderr.strip()}')
    return completed.stdout.splitlines()


def local_port_of(row: str) -> tuple[str, int] | None:
    """Return (host, port) for one `ss -ltnH` row's local address, when any."""
    parts = row.split()
    if len(parts) < 4:
        return None
    local = parts[3]
    # ss prints IPv6 as [::1]:3080; IPv4/wildcard as 127.0.0.1:3080, *:3080, 0.0.0.0:3080.
    match = re.match(r'^(?P<host>\[[0-9a-fA-F:.]+\]|[0-9a-fA-F.*:]+):(?P<port>\d+)$', local)
    if match is None:
        return None
    return match.group('host'), int(match.group('port'))


def bind_conflicts(listen_hosts: list[str], port: int) -> bool:
    """Whether caddy binding every `listen_hosts:port` would hit a listener.

    Binding 0.0.0.0:port conflicts with any listener on that port. Binding a
    specific IP only conflicts with wildcard listeners or the same IP — a dsh
    instance on 127.0.0.1:3080 does NOT block binding 192.168.x.x:3080.
    """
    if WILDCARD_LISTEN_HOST in listen_hosts:
        return any(found is not None and found[1] == port for found in map(local_port_of, listening_tcp_rows()))
    for row in listening_tcp_rows():
        found = local_port_of(row)
        if found is None or found[1] != port:
            continue
        row_host = found[0]
        if row_host in WILDCARD_HOSTS or row_host in listen_hosts:
            return True
    return False


def default_listen_host() -> str:
    """Best-effort LAN IP so `up` with no args can share dsh's port safely.

    A dsh instance listening on 127.0.0.1:3080 does not conflict with caddy
    binding 192.168.x.x:3080, but it DOES conflict with a wildcard
    0.0.0.0:3080 bind. Prefer the default-route source IPv4; fall back to the
    first global IPv4, then to the wildcard bind.
    """
    try:
        completed = subprocess.run(['ip', '-4', 'route', 'get', '8.8.8.8'], capture_output=True, text=True)
        match = re.search(r'\bsrc\s+(\d+\.\d+\.\d+\.\d+)', completed.stdout)
        if match is not None:
            return match.group(1)
    except (OSError, ValueError):
        pass
    try:
        completed = subprocess.run(['ip', '-4', '-o', 'addr', 'show', 'scope', 'global'], capture_output=True, text=True)
        for line in completed.stdout.splitlines():
            match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)', line)
            if match is not None and match.group(1) != '127.0.0.1':
                return match.group(1)
    except (OSError, ValueError):
        pass
    return WILDCARD_LISTEN_HOST


def scan_candidate_ports() -> list[int]:
    """Listening TCP ports on loopback/wildcard addresses, for dsh probing."""
    ports: set[int] = set()
    wildcard_hosts = {'*', '0.0.0.0', '[::]'}
    loopback_hosts = {'127.0.0.1', '[::1]'}
    for row in listening_tcp_rows():
        found = local_port_of(row)
        if found is None:
            continue
        host, port = found
        if host in wildcard_hosts or host in loopback_hosts:
            ports.add(port)
    return sorted(ports)


def probe_dsh_port(port: int) -> int | None:
    """Return the port when 127.0.0.1:port answers like a dsh web instance."""
    url = f'http://127.0.0.1:{port}/'
    request = urllib.request.Request(
        url,
        headers={'Host': f'127.0.0.1:{port}', 'User-Agent': 'dsh-proxy-scan/1'},
    )
    try:
        with urllib.request.urlopen(request, timeout=SCAN_TIMEOUT_SECONDS) as response:
            server = (response.headers.get('Server') or '').lower()
            if 'caddy' in server:
                return None
            body = response.read(131072).decode('utf-8', 'replace')
            return port if DSH_MARKER in body else None
    except urllib.error.HTTPError as error:
        # Newer dsh web guards `/` with the process launch token, so an
        # unauthenticated probe gets the 401 auth challenge instead of the
        # index document. The challenge body is still a reliable dsh marker.
        if error.code != 401:
            return None
        body = error.read(131072).decode('utf-8', 'replace')
        return port if DSH_AUTH_CHALLENGE in body else None
    except Exception:
        # The scan only needs to recognize dsh web services; every other local
        # listener (SSH, gRPC, plain TCP) legitimately fails an HTTP probe.
        return None


def read_loopback_http_text(dsh_port: int, path: str) -> str | None:
    """GET a text resource from 127.0.0.1:dsh_port and return it as UTF-8 text."""
    url = f'http://127.0.0.1:{dsh_port}{path}'
    request = urllib.request.Request(
        url,
        headers={'Host': f'127.0.0.1:{dsh_port}', 'User-Agent': SETTINGS_PROBE_USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=SETTINGS_PROBE_TIMEOUT_SECONDS) as response:
            return response.read().decode('utf-8', 'replace')
    except Exception:
        # The probe is best-effort: dsh may be down, or the path may 404 on an
        # older/newer dsh. Callers treat a failed read as "unknown".
        return None


def dsh_boot_entries(html: str) -> list[dict] | None:
    """Parse `window.__DSH_BOOT__` from a dsh web index document, when present."""
    match = re.search(r'window\.__DSH_BOOT__\s*=\s*(\{.*?\})\s*</script>', html, re.S)
    if match is None:
        return None
    try:
        data = json.loads(match.group(1))
        entries = data.get('entries')
        return entries if isinstance(entries, list) else None
    except (json.JSONDecodeError, TypeError):
        return None


def settings_bundle_path(entries: list[dict]) -> str | None:
    """Return the served URL path of the `dsh-client-ui-settings` client bundle."""
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_id = entry.get('id')
        entry_url = entry.get('url')
        if isinstance(entry_id, str) and isinstance(entry_url, str) and entry_id.endswith(SETTINGS_BUNDLE_SUFFIX):
            return entry_url if entry_url.startswith('/') else f'/{entry_url}'
    return None


def settings_gate_blocks_remote(dsh_port: int) -> bool | None:
    """Whether the served dsh client still disables settings for non-loopback pages.

    The current dsh client builds its settings mirror with
    `connection.isLoopback ? "host" : "memory"`, so any browser whose page URL
    is not loopback never reads or writes settings. Host/Origin rewriting by
    the proxy cannot change that, but a future dsh can. Returning `True` means
    "the gate is present, remote settings pages will be unavailable"; `False`
    means "the gate pattern is gone, assume dsh updated"; `None` means the dsh
    instance could not be probed.
    """
    html = read_loopback_http_text(dsh_port, '/')
    if html is None or DSH_MARKER not in html:
        return None
    entries = dsh_boot_entries(html)
    if entries is None:
        return None
    bundle_path = settings_bundle_path(entries)
    if bundle_path is None:
        return None
    bundle = read_loopback_http_text(dsh_port, bundle_path)
    if bundle is None:
        return None
    return SETTINGS_GATE_PATTERN.search(bundle) is not None


def probe_settings_availability(
    mappings: list[tuple[int, int]],
) -> tuple[list[int], list[int]]:
    """Return `(blocked_ports, unknown_ports)` for model settings through the proxy."""
    blocked: list[int] = []
    unknown: list[int] = []
    for dsh_port in sorted({dsh_port for _proxy_port, dsh_port in mappings}):
        result = settings_gate_blocks_remote(dsh_port)
        if result is True:
            blocked.append(dsh_port)
        elif result is None:
            unknown.append(dsh_port)
    return blocked, unknown


def scan_dsh_ports() -> list[int]:
    candidates = scan_candidate_ports()
    if not candidates:
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=SCAN_WORKERS) as executor:
        results = executor.map(probe_dsh_port, candidates)
    return sorted(port for port in results if port is not None)


def dedupe_mappings(mappings: list[tuple[int, int]]) -> list[tuple[int, int]]:
    deduped: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    proxy_owners: dict[int, int] = {}
    for proxy_port, dsh_port in mappings:
        if (proxy_port, dsh_port) in seen:
            continue
        seen.add((proxy_port, dsh_port))
        existing = proxy_owners.get(proxy_port)
        if existing is not None and existing != dsh_port:
            raise SystemExit(
                f'proxy port {proxy_port} is mapped to both dsh ports {existing} and {dsh_port}; '
                f'one proxy port can only forward to one dsh instance',
            )
        proxy_owners[proxy_port] = dsh_port
        deduped.append((proxy_port, dsh_port))
    return deduped


# ---------------------------------------------------------------- dsh web auth injection (plan B)

def parse_instances_yml() -> list[dict]:
    """Best-effort instance definitions from instances.yml, mirroring manage.py.

    Each entry may declare `port`, `profile`, `home`, and `name`. deploy.py only
    consumes `port` and `home`; the rest stays available for manage.py.
    """
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


def instance_homes_for_mappings(mappings: list[tuple[int, int]]) -> tuple[dict[int, str], list[str]]:
    """Resolve `DSH_HOME` per proxied dsh port from instances.yml.

    Returns `({dsh_port: home}, warnings)`. Ports missing from instances.yml
    fall back to `~/.dsh`; the warning stays quiet for the single-default case
    and only names ports when several dsh instances are being proxied.
    """
    defined = {item['port']: item for item in parse_instances_yml()}
    homes: dict[int, str] = {}
    warnings: list[str] = []
    dsh_ports = sorted({dsh_port for _proxy_port, dsh_port in mappings})
    for dsh_port in dsh_ports:
        item = defined.get(dsh_port)
        home = item.get('home', '~/.dsh') if item is not None else '~/.dsh'
        homes[dsh_port] = home
        if item is None and len(dsh_ports) > 1:
            warnings.append(
                f'instances.yml 未定义端口 {dsh_port}；使用默认 DSH_HOME=~/.dsh。'
                f'若该实例使用独立 DSH_HOME，请在 instances.yml 中声明，否则注入的 Cookie 会读错凭据。',
            )
    return homes, warnings


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def decode_b64url(value: str) -> bytes | None:
    try:
        padding = '=' * (-len(value) % 4)
        return base64.urlsafe_b64decode(value + padding)
    except Exception:
        return None


def load_browser_session_secret(home: str) -> bytes | None:
    """Read the persistent browser-session signing secret from a DSH_HOME.

    The record is written by dsh's connection plugin on first `dsh web` boot
    and lives at `<DSH_HOME>/.credentials.yaml` under the `records` section.
    """
    credentials_path = Path(home).expanduser() / '.credentials.yaml'
    if not credentials_path.is_file():
        return None
    try:
        import yaml
    except ImportError as error:
        raise RuntimeError('reading dsh credentials needs PyYAML - install it with `pip install pyyaml`') from error
    try:
        data = yaml.safe_load(credentials_path.read_text(encoding='utf-8')) or {}
    except Exception as error:
        raise RuntimeError(f'{credentials_path}: {error}') from error
    if not isinstance(data, dict):
        raise RuntimeError(f'{credentials_path}: expected a mapping')
    record = (data.get('records') or {}).get(AUTH_RECORD_KEY)
    if not isinstance(record, dict) or record.get('kind') != 'grant':
        return None
    payload = record.get('payload')
    if not isinstance(payload, dict) or payload.get('version') != 1:
        return None
    secret = payload.get('secret')
    if not isinstance(secret, str):
        return None
    decoded = decode_b64url(secret)
    if decoded is None or len(decoded) != AUTH_SECRET_BYTES:
        raise RuntimeError(f'{credentials_path}: browser-session secret is not {AUTH_SECRET_BYTES} base64url bytes')
    return decoded


def mint_browser_cookie(secret: bytes, authority: str, max_age_days: int) -> str:
    """Mint the dsh web session cookie value for one upstream authority.

    The format is the same `v1.<payload>.<hmac>` signed cookie dsh's
    BrowserAuth accepts; the injected cookie removes the per-browser token
    exchange for every request that arrives through the proxy.
    """
    issued_at = int(time.time() * 1000)
    expires_at = issued_at + max_age_days * 24 * 60 * 60 * 1000
    payload = {'version': 1, 'authority': authority, 'issuedAt': issued_at, 'expiresAt': expires_at}
    body = b64url(json.dumps(payload, separators=(',', ':')).encode('utf-8'))
    cookie_name = 'dsh-auth-' + b64url(hashlib.sha256(authority.encode('utf-8')).digest())
    signature = b64url(hmac.new(secret, body.encode('ascii'), hashlib.sha256).digest())
    return f'{cookie_name}=v1.{body}.{signature}'


def build_upstream_auth_cookies(
    mappings: list[tuple[int, int]],
    auth_cookie_days: int,
) -> tuple[dict[int, str], list[str]]:
    """Mint one upstream Cookie header per proxied dsh port, keyed by dsh port.

    The cookie is bound to `127.0.0.1:<dsh-port>` because the generated
    Caddyfile rewrites Host to that authority. Ports whose DSH_HOME has no
    browser-session record yet are skipped with a warning; the proxy then
    keeps the ordinary token login for that port.
    """
    cookies: dict[int, str] = {}
    warnings: list[str] = []
    homes, home_warnings = instance_homes_for_mappings(mappings)
    warnings.extend(home_warnings)
    for dsh_port in sorted({dsh_port for _proxy_port, dsh_port in mappings}):
        home = homes[dsh_port]
        try:
            secret = load_browser_session_secret(home)
        except RuntimeError as error:
            warnings.append(f'端口 {dsh_port} (DSH_HOME={home}) 无法读取 browser-session 凭据: {error}')
            continue
        if secret is None:
            warnings.append(
                f'端口 {dsh_port} (DSH_HOME={home}) 尚无 browser-session 凭据；'
                f'先启动一次 `dsh web --port {dsh_port}` 生成 .credentials.yaml，再重新 deploy.py reload 以注入 Cookie。',
            )
            continue
        cookies[dsh_port] = mint_browser_cookie(secret, f'127.0.0.1:{dsh_port}', auth_cookie_days)
    return cookies, warnings


def render_caddyfile(
    mappings: list[tuple[int, int]],
    listen_hosts: list[str],
    preserve_host: bool,
    tls: bool,
    manage_port: int,
    http_redirect: bool = True,
    upstream_cookies: dict[int, str] | None = None,
) -> str:
    lines = [
        '# Generated by deploy/ds-harness/deploy.py — run `python3 deploy.py up` again to regenerate.',
        '#',
    ]
    if tls and http_redirect:
        # Native Caddy cannot multiplex HTTP and HTTPS on the same port, so
        # the redirect listens on the standard HTTP port 80. Caddy's own
        # automatic redirects are disabled so this stays explicit and reload
        # swaps the listeners cleanly.
        lines.append('{')
        lines.append('\tauto_https disable_redirects')
        lines.append('}')
        lines.append('')

    def render_site(site_address: str, bind_hosts: list[str], proxy_port: int, dsh_port: int, extra: list[str]) -> None:
        lines.append(f'{site_address} {{')
        if WILDCARD_LISTEN_HOST not in bind_hosts:
            lines.append(f'\tbind {" ".join(bind_hosts)}')
        for extra_line in extra:
            lines.append(f'\t{extra_line}')
        # JSON access logs per site: /manage traffic reads them best-effort and
        # the log files live on the host through the mounted data/ directory.
        lines.append('\tlog {')
        lines.append(f'\t\toutput file /data/logs/access-{proxy_port}-{bind_hosts[0]}.json {{')
        lines.append('\t\t\troll_size 10MiB')
        lines.append('\t\t\troll_keep 2')
        lines.append('\t\t}')
        lines.append('\t\tformat json')
        lines.append('\t}')
        # Proxy-side loading optimizations (dsh is left untouched):
        # - compress everything except the event streams (large session lists
        #   and static bundles shrink substantially over the wire)
        # - cache hashed static assets in the browser
        # - force revalidation for the shell document and API responses
        lines.append('\t@stream path /api/events.host /api/events.mux')
        lines.append('\t@not-stream not path /api/events.host /api/events.mux')
        lines.append('\t@static path /plugins/* /assets/* /favicon.svg')
        lines.append('\t@dynamic path / /api/*')
        lines.append('\tencode @not-stream zstd gzip')
        lines.append('\theader @static Cache-Control "public, max-age=31536000, immutable"')
        lines.append('\theader @dynamic Cache-Control "no-cache"')
        # /manage is served by the Python management backend, not by dsh, so
        # it stays available while dsh itself cannot boot.
        lines.append('\thandle /manage {')
        lines.append('\t\tredir * /manage/ 308')
        lines.append('\t}')
        lines.append('\thandle_path /manage/* {')
        lines.append(f'\t\treverse_proxy 127.0.0.1:{manage_port}')
        lines.append('\t}')
        lines.append('\thandle {')
        lines.append(f'\t\treverse_proxy 127.0.0.1:{dsh_port} {{')
        if not preserve_host:
            # dsh's /api trust fence accepts loopback Hosts; rewriting both
            # Host and Origin keeps browser requests same-origin from dsh's
            # point of view, including the loopback-only privileged methods.
            lines.append(f'\t\t\theader_up Host 127.0.0.1:{dsh_port}')
            lines.append(f'\t\t\theader_up Origin http://127.0.0.1:{dsh_port}')
            injected_cookie = (upstream_cookies or {}).get(dsh_port)
            if injected_cookie is not None:
                # Plan B: Caddy presents a signed dsh web session cookie, so
                # devices that can reach the proxy never see dsh's token gate.
                # The cookie is minted for 127.0.0.1:<dsh_port>, matching the
                # rewritten Host above.
                lines.append(f'\t\t\theader_up Cookie "{injected_cookie}"')
        lines.append('\t\t}')
        lines.append('\t}')
        lines.append('}')
        lines.append('')

    for proxy_port, dsh_port in mappings:
        if tls:
            # One site per listen IP: the site address carries the subject
            # name, so each IP gets its own tls internal certificate.
            for listen_host in listen_hosts:
                render_site(f'https://{listen_host}:{proxy_port}', [listen_host], proxy_port, dsh_port, ['tls internal'])
            continue
        render_site(f'http://:{proxy_port}', listen_hosts, proxy_port, dsh_port, [])

    if tls and http_redirect:
        # HTTP (port 80) redirects to the first proxy port on each listen IP.
        # A port-80 request no longer carries the original destination port, so
        # when several proxy ports share one IP the first mapping wins and the
        # other ports must be accessed with an explicit https:// URL.
        redirect_port = mappings[0][0]
        for listen_host in listen_hosts:
            lines.append(f'http://{listen_host}:80 {{')
            lines.append(f'\tbind {listen_host}')
            lines.append(f'\tredir https://{{host}}:{redirect_port}{{uri}} 308')
            lines.append('}')
            lines.append('')
    return '\n'.join(lines)


def print_mapping_table(
    mappings: list[tuple[int, int]],
    listen_hosts: list[str],
    tls: bool,
    homes: dict[int, str] | None = None,
) -> None:
    scheme = 'https' if tls else 'http'
    print(f'proxy port -> dsh port ({scheme}, loopback upstream)')
    for proxy_port, dsh_port in mappings:
        home = (homes or {}).get(dsh_port)
        home_suffix = f'  [DSH_HOME={home}]' if home is not None else ''
        for listen_host in listen_hosts:
            bind = 'all interfaces' if listen_host == WILDCARD_LISTEN_HOST else listen_host
            print(f'  {scheme}://{bind}:{proxy_port} -> 127.0.0.1:{dsh_port}{home_suffix}')


def print_security_warning(cookie_injected: bool) -> None:
    if cookie_injected:
        print('note: Caddy will inject a signed dsh web session cookie toward the upstream;')
        print('      devices that can reach this proxy no longer need the dsh web startup token.')
        print('warning: the proxy is now the trust boundary again - anyone who can reach it can use dsh;')
    else:
        print('note: newer dsh web requires the startup token printed by `dsh web`.')
        print('      First visit through the proxy must use <proxy-url>/?token=<token> from that line;')
        print('      dsh then mints an HttpOnly browser cookie and the plain <proxy-url>/ works afterwards.')
        print('warning: anyone holding the token can access dsh through this proxy;')
    print('         bind the proxy to a trusted network only (use --listen, a firewall, or Caddy basic_auth).')


def print_settings_availability_warning(listen_hosts: list[str], mappings: list[tuple[int, int]]) -> None:
    """Warn when the proxied dsh client still disables settings on non-loopback page URLs.

    The proxy can rewrite Host/Origin so the settings RPCs pass dsh's
    server-side trust fence, but the current dsh client additionally gates the
    settings domain on `location.hostname`. The only reliable deploy-time signal
    is the served client bundle itself: probe it, and stay silent when the gate
    is gone (dsh updated) or when the proxy only binds loopback.
    """
    if all(host in ('127.0.0.1', '[::1]') for host in listen_hosts):
        return
    blocked, unknown = probe_settings_availability(mappings)
    if not blocked and not unknown:
        return
    if blocked:
        ports = ', '.join(map(str, blocked))
        print(f'note: dsh client on port(s) {ports} still gates settings pages to loopback browsers;')
        print('      through this proxy the models settings page will show "settings are unavailable in this browser".')
    if unknown:
        auth_gated = [port for port in unknown if probe_dsh_port(port) is not None]
        if auth_gated:
            ports = ', '.join(map(str, auth_gated))
            print(f'note: dsh web on port(s) {ports} is token-auth-gated; the settings-bundle probe cannot log in.')
            print('      Through this proxy the models settings page will still show "settings are unavailable in this browser".')
        unreachable = sorted(set(unknown) - set(auth_gated))
        if unreachable:
            ports = ', '.join(map(str, unreachable))
            print(f'note: could not probe dsh settings availability on port(s) {ports} (dsh web not reachable?);')
            print('      if the models settings page reports "settings are unavailable in this browser", use the workaround below.')
    if blocked or unknown:
        print('      Full settings access: run `up --listen 127.0.0.1` and browse through an SSH local forward')
        print('      (e.g. ssh -L <port>:127.0.0.1:<dsh-port> <server>, then visit http://127.0.0.1:<port>/).')


def print_login_url_guidance(
    listen_hosts: list[str],
    mappings: list[tuple[int, int]],
    tls: bool,
    cookie_injected: bool,
) -> None:
    """Print the access URL shape for each proxied dsh web instance.

    With plan-B cookie injection the plain proxy URL is already authenticated;
    without it, dsh web prints a per-process `?token=...` at startup and the
    first visit must use that URL through the proxy.
    """
    scheme = 'https' if tls else 'http'
    if cookie_injected:
        print('access: Caddy injects the dsh web session cookie; open the plain URL:')
    else:
        print('first login: paste the token from the `dsh web:` startup line into:')
    for proxy_port, dsh_port in mappings:
        for listen_host in listen_hosts:
            host = '<host>' if listen_host == WILDCARD_LISTEN_HOST else listen_host
            suffix = '' if cookie_injected else '/?token=<TOKEN>'
            print(f'  {scheme}://{host}:{proxy_port}{suffix}  -> 127.0.0.1:{dsh_port}')


def write_caddyfile(content: str, dry_run: bool) -> None:
    if dry_run:
        print('\n[Caddyfile]')
        print(content, end='')
        return
    CADDYFILE_PATH.write_text(content, encoding='utf-8')
    # When plan-B cookie injection is active the Caddyfile carries a bearer
    # cookie for dsh web; keep it owner-readable like the other machine-local
    # secrets (Caddy runs as the same user and reads it fine).
    os.chmod(CADDYFILE_PATH, 0o600)
    print(f'wrote {CADDYFILE_PATH}')


def collect_mappings(args: argparse.Namespace) -> list[tuple[int, int]]:
    specs: list[str] = args.ports
    if not specs and not args.auto:
        specs = [str(DEFAULT_DSH_PORT)]
    mappings: list[tuple[int, int]] = []
    for spec in specs:
        try:
            mappings.append(parse_port_spec(spec))
        except ValueError as error:
            raise SystemExit(f'error: {error}') from error

    if args.auto:
        discovered = scan_dsh_ports()
        if discovered:
            print(f'auto-scan: discovered dsh web services on ports: {", ".join(map(str, discovered))}')
        else:
            print('auto-scan: no dsh web services found')
        mappings.extend((port, port) for port in discovered)

    mappings = dedupe_mappings(mappings)
    if not mappings:
        raise SystemExit('nothing to proxy: pass PORTS, or run --auto while at least one dsh web service is listening')
    return mappings


def prepare_data_dirs(args: argparse.Namespace) -> None:
    """Ensure /data subdirs exist and are owned by the host user.

    Caddy runs as the host user (--user), so TLS storage and JSON access logs
    are readable by manage.py. A data/caddy directory left by an older
    root-run Caddy belongs to another uid; it is renamed aside so the new
    container starts with a fresh, user-owned storage.
    """
    data = CADDYFILE_PATH.parent / 'data'
    logs = data / 'logs'
    caddy = data / 'caddy'
    if args.dry_run:
        print(f'dry-run: would ensure {data} and {logs} exist')
        if caddy.exists():
            stat = caddy.stat()
            if stat.st_uid != os.getuid() or stat.st_gid != os.getgid():
                print(f'dry-run: would rename {caddy} (owned by {stat.st_uid}:{stat.st_gid}) aside and create a fresh one')
        for log_file in logs.glob('access-*.json'):
            stat = log_file.stat()
            if stat.st_uid != os.getuid() or stat.st_gid != os.getgid():
                print(f'dry-run: would remove old unreadable access log {log_file}')
        return
    data.mkdir(parents=True, exist_ok=True)
    logs.mkdir(parents=True, exist_ok=True)
    if caddy.exists():
        stat = caddy.stat()
        if stat.st_uid != os.getuid() or stat.st_gid != os.getgid():
            backup = data / f'caddy.bak-{time.strftime("%Y%m%d-%H%M%S")}'
            caddy.rename(backup)
            print(f'renamed {caddy} -> {backup} (old owner {stat.st_uid}:{stat.st_gid}); new TLS CA will be generated')
    caddy.mkdir(parents=True, exist_ok=True)
    for log_file in logs.glob('access-*.json'):
        try:
            stat = log_file.stat()
        except OSError:
            continue
        if stat.st_uid != os.getuid() or stat.st_gid != os.getgid():
            log_file.unlink()
            print(f'removed old unreadable access log {log_file} (owned by {stat.st_uid}:{stat.st_gid})')


def docker_run_proxy(args: argparse.Namespace) -> int:
    command = [
        'docker', 'run', '-d',
        '--name', args.container,
        '--network', 'host',
        '--restart', 'unless-stopped',
        # Run as the host user so data/ logs and TLS storage are readable by
        # deploy.py and manage.py; NET_BIND_SERVICE keeps the port-80 redirect
        # bindable for --tls mode.
        '--user', f'{os.getuid()}:{os.getgid()}',
        '--cap-add', 'NET_BIND_SERVICE',
        '-v', f'{CADDYFILE_PATH.parent}:/etc/caddy:ro',
        '-v', f'{CADDYFILE_PATH.parent / "data"}:/data',
        args.image,
    ]
    return run(command, dry_run=args.dry_run)


def manage_pid() -> int | None:
    try:
        return int(MANAGE_PID_PATH.read_text(encoding='utf-8').strip())
    except (OSError, ValueError):
        return None


def manage_running() -> bool:
    pid = manage_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def start_manage(args: argparse.Namespace) -> int:
    if manage_running():
        print(f'manage server already running (pid {manage_pid()}) on 127.0.0.1:{args.manage_port}')
        return 0
    MANAGE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    (MANAGE_DATA_DIR / 'logs').mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable, str(MANAGE_SCRIPT_PATH),
        '--port', str(args.manage_port),
        '--container', args.container,
    ]
    print_command(command)
    if args.dry_run:
        return 0
    log_file = open(MANAGE_LOG_PATH, 'a', encoding='utf-8')
    process = subprocess.Popen(
        command,
        cwd=str(MANAGE_SCRIPT_PATH.parent),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    MANAGE_PID_PATH.write_text(str(process.pid), encoding='utf-8')
    time.sleep(0.4)
    if process.poll() is not None:
        MANAGE_PID_PATH.unlink(missing_ok=True)
        raise SystemExit(
            f'manage server exited immediately (code {process.returncode}); '
            f'check {MANAGE_LOG_PATH} — the manage port {args.manage_port} may already be in use',
        )
    print(f'started manage server (pid {process.pid}) on http://127.0.0.1:{args.manage_port}')
    print(f'manage UI: <proxy-url>/manage/')
    return 0


def stop_manage(args: argparse.Namespace) -> int:
    pid = manage_pid()
    if pid is None:
        print('manage server is not running')
        return 0
    print(f'==> stopping manage server (pid {pid})')
    if args.dry_run:
        return 0
    try:
        os.kill(pid, 15)
    except ProcessLookupError:
        pass
    except OSError as error:
        print(f'warning: failed to stop manage server: {error}')
    MANAGE_PID_PATH.unlink(missing_ok=True)
    return 0


def cmd_up(args: argparse.Namespace) -> int:
    if not docker_available():
        raise SystemExit('`docker` is required but not found on PATH')
    mappings = collect_mappings(args)
    if args.tls and WILDCARD_LISTEN_HOST in args.listen:
        raise SystemExit('--tls needs concrete --listen IP(s) (the default LAN IP works); 0.0.0.0 cannot be used with tls internal')

    homes, home_warnings = instance_homes_for_mappings(mappings)
    for warning in home_warnings:
        print(f'warning: {warning}')
    upstream_cookies: dict[int, str] = {}
    cookie_injected = False
    if not args.preserve_host:
        upstream_cookies, cookie_warnings = build_upstream_auth_cookies(mappings, args.auth_cookie_days)
        for warning in cookie_warnings:
            print(f'warning: {warning}')
        cookie_injected = bool(upstream_cookies)
        if cookie_injected and args.auth_cookie_days > DEFAULT_AUTH_COOKIE_DAYS:
            print(f'note: --auth-cookie-days {args.auth_cookie_days} requires the dsh connection plugin '
                  f'cookieMaxAgeDays >= {args.auth_cookie_days} for each proxied profile, otherwise dsh rejects the injected cookie.')
    else:
        print('note: --preserve-host 模式下不注入会话 Cookie；通过代理访问仍需各自 token 登录。')

    print_mapping_table(mappings, args.listen, args.tls, homes)
    print_security_warning(cookie_injected)
    print_settings_availability_warning(args.listen, mappings)
    print_login_url_guidance(args.listen, mappings, args.tls, cookie_injected)

    state = container_state(args.container)
    if state is not None:
        print(f'==> removing existing container {args.container} ({state})')
        if run(['docker', 'rm', '-f', args.container], dry_run=args.dry_run) != 0 and not args.dry_run:
            raise SystemExit(1)

    http_redirect = True
    if args.tls and not args.dry_run and bind_conflicts(args.listen, 80):
        print('warning: port 80 is in use on one of the listen IPs; '
              'HTTP->HTTPS redirect sites will not be generated (HTTPS only)')
        http_redirect = False

    if not args.dry_run:
        for proxy_port, _dsh_port in mappings:
            if bind_conflicts(args.listen, proxy_port):
                if WILDCARD_LISTEN_HOST in args.listen:
                    raise SystemExit(
                        f'proxy port {proxy_port} is already in use; if the listener is dsh itself on '
                        f'127.0.0.1:{proxy_port}, caddy cannot also bind 0.0.0.0:{proxy_port}. '
                        f'Use specific --listen <本机IP> (caddy will bind only those IPs) or a different '
                        f'proxy port, e.g. `up 8080:{proxy_port}`',
                    )
                raise SystemExit(f'proxy port {proxy_port} is already in use on one of {", ".join(args.listen)}')

    content = render_caddyfile(
        mappings, args.listen, args.preserve_host, args.tls, args.manage_port, http_redirect,
        upstream_cookies=upstream_cookies,
    )
    write_caddyfile(content, args.dry_run)
    prepare_data_dirs(args)

    if docker_run_proxy(args) != 0:
        raise SystemExit(f'docker run failed; check `docker logs {args.container}`')
    if start_manage(args) != 0:
        raise SystemExit('failed to start manage server')
    if not args.dry_run:
        print(f'started {args.container} ({args.image}, host network)')
        scheme = 'https' if args.tls else 'http'
        for listen_host in args.listen:
            host = '<host>' if listen_host == WILDCARD_LISTEN_HOST else listen_host
            for proxy_port, _dsh_port in mappings:
                print(f'  {scheme}://{host}:{proxy_port}/')
                print(f'  {scheme}://{host}:{proxy_port}/manage/  (dsh manage)')
        if args.tls and http_redirect:
            redirect_port = mappings[0][0]
            for listen_host in args.listen:
                host = '<host>' if listen_host == WILDCARD_LISTEN_HOST else listen_host
                print(f'  http://{host}/ -> https://{host}:{redirect_port}/')
    return 0


def cmd_down(args: argparse.Namespace) -> int:
    if not docker_available():
        raise SystemExit('`docker` is required but not found on PATH')
    state = container_state(args.container)
    if state is None:
        print(f'{args.container} does not exist')
    else:
        print(f'==> removing {args.container} ({state})')
        if run(['docker', 'rm', '-f', args.container], dry_run=args.dry_run) != 0:
            raise SystemExit(1)
    return stop_manage(args)


def cmd_status(args: argparse.Namespace) -> int:
    state = container_state(args.container)
    print(f'{args.container}: {state or "does not exist"}')
    if state == 'running':
        completed = subprocess.run(
            ['docker', 'logs', '--tail', '10', args.container],
            capture_output=True,
            text=True,
        )
        print('--- recent caddy logs ---')
        print(completed.stdout.strip())
    print(f'manage server: {"running (pid " + str(manage_pid()) + ")" if manage_running() else "not running"}')
    if CADDYFILE_PATH.is_file():
        print('--- Caddyfile sites ---')
        for line in CADDYFILE_PATH.read_text(encoding='utf-8').splitlines():
            if re.match(r'^https?://', line):
                print(line)
    return 0


def cmd_scan(_args: argparse.Namespace) -> int:
    discovered = scan_dsh_ports()
    if discovered:
        print('discovered dsh web services on ports: ' + ', '.join(map(str, discovered)))
    else:
        print('no dsh web services found')
    return 0


def cmd_reload(args: argparse.Namespace) -> int:
    if not docker_available():
        raise SystemExit('`docker` is required but not found on PATH')
    mappings = collect_mappings(args)
    if args.tls and WILDCARD_LISTEN_HOST in args.listen:
        raise SystemExit('--tls needs concrete --listen IP(s) (the default LAN IP works); 0.0.0.0 cannot be used with tls internal')

    homes, home_warnings = instance_homes_for_mappings(mappings)
    for warning in home_warnings:
        print(f'warning: {warning}')
    upstream_cookies: dict[int, str] = {}
    cookie_injected = False
    if not args.preserve_host:
        upstream_cookies, cookie_warnings = build_upstream_auth_cookies(mappings, args.auth_cookie_days)
        for warning in cookie_warnings:
            print(f'warning: {warning}')
        cookie_injected = bool(upstream_cookies)
        if cookie_injected and args.auth_cookie_days > DEFAULT_AUTH_COOKIE_DAYS:
            print(f'note: --auth-cookie-days {args.auth_cookie_days} requires the dsh connection plugin '
                  f'cookieMaxAgeDays >= {args.auth_cookie_days} for each proxied profile, otherwise dsh rejects the injected cookie.')
    else:
        print('note: --preserve-host 模式下不注入会话 Cookie；通过代理访问仍需各自 token 登录。')

    print_mapping_table(mappings, args.listen, args.tls, homes)
    print_security_warning(cookie_injected)
    print_settings_availability_warning(args.listen, mappings)
    print_login_url_guidance(args.listen, mappings, args.tls, cookie_injected)
    content = render_caddyfile(
        mappings, args.listen, args.preserve_host, args.tls, args.manage_port,
        upstream_cookies=upstream_cookies,
    )
    write_caddyfile(content, args.dry_run)
    if not args.dry_run:
        (CADDYFILE_PATH.parent / 'data' / 'logs').mkdir(parents=True, exist_ok=True)

    state = container_state(args.container)
    if state != 'running':
        raise SystemExit(f'{args.container} is not running ({state or "missing"}); run `python3 deploy.py up` first')
    command = [
        'docker', 'exec', args.container,
        'caddy', 'reload',
        '--config', '/etc/caddy/Caddyfile',
        '--adapter', 'caddyfile',
    ]
    code = run(command, dry_run=args.dry_run)
    if code != 0:
        raise SystemExit(code)
    return start_manage(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        'action',
        nargs='?',
        choices=['up', 'down', 'status', 'scan', 'reload', 'install', 'update'],
        default='up',
    )
    parser.add_argument(
        'ports',
        nargs='*',
        help='deploy: port mappings PORT or PROXY:DSH (default: 3080); update: plugin names to update (default: all in plugins.yml)',
    )
    parser.add_argument('--auto', action='store_true', help='deploy: scan 127.0.0.1 listening ports for dsh web services and add them')
    parser.add_argument('--listen', action='append', default=None, help='deploy: proxy bind host; repeat for multiple IPs (default: first non-loopback IPv4, fallback 0.0.0.0; use 127.0.0.1 for local-only)')
    parser.add_argument('--preserve-host', action='store_true', help='deploy: do not rewrite Host/Origin to loopback (dsh then needs --trusted-host; privileged methods stay loopback-only)')
    parser.add_argument('--auth-cookie-days', type=int, default=DEFAULT_AUTH_COOKIE_DAYS, help=f'deploy: lifetime in days for the Caddy-injected dsh web session cookie; requires dsh connection cookieMaxAgeDays >= this value (default: {DEFAULT_AUTH_COOKIE_DAYS})')
    parser.add_argument('--tls', action='store_true', help='deploy: serve HTTPS on the proxy ports with Caddy internal CA (needs a concrete --listen IP; fixes browser crypto.randomUUID on LAN access)')
    parser.add_argument('--container', default=DEFAULT_CONTAINER, help=f'deploy: caddy container name (default: {DEFAULT_CONTAINER})')
    parser.add_argument('--image', default=DEFAULT_IMAGE, help=f'deploy: caddy docker image (default: {DEFAULT_IMAGE})')
    parser.add_argument('--manage-port', type=int, default=DEFAULT_MANAGE_PORT, help=f'deploy: loopback port for the /manage backend (default: {DEFAULT_MANAGE_PORT})')
    parser.add_argument('--profile', default=None, help='plugin: dsh profile name (default: $DSH_PROFILE or web)')
    parser.add_argument('--home', default=None, help='plugin: dsh home directory (default: $DSH_HOME or ~/.dsh)')
    parser.add_argument('--dsh', default=None, help='plugin: dsh executable (default: dsh from PATH)')
    parser.add_argument('--dry-run', action='store_true', help='print commands and generated Caddyfile without executing')
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    action = args.action or 'up'

    if action in ('install', 'update'):
        if args.auto or args.listen is not None or args.preserve_host or args.tls:
            raise SystemExit('error: --auto/--listen/--preserve-host/--tls are deployment-only options; install/update only take --profile/--home/--dsh/--dry-run')
        args.profile = plugin_profile(args)
        args.home = plugin_home(args)
        args.dsh = plugin_dsh(args)
        return cmd_install(args) if action == 'install' else cmd_update(args)

    if args.profile is not None or args.home is not None or args.dsh is not None:
        raise SystemExit('error: --profile/--home/--dsh are plugin-management-only options; use them with install/update')
    if not 1 <= args.auth_cookie_days <= 36500:
        raise SystemExit('error: --auth-cookie-days must be between 1 and 36500')
    if args.listen is None:
        args.listen = [default_listen_host()]
    if action in ('up', 'reload'):
        for listen_host in args.listen:
            if listen_host != WILDCARD_LISTEN_HOST and re.match(r'^[0-9a-fA-F:.]+$', listen_host) is None:
                raise SystemExit(f'error: --listen {listen_host!r} does not look like an IP address')

    commands = {
        'up': cmd_up,
        'down': cmd_down,
        'status': cmd_status,
        'scan': cmd_scan,
        'reload': cmd_reload,
    }
    raise SystemExit(commands[action](args))


if __name__ == '__main__':
    main()
