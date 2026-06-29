"""Project-root conftest — path injection and test layer auto-marking.

Run tests by layer:
    pytest -m unit                     # Layer 1: fast unit tests
    pytest -m "unit or integration"    # Layer 2: unit + integration
    pytest -m "unit or integration or e2e"  # Layer 3: all tests
    pytest -x                          # --quick: stop on first failure
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent
CLIENT_DIR = ROOT / "client"

# Inject paths at module load (before pytest collection reaches client conftest)
for p in (str(ROOT), str(CLIENT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)


def pytest_configure(config):
    """Register test layer markers."""
    for marker, desc in [
        ("unit", "fast tests with no external dependencies"),
        ("integration", "tests needing mock client or services"),
        ("e2e", "end-to-end tests needing real CUA control plane"),
    ]:
        config.addinivalue_line("markers", f"{marker}: {desc}")


def pytest_collection_modifyitems(config, items):
    """Auto-assign layer markers based on test file name."""
    for item in items:
        path = str(item.fspath)
        if "test_integration" in path:
            item.add_marker(pytest.mark.integration)
        elif "test_e2e" in path:
            item.add_marker(pytest.mark.e2e)
        else:
            item.add_marker(pytest.mark.unit)


# ── Mock client fixture (Layer 2 integration) ──────────────────────

MOCK_PORT = 19110


@pytest.fixture(scope="session")
def mock_client():
    """Start mock client for integration tests."""
    import httpx

    try:
        r = httpx.get(f"http://127.0.0.1:{MOCK_PORT}/health", timeout=2)
        if r.status_code == 200:
            yield f"http://127.0.0.1:{MOCK_PORT}"
            return
    except Exception:
        pass

    mock_script = CLIENT_DIR / "tests" / "mock_client.py"
    proc = subprocess.Popen(
        [sys.executable, str(mock_script), "--port", str(MOCK_PORT)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        cwd=str(CLIENT_DIR / "tests"),
    )

    ready = False
    for _ in range(10):
        time.sleep(1)
        try:
            r = httpx.get(f"http://127.0.0.1:{MOCK_PORT}/health", timeout=2)
            if r.status_code == 200:
                ready = True
                break
        except Exception:
            pass

    if not ready:
        proc.terminate(); proc.wait()
        pytest.fail("Mock client failed to start within 10s")

    yield f"http://127.0.0.1:{MOCK_PORT}"

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


# ── E2E control plane fixture (Layer 3) ────────────────────────────

@pytest.fixture(scope="session")
def e2e_control_plane():
    """Check real control plane is up; skip if not."""
    import json, httpx
    port = int(os.environ.get("CUA_API_PORT", "9111"))

    try:
        r = httpx.get(f"http://127.0.0.1:{port}/health", timeout=3)
    except Exception:
        pytest.skip(f"Control Plane not running on port {port}")
    if r.status_code != 200:
        pytest.skip(f"Control Plane unhealthy on port {port}")

    token = ""
    for cp in (
        Path.home() / ".config" / "cua-control-plane" / "config.json",
        Path(os.environ.get("APPDATA", "")) / "cua-control-plane" / "config.json",
    ):
        if cp.exists():
            token = json.loads(cp.read_text()).get("local_token", "")
            break

    return {"url": f"http://127.0.0.1:{port}", "token": token}
