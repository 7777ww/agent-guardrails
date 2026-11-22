#!/usr/bin/env bash
# 兩個 hook 共用：回傳這個 session 的「編輯過 Python 檔」標記檔路徑。
# 用法：marker="$(edited_marker "$hook_input_json")"

# 從檔案所在目錄往上找最近的 pyproject.toml；只有內含 [tool.agent-guardrails]
# 才視為 opt-in 專案並印出其根目錄。不依賴 CLAUDE_PROJECT_DIR，因為 session
# 中途切換資料夾或 monorepo 時，它不一定指向檔案所屬的專案。
opted_in_project_root() {
  local dir
  dir="$(cd "$(dirname "$1")" 2>/dev/null && pwd)" || return 1
  while [[ -n "$dir" && "$dir" != "/" ]]; do
    if [[ -f "$dir/pyproject.toml" ]]; then
      grep -qs '^\[tool\.agent-guardrails\]' "$dir/pyproject.toml" || return 1
      printf '%s' "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  return 1
}

edited_marker() {
  local session
  session="$(printf '%s' "$1" | jq -r '.session_id // "unknown"' | tr -cd 'A-Za-z0-9_-')"
  local dir="${TMPDIR:-/tmp}/agent-guardrails-state"
  mkdir -p "$dir"
  printf '%s/%s.edited' "$dir" "${session:-unknown}"
}
