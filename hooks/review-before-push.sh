#!/usr/bin/env bash
# PreToolUse hook（Bash）：Claude 要執行 git push 時，如果這個 session 編輯過 opt-in
# 專案的受檢查檔案（.py / .go），先擋下這一次 push，請 agent 回顧這次修改有沒有
# 可以變成 guardrails 規則的地方（專案層／共用層），把候選列給使用者確認後再 push。
# 每批編輯只擋一次：擋下時會清掉標記，agent 重新執行同一個指令就會通過。
# 這個 hook 只負責「提醒」；任何規則檔的新增都必須先得到使用者同意。
set -uo pipefail

input="$(cat)"

command="$(printf '%s' "$input" | jq -r '.tool_input.command // empty')"
[[ -n "$command" ]] || exit 0

# 只看真的會送出 commit 的 git push（允許 git -C <dir>、-c k=v 等全域選項）。
push_pattern='(^|[^[:alnum:]_./-])git([[:space:]]+-[^[:space:]]+([[:space:]]+[^-[:space:]][^[:space:]]*)?)*[[:space:]]+push([[:space:]]|$)'
printf '%s' "$command" | grep -qE -- "$push_pattern" || exit 0
printf '%s' "$command" | grep -qE -- '--dry-run|--delete' && exit 0

source "$(dirname "${BASH_SOURCE[0]}")/session-state.sh"
marker="$(edited_marker "$input")"

# 標記只會在 opt-in 專案的受檢查檔案被編輯時產生；沒有標記就不打擾。
[[ -f "$marker" ]] || exit 0
rm -f "$marker"

jq -n '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: "[agent-guardrails] push 前先做一次規則回顧，這次 push 暫時擋下（只擋這一次，回顧完重新執行同一個指令即可）。請用 agent-guardrails:learn-rule skill 的「回顧」流程檢查即將 push 的修改（git diff @{upstream}...HEAD，沒有 upstream 時對預設分支比較）以及這個 session 中被使用者糾正、或你自己寫錯又改掉的地方：有沒有可以用程式規則（AST pattern、禁用 API、import 邊界）擋下、目前規則又還沒涵蓋的錯誤。有的話，把候選分成「專案層」（只適用這個專案，跟著這次 push 一起送出）與「共用層」（所有專案都適用，同步到 agent-guardrails）列給使用者，一次問完；在使用者明確同意之前，不要建立或修改任何規則檔，也不要 push。沒有候選時，寫一行「這次修改沒有適合新增為 guardrails 規則的項目」，然後直接重新執行剛才的 push 指令。如果這次 push 本身就是在送出使用者剛同意的規則，直接重新執行即可。"
  }
}'
