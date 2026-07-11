from pathlib import Path

from MaintainAll.missions.models import Expect
from MaintainAll.tools.validate import evaluate_expect


def test_contains():
    ok, msg = evaluate_expect(
        Expect(type="contains", patterns=["hello"]),
        stdout="say hello",
        report_text="",
        repo_root=Path("."),
    )
    assert ok


def test_file_exists(tmp_path):
    (tmp_path / "r.md").write_text("x")
    ok, _ = evaluate_expect(
        Expect(type="file_exists", path_glob="*.md"),
        stdout="",
        report_text="",
        repo_root=tmp_path,
    )
    assert ok


def test_report_section():
    ok, _ = evaluate_expect(
        Expect(type="report_section", name="Summary"),
        stdout="",
        report_text="# Report\n\n## Summary\n\nDone.",
        repo_root=Path("."),
    )
    assert ok


def test_report_section_case_sensitive():
    ok, msg = evaluate_expect(
        Expect(type="report_section", name="summary"),
        stdout="",
        report_text="## Summary",
        repo_root=Path("."),
    )
    assert not ok
    assert "summary" in msg.lower() or "Summary" in msg


def test_report_section_rejects_mid_line_heading():
    ok, msg = evaluate_expect(
        Expect(type="report_section", name="Summary"),
        stdout="",
        report_text="Notes: ## Summary is not a heading",
        repo_root=Path("."),
    )
    assert not ok
    assert "Summary" in msg
