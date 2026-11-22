"""Project-level rules must be tested, and must be enforced by `check`."""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

SGCONFIG = "ruleDirs:\n  - rules\ntestConfigs:\n  - testDir: rule-tests\n"
RULE = (
    "id: no-naive-now\n"
    "language: Python\n"
    "severity: error\n"
    "rule:\n"
    "  pattern: datetime.now()\n"
    "message: naive now is forbidden\n"
)
TEST_HEADER = "id: no-naive-now\n"
RULE_TEST = TEST_HEADER + "valid:\n  - datetime.now(tz=UTC)\ninvalid:\n  - datetime.now()\n"
WRONG_RULE_TEST = TEST_HEADER + "valid:\n  - datetime.now()\ninvalid:\n  - datetime.now(tz=UTC)\n"
VIOLATING_MODULE = (
    '"""Clock."""\n\nfrom datetime import datetime\n\nSTARTED_AT = datetime.now()\n'
)


def _guardrails(directory: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "agent_guardrails", *arguments],
        cwd=directory,
        capture_output=True,
        text=True,
        check=False,
    )


def _project(directory: Path, rule_test: str | None) -> None:
    (directory / "sgconfig.yml").write_text(SGCONFIG, encoding="utf-8")
    (directory / "rules").mkdir()
    (directory / "rule-tests").mkdir()
    (directory / "rules" / "no-naive-now.yml").write_text(RULE, encoding="utf-8")
    if rule_test is not None:
        (directory / "rule-tests" / "no-naive-now.yml").write_text(rule_test, encoding="utf-8")


def test_project_without_rules_passes(tmp_path: Path) -> None:
    assert _guardrails(tmp_path, "test-rules").returncode == 0


def test_empty_rule_directory_passes(tmp_path: Path) -> None:
    (tmp_path / "sgconfig.yml").write_text(SGCONFIG, encoding="utf-8")
    (tmp_path / "rules").mkdir()
    (tmp_path / "rule-tests").mkdir()
    assert _guardrails(tmp_path, "test-rules").returncode == 0
    assert _guardrails(tmp_path, "check").returncode == 0


def test_rule_without_test_is_rejected(tmp_path: Path) -> None:
    _project(tmp_path, rule_test=None)
    result = _guardrails(tmp_path, "test-rules")
    assert result.returncode != 0
    assert "no-naive-now" in result.stderr


def test_rule_with_passing_test_is_accepted(tmp_path: Path) -> None:
    _project(tmp_path, rule_test=RULE_TEST)
    result = _guardrails(tmp_path, "test-rules")
    assert result.returncode == 0, result.stdout + result.stderr


def test_rule_with_failing_test_is_rejected(tmp_path: Path) -> None:
    _project(tmp_path, rule_test=WRONG_RULE_TEST)
    assert _guardrails(tmp_path, "test-rules").returncode != 0


def test_check_enforces_project_rule(tmp_path: Path) -> None:
    _project(tmp_path, rule_test=RULE_TEST)
    (tmp_path / "clock.py").write_text(VIOLATING_MODULE, encoding="utf-8")
    result = _guardrails(tmp_path, "check", "clock.py")
    assert result.returncode != 0
    assert "no-naive-now" in result.stdout + result.stderr
