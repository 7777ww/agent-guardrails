"""Tests for the PreToolUse hook that asks for a rule review before git push."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "review-before-push.sh"
BASH = shutil.which("bash")
SESSION = "push-hook-test"

pytestmark = pytest.mark.skipif(
    BASH is None or shutil.which("jq") is None,
    reason="bash and jq are required to run the hook",
)


def _marker(state_root: Path) -> Path:
    return state_root / "agent-guardrails-state" / f"{SESSION}.edited"


def _mark_edited(state_root: Path) -> None:
    marker = _marker(state_root)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()


def _run(command: str, state_root: Path) -> subprocess.CompletedProcess[str]:
    payload = {"session_id": SESSION, "tool_name": "Bash", "tool_input": {"command": command}}
    return subprocess.run(
        [str(BASH), str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin", "TMPDIR": str(state_root)},
    )


@pytest.mark.parametrize(
    "command",
    [
        "git push",
        "git push -u origin feat/x",
        "cd /repo && git push origin main",
        "git -C /repo push",
        "git -c core.sshCommand=ssh push origin main",
        "git commit -m done; git push",
    ],
)
def test_push_is_held_once_after_edits(tmp_path: Path, command: str) -> None:
    _mark_edited(tmp_path)

    first = _run(command, tmp_path)

    assert first.returncode == 0
    decision = json.loads(first.stdout)["hookSpecificOutput"]
    assert decision["hookEventName"] == "PreToolUse"
    assert decision["permissionDecision"] == "deny"
    assert "learn-rule" in decision["permissionDecisionReason"]
    assert not _marker(tmp_path).exists()

    second = _run(command, tmp_path)

    assert second.returncode == 0
    assert second.stdout == ""


def test_push_without_edits_is_not_held(tmp_path: Path) -> None:
    result = _run("git push origin main", tmp_path)

    assert result.returncode == 0
    assert result.stdout == ""


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git commit -m 'prepare push'",
        "git stash push",
        "git push --dry-run",
        "git push origin --delete old-branch",
        "legit push",
        "ls ./git push",
    ],
)
def test_other_commands_pass_and_keep_marker(tmp_path: Path, command: str) -> None:
    _mark_edited(tmp_path)

    result = _run(command, tmp_path)

    assert result.returncode == 0
    assert result.stdout == ""
    assert _marker(tmp_path).exists()
