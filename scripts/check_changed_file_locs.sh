#!/usr/bin/env bash

set -euo pipefail

MAX_LOC="${MAX_LOC:-500}"

is_source_file() {
  local path="$1"
  case "$path" in
    *.py|*.ts|*.tsx|*.js|*.jsx|*.css|*.scss|*.html|*.htm|*.sql|*.sh|*.bash|*.zsh|*.yaml|*.yml|*.toml|*.ini|*.cfg|*.conf|*.go|*.rs|*.java|*.kt|*.swift|*.rb|*.php|*.c|*.cc|*.cpp|*.h|*.hpp)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_excluded_test_path() {
  local path="$1"
  if [[ "$path" =~ (^|/)tests?/ ]]; then
    return 0
  fi
  if [[ "$path" =~ (^|/)test_ ]]; then
    return 0
  fi
  return 1
}

resolve_base_ref() {
  if [[ -n "${GITHUB_BASE_REF:-}" ]]; then
    echo "origin/${GITHUB_BASE_REF}"
    return 0
  fi
  if git rev-parse --verify HEAD~1 >/dev/null 2>&1; then
    echo "HEAD~1"
    return 0
  fi
  echo "HEAD"
}

collect_changed_files() {
  local base_ref="$1"
  if [[ "$base_ref" == "HEAD" ]]; then
    git ls-files
    return 0
  fi
  git diff --name-only --diff-filter=ACMR "${base_ref}...HEAD"
}

main() {
  local base_ref
  base_ref="$(resolve_base_ref)"

  if [[ "$base_ref" == origin/* ]]; then
    git fetch origin "${GITHUB_BASE_REF}:${GITHUB_BASE_REF}" --depth=1 >/dev/null 2>&1 || true
  fi

  local offenders=()
  while IFS= read -r file_path; do
    [[ -z "$file_path" ]] && continue
    [[ -f "$file_path" ]] || continue
    is_source_file "$file_path" || continue
    is_excluded_test_path "$file_path" && continue

    local line_count
    line_count="$(wc -l < "$file_path" | tr -d '[:space:]')"
    if [[ -n "$line_count" ]] && [[ "$line_count" -gt "$MAX_LOC" ]]; then
      offenders+=("${file_path}:${line_count}")
    fi
  done < <(collect_changed_files "$base_ref")

  if [[ "${#offenders[@]}" -gt 0 ]]; then
    echo "LOC guard failed: source files above ${MAX_LOC} LOC detected in changed files:"
    for item in "${offenders[@]}"; do
      echo "  - ${item}"
    done
    exit 1
  fi

  echo "LOC guard passed: no changed source files exceed ${MAX_LOC} LOC."
}

main "$@"

