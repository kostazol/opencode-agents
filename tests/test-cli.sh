#!/usr/bin/env bash
set -eu

repo_root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cli="$repo_root/bin/opencode-agents"
tmp_root="$(mktemp -d)"
trap 'rm -rf "$tmp_root"' EXIT

source_root="$tmp_root/source"
target_root="$tmp_root/config"
backup_root="$tmp_root/backup"
mkdir -p "$source_root/agents" "$source_root/plugins"
printf 'agent-v1\n' > "$source_root/agents/example.md"
printf 'plugin-v1\n' > "$source_root/plugins/example.js"
test ! -e "$source_root/AGENTS.md"
test ! -e "$source_root/helpers"

"$cli" --source "$source_root" --target "$target_root" install
test "$(cat "$target_root/agents/example.md")" = agent-v1
test "$(cat "$target_root/plugins/example.js")" = plugin-v1
test -f "$target_root/AGENTS.md"
grep -q 'caveman' "$target_root/AGENTS.md"
test ! -e "$target_root/helpers"
"$cli" --source "$source_root" --target "$target_root" install | grep -q 'skip agents/example.md'

printf 'local-change\n' > "$target_root/agents/example.md"
printf 'user-agent\n' > "$target_root/agents/user-agent.md"
printf 'user-plugin\n' > "$target_root/plugins/user-plugin.js"
printf 'agent-v2\n' > "$source_root/agents/example.md"
printf 'plugin-v2\n' > "$source_root/plugins/example.js"
"$cli" --source "$source_root" --target "$target_root" --backup-dir "$backup_root" update
test "$(cat "$target_root/agents/example.md")" = agent-v2
test "$(cat "$target_root/plugins/example.js")" = plugin-v2
test "$(cat "$backup_root/agents/example.md")" = local-change
test "$(cat "$target_root/agents/user-agent.md")" = user-agent
test "$(cat "$target_root/plugins/user-plugin.js")" = user-plugin

"$cli" --source "$source_root" --target "$target_root" status | grep -q 'current agents/example.md'
"$cli" --source "$source_root" --target "$target_root" status | grep -q 'current plugins/example.js'
printf 'protected\n' > "$tmp_root/protected.txt"
printf 'agent-link\n' > "$source_root/agents/link.md"
ln -s "$tmp_root/protected.txt" "$target_root/agents/link.md"
if "$cli" --source "$source_root" --target "$target_root" update >/dev/null 2>&1; then
    exit 1
fi
test "$(cat "$tmp_root/protected.txt")" = protected
rm "$target_root/agents/link.md"
printf 'protected-hardlink\n' > "$tmp_root/protected-hardlink.txt"
printf 'agent-hardlink\n' > "$source_root/agents/hardlink.md"
ln "$tmp_root/protected-hardlink.txt" "$target_root/agents/hardlink.md"
"$cli" --source "$source_root" --target "$target_root" update >/dev/null
test "$(cat "$tmp_root/protected-hardlink.txt")" = protected-hardlink
printf 'CLI tests passed\n'
