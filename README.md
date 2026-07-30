# OpenCode Agents

Private source repository for personal OpenCode agent prompts and shared orchestration protocols.

## Contents

- `agents/` — portable source prompts for Orchestrator v2 roles.
- `protocols/` — shared protocols loaded by coordinated agents.
- `AGENTS.md` — maintenance rules for humans and coding agents.
- `CHANGELOG.md` — notable prompt and workflow changes.
- `VERSION` — repository configuration version.

Repository keeps only Orchestrator v2 agents: orchestrator, bootstrap, planners, executor, validator, mini-reviewer, aggregator, and final-reviewer.

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

CLI installs and updates agent prompts plus shared protocols:

```bash
# Linux/macOS
python3 opencode-agents.py install
python3 opencode-agents.py update --prune-legacy
python3 opencode-agents.py status

# Windows
py -3 opencode-agents.py install
py -3 opencode-agents.py update --prune-legacy
py -3 opencode-agents.py status
```

Run commands from repository root. Python CLI works on Windows, Linux, and macOS. `install` copies only missing files. `update` backs up changed files before replacement. `update --prune-legacy` removes only former repository agent names; unknown user prompts remain. Use `--dry-run` to preview updates, `--target DIR` to select another OpenCode config root, and `--backup-dir DIR` to control backup location. Unix users may use `./bin/opencode-agents` as convenience wrapper.

Source prompts use portable protocol-path placeholders. CLI renders them to `<target>/protocols/orchestrator-v2.md` during installation and update, including matching OpenCode permissions.

Restart OpenCode after installation. Agent and protocol files are loaded at process start.

Run CLI checks:

```bash
# Linux/macOS
python3 tests/test-cli.py

# Windows
py -3 tests/test-cli.py
```

## Validation

After installing changes:

```bash
opencode debug config >/dev/null
```

For orchestration changes, also perform an independent cross-file review covering permissions, state transitions, evidence IDs, repair limits, and final-review handoffs.

## Security

This repository intentionally excludes `opencode.json`, authentication files, MCP environment files, session databases, tool output, and generated workflow artifacts. Never commit credentials, tokens, private keys, `.env` contents, or captured user repositories.
