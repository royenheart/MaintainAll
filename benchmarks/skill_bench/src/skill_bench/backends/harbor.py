"""Pinned Harbor orchestration through public custom agent/environment APIs.

The execution environment is the verified Codex Linux sandbox, not Harbor's
built-in Docker/Codex adapter. Authentication remains in the trusted host CLI.
"""

import asyncio
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from urllib.parse import unquote, urlparse
import uuid

from .base import Backend
from .local_codex import LocalCodexBackend, legacy, write_json


SOURCE_SHA = 'd5ac1be17f575852eaf4fffc4072fd18481c209b'
VERSION = '0.24.0'
_TRIALS = {}


def runtime_identity():
    """Fingerprint the executing interpreter and its actual installed versions."""
    versions = sorted((distribution.metadata.get('Name', '').lower().replace('_', '-'), distribution.version)
                      for distribution in importlib.metadata.distributions() if distribution.metadata.get('Name'))
    executable = Path(sys.executable).resolve()
    return {'python_version': sys.version, 'implementation': sys.implementation.name,
            'python_executable': str(executable), 'python_executable_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
            'environment_prefix': sys.prefix, 'machine': platform.machine(),
            'dependency_versions': versions,
            'dependency_versions_sha256': hashlib.sha256(json.dumps(versions, separators=(',', ':')).encode()).hexdigest()}


def validate_native_result(result, turn_ids):
    """Completed local calls cannot hide failed Harbor lifecycle evidence."""
    trials = result.trial_results
    if len(trials) != 1 or trials[0].exception_info is not None:
        raise ValueError('Harbor native trial lifecycle failed or is incomplete.')
    steps = trials[0].step_results or []
    if [step.step_name for step in steps] != turn_ids or any(step.exception_info is not None for step in steps):
        raise ValueError('Harbor native step evidence failed or is incomplete.')


def verify_local_git_source(distribution, url):
    """Verify a local install against actual fixed Git objects, not a label."""
    parsed = urlparse(url)
    if parsed.scheme != 'file' or parsed.netloc:
        raise ValueError('Harbor provenance is not a supported official source.')
    source = Path(unquote(parsed.path))
    try:
        remote = subprocess.check_output(['git', '-C', str(source), 'remote', 'get-url', 'origin'], text=True, timeout=10).strip()
        revision = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True, timeout=10).strip()
        tree = subprocess.check_output(['git', '-C', str(source), 'ls-tree', '-rz', SOURCE_SHA, 'src/harbor'], timeout=10)
    except (OSError, subprocess.SubprocessError) as error:
        raise ValueError('Local Harbor provenance has no verifiable fixed Git tree.') from error
    if remote not in {'https://github.com/harbor-framework/harbor', 'https://github.com/harbor-framework/harbor.git'} or revision != SOURCE_SHA:
        raise ValueError('Local Harbor provenance is not the official fixed Git checkout.')
    expected = {}
    for record in tree.split(b'\0'):
        if not record:
            continue
        metadata, name = record.split(b'\t', 1)
        mode, kind, object_id = metadata.split()
        if kind != b'blob' or mode not in {b'100644', b'100755'}:
            raise ValueError('Harbor source tree contains unsupported linked/special entries.')
        expected[name.decode().removeprefix('src/')] = object_id.decode()
    checked = {}
    for relative in distribution.files or []:
        name = relative.as_posix()
        if not name.startswith('harbor/') or '__pycache__' in relative.parts or name.endswith(('.pyc', '.pyo')):
            continue
        path = distribution.locate_file(relative)
        if path.is_symlink() or name not in expected:
            raise ValueError('Installed Harbor module is outside the fixed source tree.')
        data = path.read_bytes()
        git_blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if git_blob != expected[name]:
            raise ValueError('Installed Harbor bytes differ from fixed Git source objects.')
        checked[name] = hashlib.sha256(data).hexdigest()
    if not checked or any(name.endswith('.py') and name not in checked for name in expected):
        raise ValueError('Installed Harbor provenance is incomplete.')
    return {'official_url': remote, 'git_commit': revision, 'verified_package_files': len(checked),
            'package_files_sha256': hashlib.sha256(json.dumps(checked, sort_keys=True).encode()).hexdigest()}


