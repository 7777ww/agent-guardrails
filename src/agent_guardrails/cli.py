"""Single entry point that runs every guardrail with the packaged rules."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

RULES_DIR = Path(__file__).parent / "rules"
RUFF_CONFIG = RULES_DIR / "ruff.toml"
AST_GREP_CONFIG = RULES_DIR / "sgconfig.yml"
PROJECT_AST_GREP_CONFIG = Path("sgconfig.yml")
PROJECT_RULES_DIR = Path("rules")
PROJECT_RULE_TESTS_DIR = Path("rule-tests")
IMPORT_LINTER_INI = Path(".importlinter")
PYPROJECT = Path("pyproject.toml")
SOURCE_DIR = Path("src")
RULE_ID = re.compile(r"^id:\s*(\S+)\s*$", re.MULTILINE)


def _tool(name: str) -> str:
    bundled = Path(sysconfig.get_path("scripts")) / name
    if bundled.exists():
        return str(bundled)
    found = shutil.which(name)
    if found is None:
        message = f"agent-guardrails: 找不到 {name}，請重新安裝 agent-guardrails"
        raise SystemExit(message)
    return found


def _run(command: list[str], env: dict[str, str] | None = None) -> int:
    return subprocess.run(command, check=False, env=env).returncode


def _rule_ids(directory: Path) -> set[str]:
    return {
        match.group(1)
        for path in sorted(directory.glob("*.yml"))
        for match in RULE_ID.finditer(path.read_text(encoding="utf-8"))
    }


def _has_project_rules() -> bool:
    return PROJECT_AST_GREP_CONFIG.is_file() and bool(_rule_ids(PROJECT_RULES_DIR))


def _has_import_contracts() -> bool:
    if IMPORT_LINTER_INI.is_file():
        return True
    if not PYPROJECT.is_file():
        return False
    return "[tool.importlinter]" in PYPROJECT.read_text(encoding="utf-8")


def _import_linter_env() -> dict[str, str]:
    env = dict(os.environ)
    if SOURCE_DIR.is_dir():
        existing = env.get("PYTHONPATH")
        parts = [str(SOURCE_DIR.resolve()), *([existing] if existing else [])]
        env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def _check(paths: list[str]) -> int:
    targets = paths or ["."]
    ruff = [_tool("ruff"), "check", "--config", str(RUFF_CONFIG), "--force-exclude"]
    ast_grep = [_tool("ast-grep"), "scan"]
    results = [
        _run([*ruff, *targets]),
        _run([*ast_grep, "--config", str(AST_GREP_CONFIG), *targets]),
    ]
    if _has_project_rules():
        results.append(_run([*ast_grep, *targets]))
    if not paths and _has_import_contracts():
        results.append(_run([_tool("lint-imports")], env=_import_linter_env()))
    return 1 if any(results) else 0


def _test_rules() -> int:
    if not PROJECT_AST_GREP_CONFIG.is_file():
        sys.stderr.write("agent-guardrails: 找不到 sgconfig.yml，這個專案沒有專案層規則。\n")
        return 0
    rules = _rule_ids(PROJECT_RULES_DIR)
    untested = sorted(rules - _rule_ids(PROJECT_RULE_TESTS_DIR))
    if untested:
        listing = "、".join(untested)
        sys.stderr.write(
            f"agent-guardrails: 以下規則沒有測試：{listing}\n"
            f"請在 {PROJECT_RULE_TESTS_DIR}/ 為每條規則新增同 id 的測試檔，"
            "至少各一個 valid 與 invalid 案例。\n"
        )
        return 1
    if not rules:
        return 0
    return _run([_tool("ast-grep"), "test", "--skip-snapshot-tests"])


def main(argv: list[str] | None = None) -> int:
    """Run the requested guardrail command and return its exit code."""
    parser = argparse.ArgumentParser(prog="agent-guardrails")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser(
        "check",
        help="檢查指定檔案；不給路徑時檢查整個專案並驗證 import 邊界",
    )
    check.add_argument("paths", nargs="*")
    commands.add_parser("test-rules", help="驗證專案層規則：每條都要有測試且測試通過")
    commands.add_parser("rules-dir", help="印出內建規則目錄的路徑")
    args = parser.parse_args(argv)
    if args.command == "rules-dir":
        sys.stdout.write(f"{RULES_DIR}\n")
        return 0
    if args.command == "test-rules":
        return _test_rules()
    return _check(args.paths)
