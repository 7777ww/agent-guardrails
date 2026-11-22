---
name: learn-rule
description: 把 agent 犯過的錯變成一條 guardrails 規則，讓同樣的錯之後被程式自動擋下。在任務收尾（使用者接受任務、允許 push 或開 PR）時回顧是否有可新增的規則、使用者糾正了一個可以用 lint 偵測的錯誤、或使用者說「把這個變成規則」、「新增 guardrails 規則」、「learn rule」時使用。
---

# 從錯誤產生 guardrails 規則

目標：用「會報錯的規則」取代「寫在 prompt 裡的提醒」。規則一旦建立，agent 就不可能再犯同樣的錯。

**硬性要求：在使用者明確同意之前，不可以建立或修改任何規則檔。** 回顧只產出「候選清單」。

## 一、回顧：找出候選規則

檢視這次任務的工作，找出符合下列全部條件的錯誤：

1. **真的發生過**：被使用者糾正，或你寫了之後自己發現不對而改掉。不要憑空發明「可能會犯」的錯。
2. **看程式碼形狀就能判斷**：用了不該用的 API、特定的寫法、跨層 import。
3. **現有規則沒涵蓋**：先確認 `agent-guardrails check` 目前擋不下它。
4. **錯誤寫法幾乎沒有正當用途**：如果正確與錯誤的用法長得一樣，就不適合。

不適合建規則的情況要直接排除，並在被問到時說明原因：

- 邏輯錯誤、算錯、誤解需求：這些應該變成測試，不是 lint 規則。
- 只是風格偏好，沒有造成實際問題。
- 只發生一次、且高度依賴當下情境。

沒有候選時，只回一行「這次任務沒有適合新增為 guardrails 規則的項目」。

有候選時，對每一項向使用者說明，然後**停下來等使用者決定**：

- 發生了什麼錯（一句話）。
- 規則會擋什麼寫法、建議的正確寫法。
- 建議放在專案層還是共用層（見下）。
- 預估的誤判風險。

## 二、決定規則放哪一層

| 層 | 位置 | 何時選 |
|---|---|---|
| 專案層 | 目前專案的 `rules/` 與 `rule-tests/` | 預設。錯誤與這個專案的架構或慣例有關 |
| 共用層 | agent-guardrails repo | 任何同語言（Python 或 Go）專案都會犯的錯，而且已在專案層驗證過好用 |

拿不定主意時先放專案層。

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

## 四、升級到共用層

共用 repo 是**公開的**，而且走 PR，由使用者 review 後合併。

1. 把規則與測試案例改寫成通用版本：移除專案名稱、內部模組名、業務用語、客戶名稱。
2. 向使用者說明要公開的完整內容，取得同意。
3. 在 agent-guardrails repo 的 clone 開新分支。找不到本機 clone 時請使用者提供路徑。
4. 規則放進 `src/agent_guardrails/rules/ast-grep/`，並在 `tests/test_rules.py` 的 `VIOLATIONS` 加入對應的違規案例，執行 `uv run pytest`。
5. 開 PR，不要直接推到 `main`，也不要自行合併。
6. 合併並發新版後，把專案層的那條規則刪掉，避免同一條規則報兩次。

## 禁止事項

- 不可以放寬、停用或刪除既有規則。認為某條規則不合理時，告訴使用者，由人決定。
- 不可以建立沒有測試案例的規則；`test-rules` 會擋下。
- 不可以為了讓規則通過而修改測試案例的意圖。
