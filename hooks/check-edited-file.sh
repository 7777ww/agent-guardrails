#!/usr/bin/env bash
# PostToolUse hook：Claude 編輯 Python 檔後執行 guardrails。
# exit 2 會把 stderr 回饋給 agent，要求它修正後才能繼續。
set -uo pipefail

input="$(cat)"
file="$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')"

[[ "$file" == *.py && -f "$file" ]] || exit 0

source "$(dirname "${BASH_SOURCE[0]}")/session-state.sh"

# 只對 opt-in 的專案生效：檔案所屬專案的 pyproject.toml 內要有 [tool.agent-guardrails]。
project="$(opted_in_project_root "$file")" || exit 0

# 記下「這個 session 編輯過 Python 檔」，收尾時 propose-rules.sh 據此決定要不要請 agent 回顧。
touch "$(edited_marker "$input")"

# 優先使用專案自己鎖定的版本，其次是全域安裝，最後才用 plugin 內附的版本。
if [[ -x "$project/.venv/bin/agent-guardrails" ]]; then
  runner=("$project/.venv/bin/agent-guardrails")
elif command -v agent-guardrails >/dev/null 2>&1; then
  runner=(agent-guardrails)
elif command -v uvx >/dev/null 2>&1 && [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  runner=(uvx --quiet --from "$CLAUDE_PLUGIN_ROOT" agent-guardrails)
else
  echo "agent-guardrails: 找不到可用的執行方式（需要 uv 或已安裝 agent-guardrails），本次未檢查。" >&2
  exit 1
fi

cd "$project" || exit 1

if ! output="$("${runner[@]}" check "$file" 2>&1)"; then
  {
    echo "agent-guardrails 檢查未通過：$file"
    echo "$output"
    echo
    echo "請依上方每條訊息的修正方式修改程式碼。不要用 noqa / type: ignore / 改寫成字串等方式繞過。"
  } >&2
  exit 2
fi
