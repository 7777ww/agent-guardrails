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

## 快速開始

需求：[uv](https://docs.astral.sh/uv/)、`jq`、Claude Code。目前支援 Python 專案；其他語言見「[其他語言](#其他語言gotypescript)」。

### 0. 每台電腦一次：安裝 plugin

```bash
claude plugin marketplace add https://github.com/7777ww/agent-guardrails.git
```

```bash
claude plugin install agent-guardrails@guardrails
```

Plugin 只對 `pyproject.toml` 內有 `[tool.agent-guardrails]` 的專案生效，裝了不會影響其他專案。

### A. 開新專案：用模板直接產生

```bash
uvx copier copy gh:7777ww/agent-guardrails my-project
```

```bash
cd my-project && git init && uv sync && uv run agent-guardrails check
```

產生出來的專案已經包含：

| 內容 | 檔案 |
|---|---|
| 鎖定版本的 guardrails 依賴與 opt-in 標記 | `pyproject.toml` |
| 分層目錄與 import 邊界（entrypoints > adapters > services > domain） | `src/<package>/`、`[tool.importlinter]` |
| CI：規則測試 + 檢查 | `.github/workflows/guardrails.yml` |
| 專案層規則的位置 | `sgconfig.yml`、`rules/`、`rule-tests/` |
| Claude Code 設定：宣告 marketplace 與 plugin | `.claude/settings.json`、`CLAUDE.md` |

在另一台電腦 clone 這個專案後，開啟並信任資料夾，Claude Code 會依 `.claude/settings.json` 提示安裝 plugin。

模板日後更新時，在專案內執行：

```bash
uvx copier update
```

### B. 既有專案：導入

最省事的做法是在 Claude Code 內執行 `/agent-guardrails:adopt-guardrails`：它會先盤點違規數量、跟你確認範圍，再分批清理。

手動導入只要三步：

```bash
uv add --dev "agent-guardrails @ git+https://github.com/7777ww/agent-guardrails.git@v0.2.0"
```

在 `pyproject.toml` 加上 opt-in 標記：

```toml
[tool.agent-guardrails]
enabled = true
```

```bash
uv run agent-guardrails check
```

既有專案第一次跑通常會有大量違規。先看數量再決定清理順序，不要用 `noqa` 一次蓋掉。
需要 import 邊界時，再於 `[tool.importlinter]` 定義 contract；需要 CI 時，複製 `template/.github/workflows/guardrails.yml`。

### 日常指令

```bash
uv run agent-guardrails check            # 整個專案 + import 邊界
uv run agent-guardrails check src/a.py   # 單一檔案
uv run agent-guardrails test-rules       # 專案層規則的測試
```

### 導入後的開發流程

1. **開發中**：Claude 每次編輯 `.py`，plugin 立即檢查；違規訊息直接回給 agent，修到通過才能繼續。
2. **收尾**：你說「可以 push／開 PR／任務完成」時，plugin 提醒 agent 回顧這次犯過的錯，列出可以變成規則的候選。
3. **確認**：你同意後才寫入規則與測試；通用的規則再以 PR 升級到這個 repo。
4. **CI**：同一套 `test-rules` 與 `check`，擋住沒經過 Claude 的修改。

## 從錯誤產生規則（自我改進迴圈）

目標是讓 agent 犯過的錯變成規則，而不是變成 prompt 裡的一句提醒。

```
agent 犯錯並修正 → 你說「可以 push／任務完成」時 hook 請 agent 回顧
      → agent 列出「可以用程式擋下」的候選規則
      → 你確認 → 規則 + 測試寫入專案 → 之後同樣的錯被自動擋下
```

- **觸發**：只在收尾時。你的訊息出現收尾用語（push、開 PR、merge、任務完成、可以交付、收尾…）
  且這個 session 編輯過 opt-in 專案的 Python 檔時才提醒，平常每一輪不會打擾。
  用語可用環境變數 `AGENT_GUARDRAILS_WRAP_UP_PATTERN`（extended regex）覆寫，
  也可以隨時手動執行 `/agent-guardrails:learn-rule`。
- **一律先確認**：hook 只負責提問並列出候選；在你明確同意之前不會建立或修改任何規則檔。
- **兩層**：規則預設先進專案層（專案根目錄的 `rules/` 與 `rule-tests/`），
  確認好用且具通用性後，再以 PR 升級到這個共用 repo。
- **沒有測試的規則不收**：每條專案層規則都要有同 id 的測試檔，至少各一個 `valid` 與 `invalid` 案例。

```bash
uv run agent-guardrails test-rules
```

不適合變成規則的錯誤（邏輯錯誤、誤解需求）應該寫成測試，`learn-rule` 會先做這個判斷。

## 其他語言（Go、TypeScript…）

目前的 CLI、hook 與模板只處理 Python：hook 會略過非 `.py` 檔，`check` 執行的是 Ruff。
其他語言還不能直接導入，但方法相同，可以用該語言的工具組出同樣的三層。以 Go 為例：

| 這個 repo（Python） | Go 的對應工具 |
|---|---|
| Ruff 嚴格設定 | `golangci-lint`（staticcheck、revive、errcheck、gocyclo 等） |
| `TID251` 禁用 API + 自訂訊息 | `golangci-lint` 的 `forbidigo`（禁用函式）與 `depguard`（禁用套件），兩者都能寫說明訊息 |
| 禁止 `noqa` 類的略過註解 | `nolintlint` |
| ast-grep 自訂規則 | 同樣用 ast-grep，規則寫 `language: go`；`rules/` + `rule-tests/` 的結構與測試方式不變 |
| import-linter 分層邊界 | `depguard` 或 `go-arch-lint`；另外 Go 的 `internal/` 目錄由編譯器強制 |
| 單一入口 `agent-guardrails check` | 專案自己的 `make check`（或同等指令），CI 與 hook 都呼叫它 |

要讓 Claude Code 在編輯 Go 檔後自動檢查，在該專案的 `.claude/settings.json` 加一個 PostToolUse hook 呼叫 `make check`，
失敗時以 exit code 2 結束並把輸出寫到 stderr，agent 就會收到錯誤並修正。

把 Go 正式納入這個 repo（語言偵測、Go 規則包、Go 模板）尚未實作。

## 修改規則

1. 改 `src/agent_guardrails/rules/` 下的檔案，錯誤訊息務必寫明「為什麼禁止」與「正確做法」。
2. 在 `tests/test_rules.py` 加上對應的違規案例，執行 `uv run pytest`。
3. 更新 `pyproject.toml` 與 `.claude-plugin/plugin.json` 的版本，打 tag。
4. 各專案把 `guardrails_ref` 改成新 tag（`uvx copier update`），各電腦執行 `claude plugin marketplace update guardrails`。

## 安全注意

- Hook 會以你的使用者權限執行 shell 指令。只從你信任、且有 review 流程的 repo 安裝這個 plugin。
- 專案一律鎖定 tag 或 commit，不要追 branch。
- 若 repo 是 private，CI 需要另外提供唯讀的 deploy key 或 token 才能安裝 dev dependency；不要把 token 寫進 `pyproject.toml`。
