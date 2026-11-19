---
name: adopt-guardrails
description: 把 agent-guardrails 導入一個既有的 Python 專案（opt-in、盤點違規、分批清理）。當使用者說「導入 guardrails」、「把這個專案套上 guardrails」、「adopt guardrails」時使用。
---

# 導入 agent-guardrails 到既有專案

目標：讓這個專案接受共用 guardrails 的強制檢查，而且不要一次被既有違規淹沒。

## 步驟

1. **先盤點，不要先改**。在專案根目錄執行，並把各規則的違規數量整理給使用者：

   ```bash
   uvx --from "${CLAUDE_PLUGIN_ROOT}" agent-guardrails check
   ```

2. **跟使用者確認修改範圍**：要一次清完，還是先清某些目錄 / 某幾條規則。未確認前不要動程式碼。

3. **清理違規**。每條錯誤訊息都附了修正方式，照做即可。禁止用 `noqa`、`type: ignore`、把註解改成字串等方式繞過。

4. **Opt-in**。違規清到使用者同意的程度後，在 `pyproject.toml` 加上：

   ```toml
   [tool.agent-guardrails]
   enabled = true
   ```

   加上之後，plugin 的 PostToolUse hook 才會開始對這個專案的每次編輯強制檢查。

5. **鎖定版本（建議）**。把 agent-guardrails 加進專案的 dev dependency，CI 與本機就會用同一版規則：

   ```bash
   uv add --dev "agent-guardrails @ git+<repo-url>@<tag>"
   ```

6. **目錄邊界**。和使用者確認分層後，在 `pyproject.toml` 加上 `[tool.importlinter]` contract，之後 `agent-guardrails check`（不帶路徑）會一併驗證。

## 規則不合理時

不要在專案內繞過。停下來告訴使用者是哪條規則、為什麼不合理，由人到 agent-guardrails repo 修改規則並發新版。
