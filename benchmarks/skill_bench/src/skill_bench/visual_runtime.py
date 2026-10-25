"""Explicit visual runtimes and trusted drivers inside the existing command sandbox."""
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

CAPABILITIES = {'browser_capture', 'playable_motion', 'action_trace_capture', 'web_audio_probe', 'blender', 'native_scene_reopen'}
DRIVERS = {'browser': 'browser_driver.py', 'blender': 'blender_driver.py'}
DEFAULT_BROWSER_SCENARIO = {
    'samples_ms': [0, 80, 180, 300, 450, 800, 1600, 2400],
    'profiles': ['desktop', 'mobile', 'reduced_motion'],
    'selectors': ['button', '[aria-selected="true"]', '[aria-expanded="true"]'],
    'actions': [{'time_ms': 50, 'type': 'key', 'key': 'Tab'},
                {'time_ms': 100, 'type': 'key', 'key': 'Enter'},
                {'time_ms': 200, 'type': 'key', 'key': 'Tab'},
                {'time_ms': 240, 'type': 'key', 'key': 'Enter'}],
}


def required_tools(capabilities):
    values = set(capabilities)
    return (["browser"] if values & {'browser_capture', 'playable_motion', 'action_trace_capture', 'web_audio_probe'} else []) + (["blender"] if values & {'blender', 'native_scene_reopen'} else [])


def discover(config=None, required=()):
    """Inspect explicit executables or bounded known defaults; never install or scan home."""
    config = config or {}
    defaults = {
        'browser': Path.home() / '.cache/ms-playwright/chromium-1228/chrome-linux64/chrome',
        'blender': Path.home() / '.local/share/maintainall/art-runtimes/blender-4.5.14-linux-x64/blender',
    }
    tools = {}
    for name in required_tools(required):
        explicit = config.get(name)
        candidate = Path(explicit).expanduser() if explicit else Path(shutil.which('blender') or defaults[name]) if name == 'blender' else defaults[name]
        candidate = candidate.resolve()
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            raise ValueError('Required visual runtime is unavailable: ' + name)
        # A runtime grant must not expose home, an authentication tree or a whole repository.
        root = candidate.parent
        if root in {Path('/'), Path.home(), Path.home() / '.codex', Path.home() / '.agents'} or any((p / '.git').exists() for p in (root, *root.parents)):
            raise ValueError('Visual runtime must live in a dedicated installation directory')
        info = candidate.stat()
        identity = _identity(str(candidate), info.st_size, info.st_mtime_ns)
        tools[name] = {'executable': str(candidate), 'root': str(root), **identity,
                       'driver_sha256': digest((Path(__file__).parent / DRIVERS[name]).read_bytes())}
        if name == 'browser':
            from .browser_namespace import fingerprint_identity
            tools[name]['namespace_runtime'] = fingerprint_identity()
    return tools


def regrade_tools(frozen, required=()):
    """Pin generation executables while discovering current trusted verifier code.

    Return a fresh current tool identity for staging and source-runtime records.
    Driver and namespace-wrapper changes belong to the independent verifier
    revision; executable paths, roots, bytes, versions and confinement methods
    remain pinned. Never mutate generation identities or fall back to defaults
    when a required frozen runtime is absent.
    """
    import copy

    names = required_tools(required)
    if not names:
        return {}
    if not isinstance(frozen, dict):
        raise ValueError('Frozen visual runtime identities are required for regrading')

    def pinned(identity, fields, label):
        if not isinstance(identity, dict):
            raise ValueError('Frozen ' + label + ' identity is missing')
        for field in fields:
            value = identity.get(field)
            if not isinstance(value, str) or not value:
                raise ValueError('Frozen ' + label + ' identity is incomplete: ' + field)
            if field == 'sha256' and (len(value) != 64 or any(c not in '0123456789abcdef' for c in value)):
                raise ValueError('Frozen ' + label + ' executable hash is invalid')
        return {field: identity[field] for field in fields}

    executable_fields = ('executable', 'root', 'sha256', 'version')
    namespace_fields = ('executable', 'sha256', 'version', 'method')
    expected = {}
    expected_namespace = {}
    for name in names:
        expected[name] = pinned(frozen.get(name), executable_fields, name)
        if name == 'browser':
            expected_namespace[name] = pinned(frozen[name].get('namespace_runtime'), namespace_fields, 'browser namespace')
    current = copy.deepcopy(discover({name: expected[name]['executable'] for name in names}, required))
    if set(current) != set(names):
        raise ValueError('Required visual runtime population changed before regrading')
    for name in names:
        actual = pinned(current[name], executable_fields, name)
        if actual != expected[name]:
            raise ValueError('Visual runtime executable differs from the frozen experiment: ' + name)
        if name == 'browser':
            actual_namespace = pinned(current[name].get('namespace_runtime'), namespace_fields, 'browser namespace')
            if actual_namespace != expected_namespace[name]:
                raise ValueError('Browser namespace runtime differs from the frozen experiment')
    return current


