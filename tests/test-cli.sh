#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

python3 "$ROOT/opencode-agents.py" install --source "$ROOT" --target "$TMP/config" >/dev/null
python3 "$ROOT/opencode-agents.py" status --source "$ROOT" --target "$TMP/config" | grep -q 'missing=0 changed=0'
printf 'local\n' > "$TMP/config/agents/orchestrator-analyst.md"
python3 "$ROOT/opencode-agents.py" update --source "$ROOT" --target "$TMP/config" --backup-dir "$TMP/backup" >/dev/null
cmp "$ROOT/agents/orchestrator-analyst.md" "$TMP/config/agents/orchestrator-analyst.md"
grep -q 'local' "$TMP/backup/agents/orchestrator-analyst.md"
