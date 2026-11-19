"""Single entry point that runs every guardrail with the packaged rules."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

RULES_DIR = Path(__file__).parent / "rules"
RUFF_CONFIG = RULES_DIR / "ruff.toml"
AST_GREP_CONFIG = RULES_DIR / "sgconfig.yml"
PROJECT_AST_GREP_CONFIG = Path("sgconfig.yml")
IMPORT_LINTER_INI = Path(".importlinter")
PYPROJECT = Path("pyproject.toml")
SOURCE_DIR = Path("src")


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
    if PROJECT_AST_GREP_CONFIG.is_file():
        results.append(_run([*ast_grep, *targets]))
    if not paths and _has_import_contracts():
        results.append(_run([_tool("lint-imports")], env=_import_linter_env()))
    return 1 if any(results) else 0


def main(argv: list[str] | None = None) -> int:
    """Run the requested guardrail command and return its exit code."""
    parser = argparse.ArgumentParser(prog="agent-guardrails")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser(
        "check",
        help="檢查指定檔案；不給路徑時檢查整個專案並驗證 import 邊界",
    )
    check.add_argument("paths", nargs="*")
    commands.add_parser("rules-dir", help="印出內建規則目錄的路徑")
    args = parser.parse_args(argv)
    if args.command == "rules-dir":
        sys.stdout.write(f"{RULES_DIR}\n")
        return 0
    return _check(args.paths)