def runtime_check(config):
    explicit = config.get('harbor_runtime')
    if explicit and not (Path(explicit) / 'bin/python').is_file():
        raise ValueError('The explicitly selected Harbor runtime is unavailable.')
    try:
        distribution = importlib.metadata.distribution('harbor')
    except importlib.metadata.PackageNotFoundError as error:
        raise ValueError('Pinned Harbor is not installed in this interpreter.') from error
    if distribution.version != VERSION:
        raise ValueError('Harbor version differs from the validated source pin.')
    provenance = distribution.read_text('direct_url.json')
    data = json.loads(provenance or '{}')
    vcs = data.get('vcs_info', {}).get('commit_id')
    archive = data.get('url', '')
    trusted_repository = archive.rstrip('/') in {'https://github.com/harbor-framework/harbor', 'https://github.com/harbor-framework/harbor.git'}
    trusted_archive = archive in {
        'https://codeload.github.com/harbor-framework/harbor/tar.gz/' + SOURCE_SHA,
        'https://github.com/harbor-framework/harbor/archive/' + SOURCE_SHA + '.tar.gz',
        'https://api.github.com/repos/harbor-framework/harbor/tarball/' + SOURCE_SHA,
    }
    verification = None
    if not ((vcs == SOURCE_SHA and trusted_repository) or trusted_archive):
        if archive.startswith('file:'):
            verification = verify_local_git_source(distribution, archive)
        else:
            raise ValueError('Harbor installation provenance does not establish the exact source SHA.')
    return {'version': distribution.version, 'source_sha': SOURCE_SHA, 'direct_url': data, 'local_git_verification': verification}


