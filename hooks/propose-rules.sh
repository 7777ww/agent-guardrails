#!/usr/bin/env bash
# UserPromptSubmit hook：只有在使用者送出「收尾」訊息（接受任務、允許 push、開 PR…）
# 且這個 session 編輯過 opt-in 專案的受檢查檔案（.py / .go）時，才請 agent 回顧
# 「有沒有犯過可以用規則擋下的錯」，並把候選規則列給使用者確認。
# 這個 hook 只負責「提醒」；任何規則檔的新增都必須先得到使用者同意。
set -uo pipefail

input="$(cat)"

source "$(dirname "${BASH_SOURCE[0]}")/session-state.sh"
marker="$(edited_marker "$input")"

# 標記只會在 opt-in 專案的受檢查檔案被編輯時產生；沒有標記就不打擾。
[[ -f "$marker" ]] || exit 0

# 收尾用語。可用環境變數 AGENT_GUARDRAILS_WRAP_UP_PATTERN 覆寫（extended regex，不分大小寫）。
default_pattern='push|pull request|(開|开|建立|创建|發|发) ?(pr|mr)|merge|ship|wrap.?up|推上|推送|合併|合并|交付|收尾|任務完成|任务完成|完成了|結案|结案'
pattern="${AGENT_GUARDRAILS_WRAP_UP_PATTERN:-$default_pattern}"

printf '%s' "$input" | jq -r '.prompt // empty' | grep -qiE -- "$pattern" || exit 0

rm -f "$marker"

jq -n '{
  hookSpecificOutput: {
    hookEventName: "UserPromptSubmit",
    additionalContext: "[agent-guardrails] 使用者這則訊息看起來是在收尾（接受任務、允許 push 或開 PR）。如果確實如此，先完成使用者要求的事，然後在收尾總結中加入一項「可新增的 guardrails 規則」：用 agent-guardrails:learn-rule skill 的「回顧」流程檢查這次任務，有沒有被使用者糾正、或你自己寫錯又改掉的地方，而且那個錯誤可以用程式規則（AST pattern、禁用 API、import 邊界）偵測、目前的規則又還沒涵蓋。有的話，把候選規則列給使用者並詢問是否要新增；在使用者明確同意之前，不要建立或修改任何規則檔。沒有的話，只寫一行「這次任務沒有適合新增為 guardrails 規則的項目」。如果你還有其他例行的收尾提案，請把這一項併入同一份清單。如果這則訊息其實不是在收尾（例如否定句、引用、假設），忽略這段提醒。"
  }
}'
