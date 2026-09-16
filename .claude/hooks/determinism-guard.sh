#!/usr/bin/env bash
# PostToolUse guard: the connector package (carbonara/) must stay deterministic.
# Flags runtime non-determinism — LLM calls, unseeded randomness, wall-clock,
# env reads — introduced into carbonara/*.py (excluding test files). Fixture
# generators and build scripts belong OUTSIDE carbonara/, where this is silent.
#
# Reads the PostToolUse JSON payload on stdin, inspects the edited file, and
# exits 2 with an explanation if a forbidden pattern is present, so the model
# sees the violation and fixes it. See .claude/skills/carbonara-correctness.
set -euo pipefail

file_path="$(python3 -c 'import json,sys; print((json.load(sys.stdin).get("tool_input") or {}).get("file_path",""))' 2>/dev/null || true)"

# Only guard Python modules inside the connector package; skip tests.
case "$file_path" in
  *"/carbonara/"*.py) ;;
  *) exit 0 ;;
esac
case "$file_path" in
  */test_*.py|*_test.py) exit 0 ;;
esac
[ -f "$file_path" ] || exit 0

# extended-regex pattern (literal parens escaped as \()|human-readable reason
patterns=(
  'import openai|LLM at runtime (openai) — no model call in the data path'
  'import anthropic|LLM at runtime (anthropic) — no model call in the data path'
  'from openai|LLM at runtime (openai) — no model call in the data path'
  'from anthropic|LLM at runtime (anthropic) — no model call in the data path'
  'datetime\.now\(|wall-clock read — inject the timestamp as a parameter instead'
  'datetime\.today\(|wall-clock read — inject the timestamp as a parameter instead'
  'date\.today\(|wall-clock read — inject the timestamp as a parameter instead'
  'time\.time\(|wall-clock read — inject the timestamp as a parameter instead'
  'uuid\.uuid4\(|non-deterministic id — derive ids from inputs (e.g. content hash)'
  'uuid4\(|non-deterministic id — derive ids from inputs (e.g. content hash)'
  'np\.random\.|unseeded randomness — the data path must be reproducible'
  'numpy\.random\.|unseeded randomness — the data path must be reproducible'
  'random\.random\(|unseeded randomness — the data path must be reproducible'
  'random\.randint\(|unseeded randomness — the data path must be reproducible'
  'random\.choice\(|unseeded randomness — the data path must be reproducible'
  'random\.uniform\(|unseeded randomness — the data path must be reproducible'
  'os\.environ|environment read — pass configuration in explicitly'
)

hits=""
for entry in "${patterns[@]}"; do
  pat="${entry%%|*}"
  reason="${entry#*|}"
  if grep -nE "$pat" "$file_path" >/dev/null 2>&1; then
    lines="$(grep -nE "$pat" "$file_path" | cut -d: -f1 | tr '\n' ',' | sed 's/,$//')"
    hits="${hits}  - line(s) ${lines}: ${reason}"$'\n'
  fi
done

if [ -n "$hits" ]; then
  {
    echo "determinism-guard: non-deterministic pattern in the connector package (${file_path##*/})."
    printf '%s' "$hits"
    echo "The data path must be reproducible (carbonara-correctness §1). Move non-deterministic"
    echo "helpers outside carbonara/, or inject the value as an explicit parameter."
  } >&2
  exit 2
fi
exit 0