def integrations():
    """Load the optional dependency only when explicitly selecting Harbor."""
    if 'HarborCodexAgent' in globals():
        return
    from harbor.agents.base import BaseAgent
    from harbor.agents.capabilities import AgentCapabilities
    from harbor.environments.base import BaseEnvironment, ExecResult
    from harbor.environments.capabilities import EnvironmentCapabilities

    class HarborCodexEnvironment(BaseEnvironment):
        def __init__(self, *args, session_key, **kwargs):
            self.entry = _TRIALS[session_key]
            super().__init__(*args, **kwargs)

        @staticmethod
        def type():
            return 'codex-linux-profile'

        @property
        def capabilities(self):
            return EnvironmentCapabilities(disable_internet=True)

        def _validate_definition(self):
            if self.network_policy.network_mode.value != 'no-network':
                raise ValueError('This environment only supports command no-network mode.')
            if self._mounts and any(mount.get('read_only') and mount.get('source') for mount in self._mounts):
                raise ValueError('Arbitrary host input mounts are unsupported.')

        async def start(self, force_build):
            report = self.entry['local'].doctor({'renderer': self.entry['prepared'].spec['renderer'],
                                                'visual_tools': self.entry['prepared'].state.get('visual_tools', {})})
            if not report['passed']:
                raise ValueError('Custom environment enforcement failed.')
            write_json(self.entry['prepared'].output / 'harbor-environment-preflight.json', report)

        async def stop(self, delete):
            # Model command groups are stopped by LocalCodexBackend on failure.
            # Preserve all private evidence; do not delete the workspace.
            return None

        def mapped(self, value):
            value = str(value)
            known = {'/logs/agent': self.trial_paths.agent_dir,
                     '/logs/verifier': self.trial_paths.verifier_dir,
                     '/logs/artifacts': self.trial_paths.artifacts_dir,
                     '/logs': self.trial_paths.trial_dir / 'environment-logs',
                     '/tests': self.trial_paths.trial_dir / 'environment-tests'}
            for prefix in sorted(known, key=len, reverse=True):
                if value == prefix or value.startswith(prefix + '/'):
                    target = known[prefix] / value[len(prefix):].lstrip('/')
                    if not target.resolve().is_relative_to(known[prefix].resolve()):
                        raise ValueError('Environment lifecycle path escapes its private mapping.')
                    return target
            raise ValueError('Unsupported environment lifecycle path: ' + value)

        async def ensure_dirs(self, dirs, chmod=True):
            for path in dirs:
                self.mapped(path).mkdir(mode=0o700, parents=True, exist_ok=True)
            return ExecResult(return_code=0)

        async def empty_dirs(self, dirs, chmod=True):
            for path in dirs:
                target = self.mapped(path)
                if target.exists():
                    for child in target.iterdir():
                        if child.is_dir() and not child.is_symlink():
                            shutil.rmtree(child)
                        else:
                            child.unlink()
                target.mkdir(mode=0o700, parents=True, exist_ok=True)
            return ExecResult(return_code=0)

        async def reset_dirs(self, *, remove_dirs, create_dirs, chmod_dirs=None):
            await self.empty_dirs(remove_dirs)
            await self.ensure_dirs(create_dirs)
            return ExecResult(return_code=0)

        async def exec(self, command, cwd=None, env=None, timeout_sec=None, user=None):
            prepared = self.entry['prepared']
            if env or user not in {None, 'root'}:
                raise ValueError('Custom environment variable/user overrides are unsupported.')
            target = Path(cwd).resolve() if cwd else prepared.workspace
            if not target.is_relative_to(prepared.workspace):
                raise ValueError('Commands cannot execute outside the solver workspace.')
            executable, package = legacy().core.runtime()
            args = [executable, 'sandbox', '-P', legacy().core.PROFILE, '-C', str(prepared.workspace),
                    *legacy().core.config_args(package, renderer=Path(prepared.spec['renderer']), readonly_inputs=True),
                    '/bin/sh', '-c', command]
            completed = await asyncio.to_thread(subprocess.run, args, cwd=target, env=legacy().core.host_env(),
                                                capture_output=True, text=True, timeout=timeout_sec or 20)
            return ExecResult(stdout=completed.stdout, stderr=completed.stderr, return_code=completed.returncode)

        async def upload_file(self, source_path, target_path):
            raise ValueError('Generic host file uploads are unsupported; explicit images use the frozen input stager.')

        async def upload_dir(self, source_dir, target_dir):
            source = Path(source_dir)
            if str(target_dir) in {'/logs/agent', '/logs/verifier', '/logs/artifacts'} and source.resolve() == self.mapped(target_dir).resolve():
                if source.is_symlink() or any(path.is_symlink() or (path.is_file() and path.stat().st_nlink != 1) for path in source.rglob('*')):
                    raise ValueError('Private log mappings cannot contain linked files.')
                # Framework and environment share this exact private log path.
                # This is a no-op, not a generic host input upload.
                return
            if not any(Path(source_dir).iterdir()):
                return
            raise ValueError('Generic host directory uploads are unsupported.')

        async def download_file(self, source_path, target_path):
            source = self.mapped(source_path)
            target = Path(target_path).resolve()
            if not target.is_relative_to(self.trial_paths.trial_dir.resolve()) or source.is_symlink():
                raise ValueError('Log transfer is outside the private trial.')
            if source.resolve() != target:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)

        async def download_dir(self, source_dir, target_dir):
            source, target = self.mapped(source_dir), Path(target_dir).resolve()
            if not target.is_relative_to(self.trial_paths.trial_dir.resolve()):
                raise ValueError('Log transfer is outside the private trial.')
            if source.resolve() != target and source.exists():
                if any(path.is_symlink() for path in source.rglob('*')):
                    raise ValueError('Log transfer cannot follow symbolic links.')
                shutil.copytree(source, target, dirs_exist_ok=True)

    class HarborCodexAgent(BaseAgent):
        capabilities = AgentCapabilities(resume=True)

        def __init__(self, *args, session_key, **kwargs):
            self.entry = _TRIALS[session_key]
            super().__init__(*args, **kwargs)

        @staticmethod
        def name():
            return 'maintainall-codex-host-auth'

        def version(self):
            return legacy().core.CLI_VERSION

        async def setup(self, environment):
            if not isinstance(environment, HarborCodexEnvironment):
                raise ValueError('The host-authenticated agent requires its verified custom environment.')

        async def run(self, instruction, environment, context):
            await self.one_turn(instruction, environment, context, first=True)

        async def resume(self, instruction, environment, context):
            await self.one_turn(instruction, environment, context, first=False)

        async def one_turn(self, instruction, environment, context, first):
            prepared = self.entry['prepared']
            previous = prepared.state.get('result', {}).get('turns', [])
            index = len(previous)
            if first != (index == 0) or index >= len(prepared.prompts) or instruction != prepared.prompts[index]:
                raise ValueError('Harbor step order or prompt differs from the frozen real-turn contract.')
            # The maintained official sandbox executes generated commands.
            # This trusted agent never uploads auth.json into the environment.
            result = await asyncio.to_thread(self.entry['local'].execute, prepared, self.entry['emit'], index + 1)
            if result['status'] != 'completed' or len(result['turns']) != index + 1:
                raise RuntimeError(result['failure_reason'] or 'Backend turn failed.')
            row = result['turns'][-1]
            context.n_input_tokens = row['usage']['input_tokens']
            context.n_cache_tokens = row['usage']['cached_input_tokens']
            context.n_output_tokens = row['usage']['output_tokens']
            context.cost_usd = None
            self.logs_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
            write_json(self.logs_dir / ('backend-turn-' + str(index + 1) + '.json'), row)

    globals()['HarborCodexEnvironment'] = HarborCodexEnvironment
    globals()['HarborCodexAgent'] = HarborCodexAgent


