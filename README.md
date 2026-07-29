# OpenCode Agents

Private source repository for personal OpenCode agent prompts and shared orchestration protocols.

## Contents

- `agents/` — snapshots of global agents from `~/.config/opencode/agents/`.
- `protocols/` — shared protocols loaded by coordinated agents.
- `AGENTS.md` — maintenance rules for humans and coding agents.
- `CHANGELOG.md` — notable prompt and workflow changes.
- `VERSION` — repository configuration version.

## Orchestrator v2

Primary workflow:

```text
orchestrator-caveman
├── workflow-bootstrap-caveman
├── planner-caveman
├── planner-senior-caveman (Terra)
├── executor-caveman
├── validator-caveman
├── mini-reviewer-caveman
├── review-aggregator-caveman
└── final-reviewer-caveman (Terra)
```

Shared contract: `protocols/orchestrator-v2.md`.

Core behavior:

- one ignored `.orchestrator/tasks/<workflow-id>/` workspace per user outcome;
- immutable request ledger and pre-mutation baseline;
- repository and test prototypes stored as `path#symbol` references, never copied source bodies;
- exact prototype revalidation before every implementation stage;
- independently buildable and testable stage boundaries;
- RED/GREEN and affected validation before review;
- risk-based parallel mini-review lenses;
- fresh cumulative mini review before independent Terra final review;
- content-bound evidence IDs and bounded repair loops;
- snapshot delta artifacts instead of temporary Git commits or resets.

## Model policy

Only roles requiring deliberate senior independence pin a model:

- `planner-senior-caveman`: `openai/gpt-5.6-terra`;
- `final-reviewer-caveman`: `openai/gpt-5.6-terra`.

Other Orchestrator v2 agents omit `model` and inherit the active/default model. This keeps bootstrap, execution, validation, and mini review usable with Luna or another selected model. Legacy or unrelated agents may retain their own model policy.

## Installation

The current prompts use the personal absolute protocol path:

```text
/home/kostaz/.config/opencode/protocols/orchestrator-v2.md
```

Preview differences before installation:

```bash
diff -ru agents ~/.config/opencode/agents || true
diff -ru protocols ~/.config/opencode/protocols || true
```

First installation without overwriting existing files:

```bash
mkdir -p ~/.config/opencode/agents ~/.config/opencode/protocols
cp -n agents/*.md ~/.config/opencode/agents/
cp -n protocols/*.md ~/.config/opencode/protocols/
```

Updating replaces matching live prompts. Back them up first:

```bash
set -eu
backup="$HOME/.config/opencode-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup/agents" "$backup/protocols"
cp -a ~/.config/opencode/agents/. "$backup/agents/"
cp -a ~/.config/opencode/protocols/. "$backup/protocols/"
test -d "$backup/agents" -a -d "$backup/protocols"
mkdir -p ~/.config/opencode/agents ~/.config/opencode/protocols
cp agents/*.md ~/.config/opencode/agents/
cp protocols/*.md ~/.config/opencode/protocols/
```

Restart OpenCode after installation. Agent and protocol files are loaded at process start.

## Validation

After installing changes:

```bash
opencode debug config >/dev/null
```

For orchestration changes, also perform an independent cross-file review covering permissions, state transitions, evidence IDs, repair limits, and final-review handoffs.

## Security

This repository intentionally excludes `opencode.json`, authentication files, MCP environment files, session databases, tool output, and generated workflow artifacts. Never commit credentials, tokens, private keys, `.env` contents, or captured user repositories.