def digest(data):
    return hashlib.sha256(data).hexdigest()


@lru_cache(maxsize=16)
def _identity(path, size, modified):
    result = subprocess.run([path, '--version'], capture_output=True, text=True, timeout=15, check=True)
    return {'sha256': digest(Path(path).read_bytes()), 'version': result.stdout.splitlines()[0], 'size': size}


def stage(workspace, tools):
    if not tools:
        return {}
    target = Path(workspace) / 'tools'
    target.mkdir(mode=0o700)
    hashes = {}
    for name in tools:
        filename = DRIVERS[name]
        data = (Path(__file__).parent / filename).read_bytes()
        if digest(data) != tools[name]['driver_sha256']:
            raise ValueError('Visual driver changed after runtime discovery')
        (target / filename).write_bytes(data)
        hashes[filename] = digest(data)
    if 'browser' in tools:
        filename = 'browser_client.py'
        data = (Path(__file__).parent / filename).read_bytes()
        (target / filename).write_bytes(data)
        hashes[filename] = digest(data)
    return hashes


def config_args(tools, package, renderer):
    """Add read-only grants to the existing root-deny profile, without broad access."""
    from .backends.local_codex import legacy
    if not tools:
        return []
    # Codex's override parser does not support quoted dotted filesystem keys.
    # Replace the complete inline table, retaining every standing deny/grant.
    values = {':root': 'deny', ':minimal': 'read', ':slash_tmp': 'deny', ':tmpdir': 'deny',
              str(package): 'read', str(renderer): 'read',
              ':workspace_roots': {'.': 'write', 'skill': 'read', 'inputs': 'read', 'tools': 'read'}}
    values.update({tool['root']: 'read' for tool in tools.values()})
    return ['-c', 'permissions.' + legacy().core.PROFILE + '.filesystem=' + legacy().core.toml(values)]


def environment(tools):
    if not tools:
        return ''
    text = ['Additional offline tools (explicit read-only runtime grants; no credentials or command networking):']
    if 'browser' in tools:
        text.append('Capture actual timed Chromium frames with /usr/bin/python3 tools/browser_client.py --source index.html --output capture [--spec scenario.json]. Use tools/browser_driver.py --help for bounded playback and input scenarios. The trusted local broker renders in a separate offline kernel namespace, preserving relative assets and temporary profiles. Direct Chromium startup under the Codex syscall filter is unsupported. Remove unneeded capture directories before the next turn. Screenshots alone do not prove all interaction requirements.')
    if 'blender' in tools:
        text.append('Blender: ' + tools['blender']['executable'] + '. Create native scenes with this binary in background mode; inspect driver help with /usr/bin/python3 tools/blender_driver.py --help. Independent scene verification uses --factory-startup --disable-autoexec and a trusted driver; it does not execute your generator. Prefer bounded CPU/Workbench renders and packed/self-contained native files. Keep each artifact below 8 MiB and the complete workspace below 32 MiB.')
    return '\n'.join(text) + '\n'