class HarborBackend(Backend):
    id = 'harbor'
    capabilities = {**LocalCodexBackend.capabilities, 'native_harbor': True}

    def fingerprint(self):
        identity = {'source_sha': SOURCE_SHA, 'source_version': VERSION, 'adapter': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    'base': hashlib.sha256(Path(__file__).with_name('base.py').read_bytes()).hexdigest(),
                    'local': LocalCodexBackend().fingerprint(), 'runtime': runtime_identity()}
        return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()

    def doctor(self, config):
        try:
            provenance = runtime_check(config)
            integrations()
            local = LocalCodexBackend().doctor(config)
            return {**local, 'backend': {'id': self.id, 'fingerprint': self.fingerprint()},
                    'capabilities': {**local['capabilities'], 'native_harbor': True}, 'harbor': provenance,
                    'runtime': runtime_identity(),
                    'model_compatibility': 'unverified_until_root_schedules_real_three_call_smoke'}
        except (ValueError, ImportError) as error:
            return {'passed': False, 'model_called': False, 'backend': {'id': self.id, 'fingerprint': self.fingerprint()},
                    'capabilities': {**self.capabilities, 'browser_capture': False, 'playable_motion': False,
                                     'action_trace_capture': False, 'web_audio_probe': False,
                                     'blender': False, 'native_scene_reopen': False},
                    'failure_reason': str(error), 'model_compatibility': 'unsupported'}

    def prepare(self, spec, output):
        runtime_check(spec.get('backend_config', {}))
        integrations()
        return LocalCodexBackend().prepare(spec, output)

    def execute(self, prepared, emit):
        from harbor.job import Job
        from harbor.models.job.config import JobConfig
        from harbor.models.trial.config import AgentConfig, EnvironmentConfig, TaskConfig, VerifierConfig
        key = uuid.uuid4().hex
        _TRIALS[key] = {'prepared': prepared, 'emit': emit, 'local': LocalCodexBackend()}
        task = prepared.output / 'harbor-task'
        task.mkdir()
        (task / 'environment').mkdir()
        config_lines = ['schema_version = "1.4"', '[environment]', 'network_mode = "no-network"', '[agent]',
                        'timeout_sec = ' + str(prepared.spec['limits']['turn_seconds'] + 30)]
        for index, turn in enumerate(prepared.spec['case']['turns']):
            config_lines.extend(['[[steps]]', 'name = ' + json.dumps(turn['id']), '[steps.agent]',
                                 'timeout_sec = ' + str(prepared.spec['limits']['turn_seconds'] + 30)])
            directory = task / 'steps' / turn['id']
            directory.mkdir(parents=True)
            (directory / 'instruction.md').write_text(prepared.prompts[index])
        (task / 'task.toml').write_text('\n'.join(config_lines) + '\n')
        config = JobConfig(job_name='native', jobs_dir=prepared.output / 'harbor-jobs', tasks=[TaskConfig(path=task)],
                           agents=[AgentConfig(import_path='skill_bench.backends.harbor:HarborCodexAgent', model_name=prepared.spec['model'],
                                               resume_trajectory=True, kwargs={'session_key': key})],
                           environment=EnvironmentConfig(import_path='skill_bench.backends.harbor:HarborCodexEnvironment', kwargs={'session_key': key}),
                           verifier=VerifierConfig(disable=True), n_attempts=1, n_concurrent_trials=1, retry={'max_retries': 0}, quiet=True)
        write_json(prepared.output / 'harbor-job-config.json', config.model_dump(mode='json'))
        async def run_job():
            job = await Job.create(config)
            return await job.run()
        previous_telemetry = os.environ.get('HARBOR_TELEMETRY')
        os.environ['HARBOR_TELEMETRY'] = '0'
        try:
            native_result = asyncio.run(run_job())
            result = prepared.state.get('result', {'trial_id': prepared.spec['trial_id'], 'status': 'failed', 'turns': [], 'failure_reason': 'Harbor stopped before the first model call.'})
            result = {**result, 'backend': {'id': self.id, 'fingerprint': self.fingerprint()},
                      'harbor': {'source_sha': SOURCE_SHA, 'version': VERSION,
                                 'job_id': str(native_result.id), 'job_dir': 'harbor-jobs/native',
                                 'environment': 'public custom Codex Linux profile environment; not the built-in Docker adapter'}}
            if len(result['turns']) != len(prepared.prompts) and result['status'] == 'completed':
                result.update(status='failed', failure_reason='Harbor did not complete every frozen real turn.')
            if result['status'] == 'completed':
                try:
                    validate_native_result(native_result, [turn['id'] for turn in prepared.spec['case']['turns']])
                except ValueError as error:
                    result.update(status='failed', failure_reason=str(error))
            write_json(prepared.output / 'backend-result.json', result)
            return result
        finally:
            _TRIALS.pop(key, None)
            if prepared.state.get('browser_broker'):
                prepared.state['browser_broker'].close()
            if previous_telemetry is None:
                os.environ.pop('HARBOR_TELEMETRY', None)
            else:
                os.environ['HARBOR_TELEMETRY'] = previous_telemetry

    def execute_trial(self, spec, output, emit):
        old_umask = os.umask(0o077)
        prepared = None

        def failed(status, reason):
            prior = prepared.state.get('result', {}) if prepared is not None else {}
            result = {**prior, 'trial_id': spec.get('trial_id'), 'status': status,
                      'turns': prior.get('turns', []),
                      'backend': {'id': self.id, 'fingerprint': self.fingerprint()}, 'failure_reason': reason}
            if prepared is not None:
                write_json(prepared.output / 'backend-result.json', result)
            return result

        try:
            try:
                runtime_check(spec.get('backend_config', {}))
                integrations()
            except (ValueError, ImportError) as error:
                return {'trial_id': spec.get('trial_id'), 'status': 'unsupported', 'turns': [],
                        'backend': {'id': self.id, 'fingerprint': self.fingerprint()}, 'failure_reason': str(error)}
            try:
                prepared = self.prepare(spec, output)
                return self.collect(prepared, self.execute(prepared, emit))
            except KeyboardInterrupt:
                return failed('interrupted', 'Harbor interrupted; no automatic retry.')
            except Exception as error:
                return failed('failed', str(error))
        finally:
            if prepared is not None and prepared.state.get('browser_broker'):
                prepared.state['browser_broker'].close()
            os.umask(old_umask)
