# agent-guardrails

用「會報錯的規則」取代「寫在文件裡的規範」，讓 AI coding agent 在 Python 專案裡只能產出符合架構的程式碼。
這個 repo 同時是三樣東西：

| 層 | 內容 | 位置 |
|---|---|---|
| 1. 共用規則套件 | Ruff 基礎設定、ast-grep 規則、單一入口 CLI `agent-guardrails check` | `src/agent_guardrails/` |
| 2. 專案模板 | copier 模板：分層目錄、import-linter contract、CI、Claude 設定 | `copier.yml`、`template/` |
| 3. Claude Code plugin | PostToolUse hook：Claude 每次編輯 `.py` 就檢查，違規時強制修正 | `.claude-plugin/`、`hooks/`、`skills/` |

## 規則

| 規則 | 工具 | 作用 |
|---|---|---|
| `no-comments` | ast-grep | 禁止註解（docstring 與 shebang 除外） |
| `no-suppression-comments` | ast-grep | 禁止 `noqa` / `type: ignore` / `pragma: no cover` |
| `no-optional-import-fallback` | ast-grep | 禁止 `try/except ImportError` fallback |
| `TID251` banned-api | Ruff | 禁用 `os.system`、`os.popen`、`typing.cast`、`pickle`，附替代方案 |
| 其餘 | Ruff | 見 `src/agent_guardrails/rules/ruff.toml` |
| 分層邊界 | import-linter | 各專案在 `pyproject.toml` 的 `[tool.importlinter]` 定義 |

Ruff 設定以 `--config` 強制套用，專案的 `pyproject.toml` 無法放寬。
專案專屬的禁用規則請放在專案根目錄的 `sgconfig.yml`，CLI 會一併執行。

## 使用

### 檢查

```bash
uv run agent-guardrails check            # 整個專案 + import 邊界
uv run agent-guardrails check src/a.py   # 單一檔案
```

### 新專案（copier）

```bash
uvx copier copy <this-repo-git-url> my-project
```

之後模板更新時，在專案內執行：

```bash
uvx copier update
```

### 既有專案

在 Claude Code 內執行 `/agent-guardrails:adopt-guardrails`，會先盤點違規再分批導入。
Hook 只對 `pyproject.toml` 內有 `[tool.agent-guardrails]` 的專案生效，其他專案不受影響。

### 在一台新電腦上安裝 plugin

需求：`uv`、`jq`、Claude Code。

```bash
claude plugin marketplace add <this-repo-git-url>
claude plugin install agent-guardrails@guardrails
```

由模板產生的專案已在 `.claude/settings.json` 宣告這個 marketplace 與 plugin，
在新電腦上開啟專案並信任該資料夾後，Claude Code 會提示安裝。

## 修改規則

1. 改 `src/agent_guardrails/rules/` 下的檔案，錯誤訊息務必寫明「為什麼禁止」與「正確做法」。
2. 在 `tests/test_rules.py` 加上對應的違規案例，執行 `uv run pytest`。
3. 更新 `pyproject.toml` 與 `.claude-plugin/plugin.json` 的版本，打 tag。
4. 各專案把 `guardrails_ref` 改成新 tag（`uvx copier update`），各電腦執行 `claude plugin marketplace update guardrails`。

## 安全注意

- Hook 會以你的使用者權限執行 shell 指令。只從你信任、且有 review 流程的 repo 安裝這個 plugin。
- 專案一律鎖定 tag 或 commit，不要追 branch。
- 若 repo 是 private，CI 需要另外提供唯讀的 deploy key 或 token 才能安裝 dev dependency；不要把 token 寫進 `pyproject.toml`。
