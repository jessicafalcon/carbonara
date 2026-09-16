#!/usr/bin/env bash
# PostToolUse: format + lint-fix an edited Python file so every file lands in
# house style without manual effort. Deterministic, non-blocking — if ruff is
# not installed yet (early in Phase 0) it exits quietly. Config lives in
# pyproject.toml (line-length 120; E,W,F,I,B,UP). See carbonara-craft.
set -euo pipefail

file_path="$(python3 -c 'import json,sys; print((json.load(sys.stdin).get("tool_input") or {}).get("file_path",""))' 2>/dev/null || true)"

case "$file_path" in
  *.py) ;;
  *) exit 0 ;;
esac
[ -f "$file_path" ] || exit 0

# Prefer the project's uv-managed ruff; fall back to a ruff on PATH.
if command -v uv >/dev/null 2>&1 && uv run ruff --version >/dev/null 2>&1; then
  ruff() { uv run ruff "$@"; }
elif command -v ruff >/dev/null 2>&1; then
  ruff() { command ruff "$@"; }
else
  exit 0  # ruff not available yet — nothing to do
fi

ruff format "$file_path" >/dev/null 2>&1 || true
ruff check --fix "$file_path" >/dev/null 2>&1 || true

# Surface anything ruff could not auto-fix, as feedback (non-blocking).
remaining="$(ruff check "$file_path" 2>/dev/null || true)"
if [ -n "$remaining" ] && ! printf '%s' "$remaining" | grep -q 'All checks passed'; then
  echo "ruff: unresolved lint in ${file_path##*/}:" >&2
  printf '%s\n' "$remaining" >&2
fi
exit 0
