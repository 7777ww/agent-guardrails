"""Each guardrail must reject its violation and accept clean code."""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

CLEAN = (
    '"""Clean module."""\n\n\n'
    "def double(value: int) -> int:\n"
    '    """Return twice the value."""\n'
    "    return value * 2\n"
)

VIOLATIONS = {
    "no-comments": CLEAN + "\n\nLIMIT = 3  # explain the limit\n",
    "no-suppression-comments": CLEAN + "\n\nimport os  # noqa: E402\n",
    "no-optional-import-fallback": (
        '"""Fallback."""\n\ntry:\n    import json\nexcept ImportError:\n    json = None\n'
    ),
    "TID251": '"""Shell."""\n\nimport os\n\nos.system("ls")\n',
    "T201": CLEAN + '\n\nprint("debug")\n',
}


def _check(directory: Path, source: str) -> subprocess.CompletedProcess[str]:
    target = directory / "sample.py"
    target.write_text(source, encoding="utf-8")
    return subprocess.run(
        [sys.executable, "-m", "agent_guardrails", "check", str(target)],
        cwd=directory,
        capture_output=True,
        text=True,
        check=False,
    )


def test_clean_code_passes(tmp_path: Path) -> None:
    result = _check(tmp_path, CLEAN)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("rule_id", sorted(VIOLATIONS))
def test_violation_is_rejected(tmp_path: Path, rule_id: str) -> None:
    result = _check(tmp_path, VIOLATIONS[rule_id])
    assert result.returncode != 0
    assert rule_id in result.stdout + result.stderr