def sandbox(workspace, renderer, tools, arguments, *, timeout=120):
    """The trusted host client authenticates; the child command gets no host secrets."""
    from .backends.local_codex import legacy
    executable, package = legacy().core.runtime()
    args = [executable, 'sandbox', '-P', legacy().core.PROFILE, '-C', str(workspace),
            *legacy().core.config_args(package, renderer=Path(renderer), readonly_inputs=True),
            *config_args(tools, package, Path(renderer)), *map(str, arguments)]
    process = subprocess.Popen(args, cwd=workspace, env=legacy().core.host_env(), stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except BaseException:
        legacy().core.stop(process)
        raise
    if process.returncode:
        # Keep diagnostics bounded and never echo generated documents or host credentials.
        raise ValueError('Sandboxed visual command failed (' + str(process.returncode) + '): ' + (stderr + stdout)[-1500:])
    return stdout


def doctor(renderer, tools):
    """Exercise actual visual tools, mounts and pipe transport with zero model calls."""
    if not tools:
        return {'passed': True, 'checks': {}, 'generation_calls': 0}
    key = digest(json.dumps({'tools': tools, 'renderer': str(renderer), 'module': digest(Path(__file__).read_bytes())}, sort_keys=True).encode())
    return _doctor(key, str(renderer), json.dumps(tools, sort_keys=True))


@lru_cache(maxsize=8)
def _doctor(key, renderer, encoded_tools):
    tools = json.loads(encoded_tools)
    checks, capability_checks = {}, {}
    with tempfile.TemporaryDirectory(prefix='skill-bench-visual-doctor-') as tmp:
        workspace = Path(tmp)
        (workspace / 'inputs').mkdir()
        stage(workspace, tools)
        # Test the expanded grants, rather than assuming the old profile proves them.
        probe = "import json,pathlib,socket; checks={}; paths=" + repr([str(Path.home() / '.codex/auth.json'), str(Path.home() / '.agents')]) + ";\nfor p in paths:\n try: q=pathlib.Path(p);q.read_bytes() if q.is_file() else list(q.iterdir());checks[p]=False\n except OSError: checks[p]=True\ntry: pathlib.Path('tools/blocked').write_text('x');checks['tools_readonly']=False\nexcept OSError: checks['tools_readonly']=True\ntry: s=socket.socket();s.settimeout(1);s.connect(('1.1.1.1',443));checks['network_denied']=False\nexcept OSError: checks['network_denied']=True\nprint(json.dumps({'passed':all(checks.values()),'checks':checks}))"
        isolation = json.loads(sandbox(workspace, renderer, tools, ['/usr/bin/python3', '-I', '-c', probe], timeout=25))
        if not isolation['passed']:
            raise ValueError('Expanded visual sandbox enforcement failed')
        checks['isolation'] = isolation
        if 'browser' in tools:
            from .browser_namespace import namespace_capture, namespace_doctor
            (workspace / 'inputs/source.html').write_text('<!doctype html><style>body{margin:0}div{width:80px;height:80px;background:#087;animation:m .7s linear infinite alternate}@keyframes m{to{transform:translateX(150px)}}</style><div></div><button onclick="this.textContent=\'Selected\'">Select</button>')
            checks['browser_namespace'] = namespace_doctor(workspace, tools)
            evidence = namespace_capture(workspace, workspace / 'inputs/source.html', workspace / 'browser-check', tools, timeout=60)
            checks['browser'] = {'passed': evidence.get('passed') is True and len({f['sha256'] for f in evidence.get('frames', [])}) > 1, 'frame_count': len(evidence.get('frames', [])), 'scope': evidence.get('scope')}
            from .action_acceptance import action_doctor
            accepted = action_doctor(workspace, tools)
            capability_checks = {name: accepted[name] for name in ('action_trace_capture', 'web_audio_probe')}
        if 'blender' in tools:
            command = [tools['blender']['executable'], '--background', '--factory-startup', '--disable-autoexec', '--threads', '1', '--python', 'tools/blender_driver.py', '--']
            sandbox(workspace, renderer, tools, [*command, '--fixture', 'fixture.blend'], timeout=40)
            sandbox(workspace, renderer, tools, [*command, '--source', 'fixture.blend', '--output', 'blender-check'], timeout=120)
            evidence = json.loads((workspace / 'blender-check/evidence.json').read_text())
            checks['blender'] = {'passed': evidence.get('source_reopen_verified') is True and evidence.get('source_editability_verified') is True, 'scope': evidence.get('scope', evidence.get('edit_scope'))}
    return {'passed': all(item['passed'] for item in checks.values()), 'checks': checks,
            'capability_checks': capability_checks, 'generation_calls': 0, 'fingerprint': key}
