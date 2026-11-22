#!/usr/bin/env bash
# PostToolUse hook：Claude 編輯 Python（.py）或 Go（.go）檔後執行 guardrails。
# exit 2 會把 stderr 回饋給 agent，要求它修正後才能繼續。
set -uo pipefail

input="$(cat)"
file="$(printf '%s' "$input" | jq -r '.tool_input.file_path // empty')"

case "$file" in
  *.py) file_language=python ;;
  *.go) file_language=go ;;
  *) exit 0 ;;
esac
[[ -f "$file" ]] || exit 0

source "$(dirname "${BASH_SOURCE[0]}")/session-state.sh"

# 只對 opt-in 的專案生效：檔案所屬專案要有 .agent-guardrails.toml，
# 或 pyproject.toml 內有 [tool.agent-guardrails]。
project="$(opted_in_project_root "$file")" || exit 0

# 檔案語言與專案語言不同時不檢查（例如 Python 專案裡的 .go 工具腳本）。
[[ "$(project_language "$project")" == "$file_language" ]] || exit 0

# 記下「這個 session 編輯過受檢查的檔案」，收尾時 propose-rules.sh 據此決定要不要請 agent 回顧。
touch "$(edited_marker "$input")"

# Go 檔：帶有產生器標頭的檔案必須由產生器產生，不接受 agent 手動編輯；
# 手寫的程式也不能加上這個標頭（golangci-lint 與 ast-grep 規則都會略過這種檔案）。
generated_header='^// Code generated .* DO NOT EDIT\.$'
if [[ "$file_language" == go ]] && sed '/^package[[:space:]]/q' "$file" | grep -qE "$generated_header"; then
  {
    echo "agent-guardrails 檢查未通過：$file"
    echo "這個檔案在 package 宣告前有「// Code generated ... DO NOT EDIT.」標頭。"
    echo "產生的檔案只能由產生器產生，而 guardrails 會略過這種檔案，手寫程式加上這個標頭等於關閉所有檢查。"
    echo "修正方式：若這是產生的檔案，請還原你的修改，改產生器的輸入後重新執行產生器（例如 go generate ./...）；"
    echo "若這是手寫的程式，請移除這個標頭。"
  } >&2
  exit 2
fi

# 選擇執行方式。Plugin 內附版本只在有 uvx 且由 Claude Code 啟動（有 CLAUDE_PLUGIN_ROOT）時可用。
plugin_runner=()
if command -v uvx >/dev/null 2>&1 && [[ -n "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  plugin_runner=(uvx --quiet --from "$CLAUDE_PLUGIN_ROOT" agent-guardrails)
fi

# Python 專案：專案 .venv 鎖定的版本優先，其次是全域安裝，最後才用 plugin 內附的版本。
# Go 專案沒有 .venv：plugin 內附的版本優先，避免用到 PATH 上只支援 Python 的舊版；沒有時才用全域安裝。
if [[ "$file_language" == python && -x "$project/.venv/bin/agent-guardrails" ]]; then
  runner=("$project/.venv/bin/agent-guardrails")
elif [[ "$file_language" == go && ${#plugin_runner[@]} -gt 0 ]]; then
  runner=("${plugin_runner[@]}")
elif command -v agent-guardrails >/dev/null 2>&1; then
  runner=(agent-guardrails)
elif [[ ${#plugin_runner[@]} -gt 0 ]]; then
  runner=("${plugin_runner[@]}")
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
    echo "請依上方每條訊息的修正方式修改程式碼。不要用 noqa / type: ignore / nolint / 改寫成字串等方式繞過。"
  } >&2
  exit 2
fi
