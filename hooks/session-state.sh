#!/usr/bin/env bash
# 兩個 hook 共用：opt-in 專案判斷，以及這個 session 的「編輯過受檢查檔案」標記檔路徑。
# 用法：marker="$(edited_marker "$hook_input_json")"

# 從檔案所在目錄往上找最近的 opt-in 標記並印出專案根目錄：
#   - .agent-guardrails.toml（任何語言；同一層若同時有 pyproject.toml，以它為準）
#   - 內含 [tool.agent-guardrails] 的 pyproject.toml（Python）
# 遇到沒有標記的 pyproject.toml 就停止，視為未 opt-in。不依賴 CLAUDE_PROJECT_DIR，
# 因為 session 中途切換資料夾或 monorepo 時，它不一定指向檔案所屬的專案。
opted_in_project_root() {
  local dir
  dir="$(cd "$(dirname "$1")" 2>/dev/null && pwd)" || return 1
  while [[ -n "$dir" && "$dir" != "/" ]]; do
    if [[ -f "$dir/.agent-guardrails.toml" ]]; then
      printf '%s' "$dir"
      return 0
    fi
    if [[ -f "$dir/pyproject.toml" ]]; then
      grep -qs '^\[tool\.agent-guardrails\]' "$dir/pyproject.toml" || return 1
      printf '%s' "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  return 1
}

# 印出專案語言：.agent-guardrails.toml 第一個 [table] 之前的 language = "..."，預設 python。
project_language() {
  local marker="$1/.agent-guardrails.toml" language=""
  if [[ -f "$marker" ]]; then
    language="$(sed -n '/^[[:space:]]*\[/q; s/^[[:space:]]*language[[:space:]]*=[[:space:]]*["'"'"']\([^"'"'"']*\)["'"'"'].*/\1/p' "$marker" | head -n 1)"
  fi
  printf '%s' "${language:-python}" | tr '[:upper:]' '[:lower:]'
}

edited_marker() {
  local session
  session="$(printf '%s' "$1" | jq -r '.session_id // "unknown"' | tr -cd 'A-Za-z0-9_-')"
  local dir="${TMPDIR:-/tmp}/agent-guardrails-state"
  mkdir -p "$dir"
  printf '%s/%s.edited' "$dir" "${session:-unknown}"
}
