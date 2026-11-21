"""Single entry point that runs every guardrail with the packaged rules."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

RULES_DIR = Path(__file__).parent / "rules"
RUFF_CONFIG = RULES_DIR / "ruff.toml"
AST_GREP_CONFIG = RULES_DIR / "sgconfig.yml"
GO_RULES_DIR = RULES_DIR / "go"
GOLANGCI_CONFIG = GO_RULES_DIR / "golangci.yml"
GO_AST_GREP_CONFIG = GO_RULES_DIR / "sgconfig.yml"
PROJECT_AST_GREP_CONFIG = Path("sgconfig.yml")
PROJECT_RULES_DIR = Path("rules")
PROJECT_RULE_TESTS_DIR = Path("rule-tests")
PROJECT_MARKER = Path(".agent-guardrails.toml")
IMPORT_LINTER_INI = Path(".importlinter")
GO_ARCH_LINT_CONFIG = Path(".go-arch-lint.yml")
GO_MOD = "go.mod"
PYPROJECT = Path("pyproject.toml")
SOURCE_DIR = Path("src")
RULE_ID = re.compile(r"^id:\s*(\S+)\s*$", re.MULTILINE)
TOML_TABLE_HEADER = re.compile(r"^\s*\[", re.MULTILINE)
LANGUAGE_SETTING = re.compile(r"""^\s*language\s*=\s*["']([^"']*)["']""", re.MULTILINE)
UNSAFE_PATH_CHARACTERS = re.compile(r"[^A-Za-z0-9._-]")
DEFAULT_LANGUAGE = "python"
EXECUTABLE_SUFFIX = ".exe" if sys.platform == "win32" else ""
PYTHON_SUFFIXES = frozenset({".py", ".pyi", ".ipynb"})
GO_SUFFIXES = frozenset({".go"})
GO_AST_GREP_SKIPPED_DIRS = frozenset({"testdata", "vendor"})
GO_AST_GREP_EXCLUDES = ["--globs", "!**/testdata/**", "--globs", "!**/vendor/**"]


@dataclass(frozen=True)
class GoTool:
    """A Go command-line tool pinned to an exact module version.

    `minimum_go` is the `go` directive of the tool's own go.mod at that version.
    """

    name: str
    module: str
    version: str
    minimum_go: str


GOLANGCI_LINT = GoTool(
    "golangci-lint",
    "github.com/golangci/golangci-lint/v2/cmd/golangci-lint",
    "v2.15.0",
    "1.26.0",
)
GO_ARCH_LINT = GoTool("go-arch-lint", "github.com/fe3dback/go-arch-lint", "v1.19.2", "1.26.0")
GO_TOOLS = (GOLANGCI_LINT, GO_ARCH_LINT)


@dataclass(frozen=True)
class LanguageSupport:
    """The checks a language runs on given paths, and on the whole project."""

    file_checks: Callable[[list[str]], list[int]]
    project_checks: Callable[[], list[int]]


def _tool(name: str) -> str:
    bundled = Path(sysconfig.get_path("scripts")) / name
    if bundled.exists():
        return str(bundled)
    found = shutil.which(name)
    if found is None:
        message = f"agent-guardrails: 找不到 {name}，請重新安裝 agent-guardrails"
        raise SystemExit(message)
    return found


def _run(
    command: list[str], env: dict[str, str] | None = None, cwd: Path | None = None
) -> int:
    return subprocess.run(command, check=False, env=env, cwd=cwd).returncode


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


def _select_targets(paths: list[str], suffixes: frozenset[str]) -> list[str]:
    if not paths:
        return ["."]
    return [raw for raw in paths if Path(raw).is_dir() or Path(raw).suffix in suffixes]


def _python_file_checks(paths: list[str]) -> list[int]:
    targets = _select_targets(paths, PYTHON_SUFFIXES)
    if not targets:
        return []
    ruff = [_tool("ruff"), "check", "--config", str(RUFF_CONFIG), "--force-exclude"]
    return [
        _run([*ruff, *targets]),
        _run([_tool("ast-grep"), "scan", "--config", str(AST_GREP_CONFIG), *targets]),
    ]


def _python_project_checks() -> list[int]:
    if not _has_import_contracts():
        return []
    return [_run([_tool("lint-imports")], env=_import_linter_env())]


def _go_executable() -> str:
    found = shutil.which("go")
    if found is None:
        message = (
            "agent-guardrails: 找不到 go 指令。Go 專案的檢查需要 Go toolchain 來安裝與執行 "
            "golangci-lint，請安裝 Go（https://go.dev/dl/）並確認 go 在 PATH 上。"
        )
        raise SystemExit(message)
    return found


def _go_env(go: str, *names: str) -> list[str]:
    result = subprocess.run([go, "env", *names], capture_output=True, text=True, check=False)
    values = result.stdout.splitlines()
    if result.returncode != 0 or len(values) != len(names) or not all(values):
        message = f"agent-guardrails: 無法執行 go env {' '.join(names)}：{result.stderr.strip()}"
        raise SystemExit(message)
    return values


def _tool_cache_root() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "agent-guardrails" / "bin"


def _go_install_env(go: str, staging: Path) -> dict[str, str]:
    host_os, host_arch = _go_env(go, "GOHOSTOS", "GOHOSTARCH")
    return {
        **os.environ,
        "GOBIN": str(staging),
        "GOFLAGS": "",
        "GOWORK": "off",
        "GOOS": host_os,
        "GOARCH": host_arch,
    }


def _install_failure(tool: GoTool, result: subprocess.CompletedProcess[str]) -> str:
    return (
        f"agent-guardrails: 安裝 {tool.name} {tool.version} 失敗"
        f"（go install exit {result.returncode}）。{tool.name} {tool.version} 需要 "
        f"Go >= {tool.minimum_go}。go install 的輸出如下：\n{result.stderr.strip()}"
    )


def _install_go_tool(go: str, tool: GoTool, binary: Path) -> None:
    binary.parent.mkdir(parents=True, exist_ok=True)
    sys.stderr.write(
        f"agent-guardrails: 第一次使用 {tool.name} {tool.version}，正在以 go install "
        f"安裝到 {binary.parent}（只需一次，可能需要一分鐘以上）\n"
    )
    staging = Path(tempfile.mkdtemp(prefix=".install-", dir=binary.parent))
    try:
        result = subprocess.run(
            [go, "install", f"{tool.module}@{tool.version}"],
            env=_go_install_env(go, staging),
            capture_output=True,
            text=True,
            check=False,
        )
        built = staging / binary.name
        if result.returncode != 0 or not built.is_file():
            raise SystemExit(_install_failure(tool, result))
        built.replace(binary)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _go_tool(tool: GoTool) -> str:
    go = _go_executable()
    (go_version,) = _go_env(go, "GOVERSION")
    label = UNSAFE_PATH_CHARACTERS.sub("_", go_version)
    directory = _tool_cache_root() / f"{tool.name}-{tool.version}-{label}"
    binary = directory / f"{tool.name}{EXECUTABLE_SUFFIX}"
    if not binary.is_file():
        _install_go_tool(go, tool, binary)
    return str(binary)


def _go_ignores(part: str) -> bool:
    return part in GO_AST_GREP_SKIPPED_DIRS or part.startswith(("_", "."))


def _project_relative(raw: str) -> Path | None:
    try:
        return Path(raw).resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        return None


def _nearest_module(directory: Path) -> Path | None:
    for candidate in (directory, *directory.parents):
        if (candidate / GO_MOD).is_file():
            return candidate
    return None


def _go_package(raw: str) -> tuple[Path, str] | None:
    relative = _project_relative(raw)
    if relative is None or any(_go_ignores(part) for part in relative.parts):
        return None
    is_dir = Path(raw).is_dir()
    if not is_dir and relative.suffix not in GO_SUFFIXES:
        return None
    package_dir = relative if is_dir else relative.parent
    module = _nearest_module(package_dir)
    if module is None:
        return None
    pattern = "./" + package_dir.relative_to(module).as_posix()
    return module, f"{pattern}/..." if is_dir else pattern


def _go_modules() -> list[Path]:
    modules = []
    for current, directories, files in os.walk("."):
        directories[:] = sorted(name for name in directories if not _go_ignores(name))
        if GO_MOD in files:
            modules.append(Path(current))
    return modules


def _golangci_targets(paths: list[str]) -> dict[Path, list[str]]:
    if not paths:
        return {module: ["./..."] for module in _go_modules()}
    targets: dict[Path, dict[str, None]] = {}
    for raw in paths:
        package = _go_package(raw)
        if package is not None:
            targets.setdefault(package[0], {})[package[1]] = None
    return {module: list(patterns) for module, patterns in targets.items()}


def _run_golangci(binary: str, module: Path, patterns: list[str]) -> int:
    directory = Path.cwd().resolve() / module
    if module != Path():
        sys.stdout.write(f"golangci-lint（module {module.as_posix()}）:\n")
        sys.stdout.flush()
    command = [binary, "run", "--config", str(GOLANGCI_CONFIG), *patterns]
    return _run(command, env={**os.environ, "PWD": str(directory)}, cwd=directory)


def _go_ast_grep_targets(paths: list[str]) -> list[str]:
    return [
        raw
        for raw in _select_targets(paths, GO_SUFFIXES)
        if not GO_AST_GREP_SKIPPED_DIRS.intersection((_project_relative(raw) or Path(raw)).parts)
    ]


def _go_file_checks(paths: list[str]) -> list[int]:
    results = []
    golangci_targets = _golangci_targets(paths)
    if golangci_targets:
        binary = _go_tool(GOLANGCI_LINT)
        results.extend(
            _run_golangci(binary, module, patterns)
            for module, patterns in golangci_targets.items()
        )
    targets = _go_ast_grep_targets(paths)
    if targets:
        ast_grep = [_tool("ast-grep"), "scan", "--config", str(GO_AST_GREP_CONFIG)]
        results.append(_run([*ast_grep, *GO_AST_GREP_EXCLUDES, *targets]))
    return results


def _ignore_directives(go: str, module: Path) -> list[str]:
    result = subprocess.run(
        [go, "mod", "edit", "-json"], cwd=module, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return []
    return [entry["Path"] for entry in json.loads(result.stdout).get("Ignore") or []]


def _report_ignore_directives(modules: Iterable[Path]) -> list[int]:
    go = _go_executable()
    results = []
    for module in modules:
        ignored = _ignore_directives(go, module)
        if ignored:
            listing = "、".join(ignored)
            sys.stderr.write(
                f"agent-guardrails: {(module / GO_MOD).as_posix()} 含有 ignore 指令（{listing}）。"
                "ignore 讓 ./... 略過這些目錄，但其中的程式仍會被編譯，整個專案的檢查因此不完整。\n"
                "修正方式：移除 ignore 指令。不屬於程式的 Go 檔請放進 testdata/，"
                "或放在以 _ 開頭的目錄（Go 不會編譯它們）。\n"
            )
            results.append(1)
    return results


def _go_project_checks() -> list[int]:
    results = _report_ignore_directives(_go_modules())
    if GO_ARCH_LINT_CONFIG.is_file():
        results.append(_run([_go_tool(GO_ARCH_LINT), "check", "--output-color=false"]))
    return results


LANGUAGES: dict[str, LanguageSupport] = {
    "python": LanguageSupport(_python_file_checks, _python_project_checks),
    "go": LanguageSupport(_go_file_checks, _go_project_checks),
}


def _project_language() -> str:
    if not PROJECT_MARKER.is_file():
        return DEFAULT_LANGUAGE
    text = PROJECT_MARKER.read_text(encoding="utf-8")
    first_table = TOML_TABLE_HEADER.search(text)
    top_level = text[: first_table.start()] if first_table else text
    setting = LANGUAGE_SETTING.search(top_level)
    return setting.group(1).strip().lower() if setting else DEFAULT_LANGUAGE


def _language_support() -> LanguageSupport:
    language = _project_language()
    support = LANGUAGES.get(language)
    if support is None:
        supported = "、".join(sorted(LANGUAGES))
        message = (
            f"agent-guardrails: {PROJECT_MARKER} 指定了不支援的 language = {language!r}。"
            f"目前支援：{supported}。"
        )
        raise SystemExit(message)
    return support


def _check(paths: list[str]) -> int:
    support = _language_support()
    results = support.file_checks(paths)
    if _has_project_rules():
        results.append(_run([_tool("ast-grep"), "scan", *(paths or ["."])]))
    if not paths:
        results.extend(support.project_checks())
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
        help="檢查指定檔案；不給路徑時檢查整個專案並驗證 import／套件邊界",
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
