---
name: new-project
description: 用 agent-guardrails 模板建立新專案（Python 或 Go），產生後直接可檢查、可開發。當使用者說「開新專案」、「建立新專案」、「new project」、「起一個新的 repo／服務」，或要你在空資料夾開始寫 Python／Go 程式時使用。不需要使用者自己下指令。
---

# 用模板建立新專案

目標：使用者只說要做什麼，你把專案建好並確認 guardrails 已生效。不要把指令丟回去請使用者執行。

## 1. 決定輸入（能推斷就不要問）

| 輸入 | 取得方式 |
|---|---|
| 語言 | 從使用者的話或需求推斷（`python`／`go`）。無法判斷才問，一次問完。 |
| 專案名稱 | kebab-case。使用者沒給就依用途提一個，並在回報時說明。 |
| 位置 | 使用者指定的資料夾；沒指定就用目前工作目錄下的 `<專案名稱>/`。 |
| Go module | 只有 Go 需要。沒給就用 `github.com/<git 使用者或組織>/<專案名稱>`（擁有者可從 `gh api user` 或既有 remote 得知），無法得知時才問。不要留用模板預設的 `example.com/...`。 |

目標資料夾已存在且非空時，停下來說明，不要覆蓋。那種情況改用 `agent-guardrails:adopt-guardrails`。

## 2. 產生專案

需要 `uv`；Go 專案另外需要 `go`。缺少時回報缺什麼與官方安裝方式，不要改用其他方法硬做。

Python：

```bash
uvx copier copy --defaults \
  --data language=python \
  --data project_name=<name> \
  gh:7777ww/agent-guardrails <dir>
```

Go：

```bash
uvx copier copy --defaults \
  --data language=go \
  --data project_name=<name> \
  --data go_module=<module> \
  gh:7777ww/agent-guardrails <dir>
```

模板預設鎖定一個已發佈的 tag。不要把 `guardrails_ref` 改成 branch 名稱。

## 3. 初始化並驗證

在新專案內：

```bash
git init
```

Python：

```bash
uv sync && uv run agent-guardrails test-rules && uv run agent-guardrails check
```

Go：

```bash
go build ./... && make test-rules && make check
```

Go 專案第一次執行 `make check` 會下載並編譯檢查工具，需要幾分鐘，之後會使用快取。

檢查沒通過時，照錯誤訊息修到通過；不要放寬規則或加略過註解。

## 4. 回報

用幾行說明：專案位置、語言、採用的 guardrails 版本、驗證指令與結果、你替使用者決定了哪些預設值。

不要自動建立遠端 repository、不要 push、不要做第一個 commit，除非使用者要求。

之後的開發流程由 plugin 接手：編輯時即時檢查，push 前提出可新增的規則。
