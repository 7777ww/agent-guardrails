---
name: learn-rule
description: 把 agent 犯過的錯變成一條 guardrails 規則，讓同樣的錯之後被程式自動擋下。在 git push 前（plugin 的 hook 會擋下第一次 push 並要求回顧）檢查這次修改是否有可新增的規則、使用者糾正了一個可以用 lint 偵測的錯誤、或使用者說「把這個變成規則」、「新增 guardrails 規則」、「learn rule」時使用。
---

# 從錯誤產生 guardrails 規則

目標：用「會報錯的規則」取代「寫在 prompt 裡的提醒」。規則一旦建立，agent 就不可能再犯同樣的錯。

**硬性要求：在使用者明確同意之前，不可以建立或修改任何規則檔。** 回顧只產出「候選清單」。

## 一、回顧：找出候選規則

回顧的範圍有兩個：

- 即將 push 的修改：`git diff @{upstream}...HEAD`；分支還沒有 upstream 時，對預設分支比較。
- 這個 session 的對話：使用者糾正過你的地方、你寫了又改掉的地方。

從中找出符合下列全部條件的錯誤：

1. **真的發生過**：被使用者糾正，或你寫了之後自己發現不對而改掉。不要憑空發明「可能會犯」的錯。
2. **看程式碼形狀就能判斷**：用了不該用的 API、特定的寫法、跨層 import。
3. **現有規則沒涵蓋**：先確認 `agent-guardrails check` 目前擋不下它。
4. **錯誤寫法幾乎沒有正當用途**：如果正確與錯誤的用法長得一樣，就不適合。

不適合建規則的情況要直接排除，並在被問到時說明原因：

- 邏輯錯誤、算錯、誤解需求：這些應該變成測試，不是 lint 規則。
- 只是風格偏好，沒有造成實際問題。
- 只發生一次、且高度依賴當下情境。

沒有候選時，只回一行「這次任務沒有適合新增為 guardrails 規則的項目」。

有候選時，把全部候選放在同一份清單、依「專案層」與「共用層」分組，一次問完，然後**停下來等使用者決定**。在使用者回答之前不要 push。每一項說明：

- 發生了什麼錯（一句話）。
- 規則會擋什麼寫法、建議的正確寫法。
- 放在專案層還是共用層（見下），以及理由。
- 預估的誤判風險。

## 二、決定規則放哪一層

| 層 | 位置 | 何時選 | 怎麼送出 |
|---|---|---|---|
| 專案層 | 目前專案的 `rules/` 與 `rule-tests/` | 錯誤與這個專案的架構、命名或慣例有關 | 跟這次 push 一起 commit、一起推 |
| 共用層 | agent-guardrails repo | 換到任何同語言（Python 或 Go）專案都會犯的錯，與業務無關 | 同步更新 agent-guardrails 並發新版（見第四節） |

判斷方式：把規則裡的專案名稱、模組名、業務用語拿掉之後，規則還成立，就是共用層；拿掉就沒有意義，就是專案層。拿不定主意時放專案層。

目前所在的專案就是 agent-guardrails 本身時，只有共用層。

## 三、建立專案層規則（使用者同意後）

1. 專案根目錄若沒有 `sgconfig.yml`，建立：

   ```yaml
   ruleDirs:
     - rules
   testConfigs:
     - testDir: rule-tests
   ```

2. 新增 `rules/<rule-id>.yml`。`message` 寫為什麼禁止，`note` 寫具體的修正方式，因為 agent 是靠這段訊息自我修正：

   ```yaml
   id: no-naive-datetime-now
   language: Python   # Go 專案寫 go
   severity: error
   rule:
     pattern: datetime.now()
   message: 禁止不帶時區的 datetime.now()，跨時區部署時會算錯時間。
   note: |-
     修正方式：改用 datetime.now(tz=UTC)，並從 datetime 匯入 UTC。
   ```

3. 新增 `rule-tests/<rule-id>.yml`，`id` 必須與規則相同，`valid` 與 `invalid` 至少各一個：

   ```yaml
   id: no-naive-datetime-now
   valid:
     - datetime.now(tz=UTC)
   invalid:
     - datetime.now()
   ```

4. 驗證規則本身：

   ```bash
   uv run agent-guardrails test-rules
   ```

5. 對現有程式碼跑一次，統計命中數：

   ```bash
   uv run agent-guardrails check
   ```

6. 向使用者回報：測試結果、現有程式碼命中幾處、其中有沒有誤判。命中處是真的違規就修掉；是誤判就收窄規則，不要用抑制註解處理。

7. 把規則與測試 commit 進同一個分支，然後重新執行原本的 push。Go 專案的指令是 `make test-rules` 與 `make check`。

## 四、同步到共用層（使用者同意後）

共用 repo 是**公開的**。使用者的一次同意要涵蓋「公開的完整內容」與「發佈方式」，所以詢問時要把下面第 2 步的內容一起列出來。

1. 把規則與測試案例寫成通用版本：移除專案名稱、內部模組名、業務用語、客戶名稱、內部網址。
2. 向使用者列出將公開的完整內容（規則檔、測試案例、訊息文字）與發佈方式：開 PR、合併、發一個 patch 版。取得明確同意。使用者只同意開 PR 時，做到開 PR 為止。
3. 找到 agent-guardrails 的本機 clone（常見位置 `~/code/agent-guardrails`；用 `git -C <dir> remote get-url origin` 確認）。找不到就 clone 到使用者同意的位置。工作目錄不乾淨時停下來回報，不要動別人的修改。
4. 從最新的 `main` 開新分支 `rule/<rule-id>`。
5. 新增規則與測試：
   - Python：`src/agent_guardrails/rules/ast-grep/<rule-id>.yml`，並在 `tests/test_rules.py` 的 `VIOLATIONS` 加入違規案例。
   - Go：`src/agent_guardrails/rules/go/ast-grep/<rule-id>.yml`，並在 `tests/test_go_rules.py` 加入違規與合法案例。
   - 在 README 的規則表加一列。
6. 把 `pyproject.toml` 與 `.claude-plugin/plugin.json` 的版本號加一個 patch 版，執行 `uv lock`。
7. 驗證：`uv run pytest -q` 與 `uv run agent-guardrails check src tests` 都要通過。
8. 公開前掃描 `git diff main...HEAD`：不可以有密鑰、token、個人資料、內部主機名、本機絕對路徑、來源專案的名稱。有疑慮就停下來問。
9. push 分支並開 PR。使用者同意過合併與發版時，接著合併 PR、在合併後的 `main` 打 `v<新版本>` tag 並 push tag；否則回報 PR 連結後停止。
10. 回到原專案：把鎖定的 guardrails 版本改成新 tag（Python 在 `pyproject.toml` 的 dependency，Go 在 `Makefile` 的 `GUARDRAILS`），執行檢查，確認新規則生效。專案層若有同一條規則，刪掉它，避免報兩次。這個修改跟原本的 push 一起送出。

發現原專案鎖定的版本落後於 agent-guardrails 最新 tag 時，在回顧清單中提議升級，一樣等使用者同意。

## 禁止事項

- 不可以放寬、停用或刪除既有規則。認為某條規則不合理時，告訴使用者，由人決定。
- 不可以建立沒有測試案例的規則；`test-rules` 會擋下。
- 不可以為了讓規則通過而修改測試案例的意圖。
