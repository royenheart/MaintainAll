"""Optional local runtimes for browser integration tests."""

import os
from pathlib import Path

CHROME = Path(os.environ.get("SKILL_BENCH_TEST_CHROMIUM", "/nonexistent/skill-bench-chromium"))
