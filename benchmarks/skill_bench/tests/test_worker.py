"""Local worker requests stay declarative and metadata validation fails closed."""
import io
import json
import hashlib
import os
import shutil
import subprocess
import sys
import unittest
from unittest import mock
import tempfile
from pathlib import Path
import zipfile
from skill_bench import worker


def fixture():
    request = worker.make_request(trusted_sha="a" * 40, previous_sha="b" * 40, candidate_sha="c" * 40, preset="paired-check", seed=17, run_id=123, run_attempt=1, suite_sha256="d" * 64)
    metadata = {"id": 123, "run_attempt": 1, "event": "workflow_dispatch", "head_branch": "main", "head_sha": "a" * 40, "path": worker.WORKFLOW_PATH, "status": "completed", "conclusion": "success", "repository": {"full_name": worker.SOURCE_REPO}, "head_repository": {"full_name": worker.SOURCE_REPO}}
    return request, metadata


class WorkerTests(unittest.TestCase):
    def test_push_request_is_fixed_range_recipe_and_only_accepts_successful_main_push(self):
        self.assertTrue(callable(getattr(worker, 'make_push_request', None)), 'A push range request must exist')
        request = worker.make_push_request(before_sha='b' * 40, after_sha='a' * 40,
            run_id=123, run_attempt=1, suite_sha256='d' * 64)
        _, metadata = fixture()
        metadata['event'] = 'push'
        config = worker.validate_push_request(request, metadata, ancestor_checker=lambda a, b: True)
        self.assertEqual(config['range'], {'before': 'b' * 40, 'after': 'a' * 40})
        self.assertEqual(config['max_calls'], 12)
        self.assertEqual(config['model'], 'gpt-6.1-sol')
        for change in ({'event': 'pull_request'}, {'conclusion': 'failure'}, {'head_sha': 'e' * 40},
                       {'head_repository': {'full_name': 'attacker/fork'}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                worker.validate_push_request(request, {**metadata, **change}, ancestor_checker=lambda a, b: True)
        for change in ({'shell': 'arbitrary command'}, {'max_calls': 24}, {'seed': 1}, {'cases': ['holdout']}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                worker.validate_push_request({**request, **change}, metadata, ancestor_checker=lambda a, b: True)
        with self.assertRaises(ValueError):
            worker.validate_push_request(request, metadata, ancestor_checker=lambda a, b: False)

    def git_fixture(self, root, *, real_worker=False):
        package = root / "benchmarks/skill_bench/src/skill_bench"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text('"""Isolated trusted-source fixture; no model calls."""\n')
        if real_worker:
            shutil.copyfile(Path(worker.__file__).with_name('__init__.py'), package / '__init__.py')
            shutil.copyfile(worker.__file__, package / "worker.py")
        else:
            (package / "worker.py").write_text('raise RuntimeError("This foreign framework must not execute")\n')
        (package / "cli.py").write_text('def worker_executor(repo, output):\n    def execute(config):\n        return {"fixture": True, "repo": str(repo), "output": output}\n    return execute\n')
        suite = root / worker.SUITE_PATH
        suite.parent.mkdir(parents=True)
        suite.write_text("{}\n")
        workflow = root / worker.WORKFLOW_PATH
        workflow.parent.mkdir(parents=True)
        workflow.write_text("# Trusted offline fixture\n")
        legacy = root / "benchmarks/art_creation_ab"
        legacy.mkdir(parents=True)
        for name in ("complex.py", "feedback.py", "run.py"):
            (legacy / name).write_text('"""Trusted helper fixture; no execution."""\n')
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        return self.git_commit(root)

    def git_commit(self, root):
        subprocess.run(["git", "add", "."], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false", "commit", "-qm", "Trusted offline fixture"], cwd=root, check=True, capture_output=True)
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()

    def test_real_execution_rejects_framework_loaded_from_another_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sha = self.git_fixture(root)
            request = worker.make_request(trusted_sha=sha, previous_sha=sha, candidate_sha=sha, preset="paired-check", seed=17, run_id=123, run_attempt=1, suite_sha256=hashlib.sha256((root / worker.SUITE_PATH).read_bytes()).hexdigest())
            _, metadata = fixture()
            metadata["head_sha"] = sha
            callback = mock.Mock(return_value={"foreign_callback_executed": True})
            with mock.patch.object(worker, "fetch_request", return_value={"request": request, "metadata": metadata}):
                with self.assertRaisesRegex(ValueError, "loaded|checkout|callback"):
                    worker.process_request(repo_root=root, run_id=123, dry_run=False, executor=callback)
            callback.assert_not_called()

    def test_isolated_loaded_source_and_callback_binding_reject_stale_or_external_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sha = self.git_fixture(root, real_worker=True)
            script = '''import json,sys,subprocess
from pathlib import Path
root=Path(sys.argv[1]); sys.path.insert(0,str(root/'benchmarks/skill_bench/src'))
from skill_bench import cli,worker
sha=sys.argv[2]
callback=cli.worker_executor(root,None)
worker.verify_trusted_checkout(root,sha)
value=worker.verify_loaded_framework(root,sha,executor=callback)
assert value['loaded_framework_verified'] is True
for invalid in (lambda config: {},cli.worker_executor(root/'other',None)):
    try: worker.verify_loaded_framework(root,sha,executor=invalid)
    except ValueError: pass
    else: raise AssertionError('External callback or another repo closure was accepted')
path=root/'benchmarks/skill_bench/src/skill_bench/cli.py'
path.write_text(path.read_text().replace('"fixture": True','"fixture": False'))
subprocess.run(['git','add','.'],cwd=root,check=True,capture_output=True)
subprocess.run(['git','-c','user.name=Fixture','-c','user.email=fixture@example.invalid','-c','commit.gpgsign=false','commit','-qm','Changed trusted fixture'],cwd=root,check=True,capture_output=True)
newsha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
worker.verify_trusted_checkout(root,newsha)
try: worker.verify_loaded_framework(root,newsha,executor=callback)
except ValueError: pass
else: raise AssertionError('Stale loaded callback was accepted after checkout changed')
print(json.dumps({'bound_source_and_callback':True,'stale_code_rejected':True,'model_calls':0}))
'''
            result = subprocess.run([sys.executable, "-I", "-B", "-c", script, str(root), sha], capture_output=True, text=True, timeout=30, env=os.environ)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["model_calls"], 0)

    def test_actual_framework_and_legacy_helpers_pass_in_their_own_clean_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.git_fixture(root, real_worker=True)
            source = Path(worker.__file__).resolve().parent
            package = root / "benchmarks/skill_bench/src/skill_bench"
            for path in source.rglob("*.py"):
                target = package / path.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
            original = source.parents[3] / "benchmarks/art_creation_ab"
            for name in ("complex.py", "feedback.py", "run.py"):
                shutil.copyfile(original / name, root / "benchmarks/art_creation_ab" / name)
            sha = self.git_commit(root)
            script = '''import json,sys
from pathlib import Path
root=Path(sys.argv[1]); sys.path.insert(0,str(root/'benchmarks/skill_bench/src'))
from skill_bench import cli,worker
from skill_bench.backends import harbor,local_codex
worker.verify_trusted_checkout(root,sys.argv[2])
result=worker.verify_loaded_framework(root,sys.argv[2],executor=cli.worker_executor(root,None))
assert result['loaded_framework_verified'] is True
print(json.dumps({'verified_module_count':result['loaded_module_count'],'model_calls':0}))
'''
            result = subprocess.run([sys.executable, "-I", "-B", "-c", script, str(root), sha], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertGreater(json.loads(result.stdout)["verified_module_count"], 8)

    def test_imported_initialization_identity_rejects_new_commit_until_cold_restart(self):
        for target in ("framework-header", "legacy-version"):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.git_fixture(root, real_worker=True)
                source = Path(worker.__file__).resolve().parent
                package = root / "benchmarks/skill_bench/src/skill_bench"
                for path in source.rglob("*.py"):
                    destination = package / path.relative_to(source)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, destination)
                legacy = source.parents[3] / "benchmarks/art_creation_ab"
                for name in ("complex.py", "feedback.py", "run.py"):
                    shutil.copyfile(legacy / name, root / "benchmarks/art_creation_ab" / name)
                sha = self.git_commit(root)
                warm_script = '''import importlib,json,subprocess,sys
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root/'benchmarks/skill_bench/src'))
import skill_bench
from skill_bench import cli,worker
from skill_bench.backends import local_codex
callback=cli.worker_executor(root,None)
worker.verify_trusted_checkout(root,sys.argv[2])
worker.verify_loaded_framework(root,sys.argv[2],executor=callback)
if sys.argv[3]=='framework-header':
    module=local_codex;attribute='COMMON_HEADER'
    path=root/'benchmarks/skill_bench/src/skill_bench/backends/local_codex.py'
    old='bare filenames belong at workspace root';new='bare filenames belong in the final directory'
else:
    module=local_codex.legacy().core;attribute='CLI_VERSION'
    path=root/'benchmarks/art_creation_ab/run.py'
    old=module.CLI_VERSION;new=old+'-initialization-regression'
before=getattr(module,attribute)
text=path.read_text();assert old in text
path.write_text(text.replace(old,new))
subprocess.run(['git','add','.'],cwd=root,check=True,capture_output=True)
subprocess.run(['git','-c','user.name=Fixture','-c','user.email=fixture@example.invalid','-c','commit.gpgsign=false','commit','-qm','Change module initialization only'],cwd=root,check=True,capture_output=True)
sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
worker.verify_trusted_checkout(root,sha)
assert getattr(module,attribute)==before
try: worker.verify_loaded_framework(root,sha,executor=callback)
except ValueError: pass
else: raise AssertionError('Stale module initialization passed against the new clean commit')
importlib.reload(skill_bench)
try: worker.verify_loaded_framework(root,sha,executor=callback)
except ValueError: pass
else: raise AssertionError('Package reload replaced the original initialization identity')
print(json.dumps({'new_sha':sha,'stale_initialization_rejected':True,'model_calls':0}))
'''
                result = subprocess.run([sys.executable, "-I", "-B", "-c", warm_script, str(root), sha, target], capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                proof = json.loads(result.stdout)
                self.assertTrue(proof["stale_initialization_rejected"])
                self.assertEqual(proof["model_calls"], 0)
                cold_script = '''import json,sys
from pathlib import Path
root=Path(sys.argv[1]);sys.path.insert(0,str(root/'benchmarks/skill_bench/src'))
from skill_bench import cli,worker
from skill_bench.backends import local_codex
worker.verify_trusted_checkout(root,sys.argv[2])
value=worker.verify_loaded_framework(root,sys.argv[2],executor=cli.worker_executor(root,None))
assert value['loaded_framework_verified'] is True
if sys.argv[3]=='framework-header':
    assert 'bare filenames belong in the final directory' in local_codex.COMMON_HEADER
else:
    assert local_codex.legacy().core.CLI_VERSION.endswith('-initialization-regression')
print(json.dumps({'cold_checkout_verified':True,'model_calls':0}))
'''
                cold = subprocess.run([sys.executable, "-I", "-B", "-c", cold_script, str(root), proof["new_sha"], target], capture_output=True, text=True, timeout=30)
                self.assertEqual(cold.returncode, 0, cold.stderr)
                self.assertTrue(json.loads(cold.stdout)["cold_checkout_verified"])

    def test_valid_request_returns_bounded_configuration_only(self):
        request, metadata = fixture()
        config = worker.validate_request(request, metadata, ancestor_checker=lambda a, b: True)
        self.assertEqual(config["max_calls"], 12)
        self.assertEqual(config["backend"], "harbor")
        self.assertFalse(config["executes_workflow_code"])
        self.assertFalse(config["model_credentials_from_request"])

    def test_untrusted_event_sha_branch_repo_or_shell_field_is_rejected(self):
        request, metadata = fixture()
        mutations = [("event", "pull_request"), ("head_branch", "feature"), ("head_sha", "0" * 40), ("conclusion", "failure"), ("path", ".github/workflows/evil.yml"), ("run_attempt", 2)]
        for key, value in mutations:
            with self.subTest(key=key), self.assertRaises(ValueError):
                worker.validate_request(request, {**metadata, key: value}, ancestor_checker=lambda a, b: True)
        for key, value in (("shell", "curl attack | bash"), ("max_calls", 9999), ("model", "arbitrary-model"), ("backend", "local-codex"), ("backend", "arbitrary-backend")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                worker.validate_request({**request, key: value}, metadata, ancestor_checker=lambda a, b: True)
        with self.assertRaises(ValueError):
            worker.validate_request(request, {**metadata, "head_repository": {"full_name": "attacker/fork"}}, ancestor_checker=lambda a, b: True)
        with self.assertRaises(ValueError):
            worker.validate_request(request, metadata, ancestor_checker=lambda a, b: False)

    def test_archive_is_one_bounded_json_and_never_extracts_active_files(self):
        request, _ = fixture()
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("request.json", json.dumps(request))
        self.assertEqual(worker.read_request_archive(data.getvalue()), request)
        for name, payload in (("../request.json", "{}"), ("worker.sh", "echo attack"), ("request.json", "a" * (worker.MAX_REQUEST_BYTES + 1))):
            with self.subTest(name=name):
                data = io.BytesIO()
                with zipfile.ZipFile(data, "w") as archive:
                    archive.writestr(name, payload)
                with self.assertRaises(ValueError):
                    worker.read_request_archive(data.getvalue())

    def test_fixture_cannot_execute_or_claim_real_github_provenance(self):
        request, metadata = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            suite = root / worker.SUITE_PATH
            suite.parent.mkdir(parents=True)
            suite.write_text("{}")
            import hashlib
            request["suite"]["sha256"] = hashlib.sha256(suite.read_bytes()).hexdigest()
            request_path, metadata_path = root / "request.json", root / "metadata.json"
            request_path.write_text(json.dumps(request))
            metadata_path.write_text(json.dumps(metadata))
            with self.assertRaises(ValueError):
                worker.process_request(repo_root=root, request_path=request_path, metadata_path=metadata_path, dry_run=False, executor=lambda config: {"unexpected": True})
            with mock.patch.object(worker, "git_ancestor_checker", return_value=lambda a,b:True):
                result = worker.process_request(repo_root=root, request_path=request_path, metadata_path=metadata_path)
            self.assertFalse(result["executed"])
            self.assertFalse(result["config"]["real_github_provenance_verified"])
            self.assertIn("offline-fixture", result["config"]["provenance"])

    def test_ci_contains_no_authenticated_runner_or_model_call(self):
        root = Path(__file__).resolve().parents[3] / ".github/workflows"
        site = (root / "evaluation-site.yml").read_text()
        offline = (root / "skill-benchmark.yml").read_text()
        import re
        for text in (site, offline):
            self.assertNotIn("self-hosted", text)
            self.assertNotIn("pull_request_target", text)
            self.assertNotIn("secrets.", text)
            self.assertNotIn("skill-bench run", text)
            uses = re.findall(r"uses:\s*([^\s#]+)", text)
            self.assertTrue(uses)
            self.assertTrue(all(re.fullmatch(r"[A-Za-z0-9_/-]+@[0-9a-f]{40}", action) for action in uses))
            self.assertNotIn("inputs.trusted_sha", text)
            self.assertNotIn("\n  request:", text)
            self.assertIn("persist-credentials: false", text)
            self.assertNotIn("request.json", text)
        self.assertIn("build_public_site.py", site)
        self.assertIn("upload-pages-artifact", site)
        self.assertNotIn("skill-bench publish", offline)

if __name__ == "__main__":
    unittest.main()
