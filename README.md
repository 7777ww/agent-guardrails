# agent-guardrails

用「會報錯的規則」取代「寫在文件裡的規範」，讓 AI coding agent 在 Python 專案裡只能產出符合架構的程式碼。
這個 repo 同時是三樣東西：

| 層 | 內容 | 位置 |
|---|---|---|
| 1. 共用規則套件 | Python（Ruff）與 Go（golangci-lint）基礎設定、ast-grep 規則、單一入口 CLI `agent-guardrails check` | `src/agent_guardrails/` |
| 2. 專案模板 | copier 模板（Python／Go）：分層目錄、邊界檢查、CI、Claude 設定 | `copier.yml`、`template/python/`、`template/go/` |
| 3. Claude Code plugin | PostToolUse hook：Claude 每次編輯 `.py`／`.go` 就檢查，違規時強制修正 | `.claude-plugin/`、`hooks/`、`skills/` |

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

需求：[uv](https://docs.astral.sh/uv/)、`jq`、Claude Code。支援 Python 與 Go 專案；Go 的差異見「[Go 專案](#go-專案)」。

### 0. 每台電腦一次：安裝 plugin

```bash
claude plugin marketplace add https://github.com/7777ww/agent-guardrails.git
```

```bash
claude plugin install agent-guardrails@guardrails
```

Plugin 只對已 opt-in 的專案生效（`pyproject.toml` 內有 `[tool.agent-guardrails]`，或根目錄有 `.agent-guardrails.toml`），裝了不會影響其他專案。

在 Claude Code 裡說「開新專案」，`/agent-guardrails:new-project` 會替你完成下面 A 的所有步驟。

### A. 開新專案：用模板直接產生

Python：

```bash
uvx copier copy --defaults --data language=python --data project_name=my-project gh:7777ww/agent-guardrails my-project
```

```bash
cd my-project && git init && uv sync && uv run agent-guardrails check
```

Go：

```bash
uvx copier copy --defaults --data language=go --data project_name=my-svc --data go_module=github.com/<owner>/my-svc gh:7777ww/agent-guardrails my-svc
```

```bash
cd my-svc && git init && go build ./... && make check
```

拿掉 `--defaults` 與 `--data` 就會改成互動式詢問。

產生出來的 Python 專案已經包含（Go 專案對應的檔案見「[Go 專案](#go-專案)」）：

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
uv add --dev "agent-guardrails @ git+https://github.com/7777ww/agent-guardrails.git@v0.3.0"
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
需要 import 邊界時，再於 `[tool.importlinter]` 定義 contract；需要 CI 時，複製 `template/python/.github/workflows/guardrails.yml`。

### 日常指令

```bash
uv run agent-guardrails check            # 整個專案 + import 邊界
uv run agent-guardrails check src/a.py   # 單一檔案
uv run agent-guardrails test-rules       # 專案層規則的測試
```

### 導入後的開發流程

1. **開發中**：Claude 每次編輯 `.py`／`.go`，plugin 立即檢查；違規訊息直接回給 agent，修到通過才能繼續。
2. **push 前**：你請 Claude push 時，plugin 先擋下第一次 `git push`，要求 agent 回顧這次修改，把候選規則分成專案層與共用層列給你。
3. **確認**：你同意後才寫入。專案層規則跟這次 push 一起送出；共用層規則同步到這個 repo 並發新版。
4. **CI**：同一套 `test-rules` 與 `check`，擋住沒經過 Claude 的修改。

## 從錯誤產生規則（自我改進迴圈）

目標是讓 agent 犯過的錯變成規則，而不是變成 prompt 裡的一句提醒。

```
agent 犯錯並修正 → 你請 Claude push → hook 擋下第一次 git push，要求回顧
      → agent 檢查這次修改與對話中的糾正，列出「可以用程式擋下」的候選
      → 你確認 → 專案層：規則 + 測試跟這次 push 一起送出
               → 共用層：同步到 agent-guardrails，發新版，之後所有專案都受保護
```

- **觸發**：Claude 執行 `git push` 時（`PreToolUse` hook），而且這個 session 編輯過 opt-in 專案的
  `.py`／`.go` 檔。每批編輯只擋一次，回顧完重新 push 就會通過。全程在本機完成，不需要 CI 或 API key。
  你自己在終端機下的 `git push` 不會觸發；也可以隨時手動執行 `/agent-guardrails:learn-rule`。
- **一律先確認**：hook 只負責提問並列出候選；在你明確同意之前不會建立或修改任何規則檔。
- **兩層**：只適用這個專案的規則進專案層（專案根目錄的 `rules/` 與 `rule-tests/`）；
  任何專案都會犯的錯進共用層（這個 repo），由 agent 開 PR、發 patch 版，再把原專案鎖定的版本升上去。
- **共用層是公開的**：寫入前 agent 會列出將公開的完整內容，並移除專案名稱與業務用語。
- **沒有測試的規則不收**：每條專案層規則都要有同 id 的測試檔，至少各一個 `valid` 與 `invalid` 案例。

```bash
uv run agent-guardrails test-rules
```

不適合變成規則的錯誤（邏輯錯誤、誤解需求）應該寫成測試，`learn-rule` 會先做這個判斷。

## Go 專案

Go 專案使用同一個 CLI、同一個 plugin hook、同一套收尾流程，差別只在底層工具：

| | Python | Go |
|---|---|---|
| opt-in 標記 | `pyproject.toml` 的 `[tool.agent-guardrails]` | 專案根目錄的 `.agent-guardrails.toml`，內容 `language = "go"` |
| 基礎 lint（強制設定，專案無法放寬） | Ruff | golangci-lint（`src/agent_guardrails/rules/go/golangci.yml`） |
| 禁用 API 與套件 | `TID251` | `forbidigo`（`fmt.Print*`、`print`、`println`）、`depguard`（`io/ioutil` 等） |
| 禁止略過註解 | `no-suppression-comments` | `no-suppression-comments`（`//nolint`、`//lint:ignore`、`#nosec`） |
| 註解 | 只允許 docstring | 函式內不可有任何註解（包含 `//go:` 開頭的）；函式外的註解不受限 |
| 分層邊界 | import-linter | go-arch-lint（專案根目錄的 `.go-arch-lint.yml`） |
| 執行方式 | `uv run agent-guardrails check` | `make check`（內部以 `uvx` 執行鎖定版本的 CLI） |

需求：Go 1.26 以上、`uv`、`jq`。golangci-lint 與 go-arch-lint 不需要自己安裝：CLI 第一次執行時會以鎖定的版本
`go install` 到 `~/.cache/agent-guardrails/bin/`（可用 `XDG_CACHE_HOME` 改位置），不會動到你的 `PATH`。
第一次需要網路，耗時十幾秒到數分鐘；Go 升版後會重新安裝一次。

注意事項：

- 專案自己的 `.golangci.yml` 不會被讀取。專案專屬的限制請寫成專案層規則（`rules/`，`language: go`）。
- 指定檔案的 `check` 會檢查該檔所在的整個 package；只看該語言的檔案，其他副檔名會被略過。
- 巢狀 module 會各自檢查。`testdata/`、`vendor/`、以 `_` 或 `.` 開頭的目錄不檢查，與 Go 本身一致。
- `go.mod` 內有 `ignore` 指令時，整個專案的 `check` 會失敗，因為被忽略的目錄仍會被編譯卻不會被檢查。
- 產生檔（`package` 之前有 `// Code generated ... DO NOT EDIT.`）不檢查。Claude 編輯這種檔案時 hook 會拒絕，
  要求改用產生器；手寫程式不可帶這個標頭。人手動加上標頭仍可略過檢查，請在 code review 把關。
- Hook 在 Go 專案優先使用 plugin 內附的 CLI 版本，`make check` 與 CI 使用 `Makefile` 鎖定的版本；升級時兩邊一起更新。
- 既有 Go 專案手動導入：加上 `.agent-guardrails.toml`，再參考 `template/go/` 的 `Makefile.jinja`（把 `{{ ... }}` 換成實際的 repo URL 與 tag）、`sgconfig.yml` 與 CI workflow。

## 其他語言

TypeScript 等其他語言尚未支援。

## 修改規則

1. 改 `src/agent_guardrails/rules/` 下的檔案（Go 規則在 `rules/go/`），錯誤訊息務必寫明「為什麼禁止」與「正確做法」。
2. 在 `tests/test_rules.py`（Go：`tests/test_go_rules.py`）加上對應的違規案例，執行 `uv run pytest`。
3. 更新 `pyproject.toml` 與 `.claude-plugin/plugin.json` 的版本，打 tag。
4. 各專案把 `guardrails_ref` 改成新 tag（`uvx copier update`），各電腦執行 `claude plugin marketplace update guardrails`。

## 安全注意

- Hook 會以你的使用者權限執行 shell 指令。只從你信任、且有 review 流程的 repo 安裝這個 plugin。
- 專案一律鎖定 tag 或 commit，不要追 branch。
- Python 專案的 hook 會優先執行專案內的 `.venv/bin/agent-guardrails`。開啟不是你自己建立的 repo 前，先確認 `.venv` 沒有被 commit 進去。
- Go 的檢查工具以鎖定版本 `go install` 取得，並由 Go checksum database 驗證；不要為了加速而關閉 `GOSUMDB`。
- 若 repo 是 private，CI 需要另外提供唯讀的 deploy key 或 token 才能安裝 dev dependency；不要把 token 寫進 `pyproject.toml`。
