# Changelog

## 2.4.0 - 2026-07-31

### Added

- `orchestrator-single-model` primary agent for `SINGLE_MODEL` workflows.
- Model-free `orchestrator-25-planner-full` combining reconnaissance, structural planning, audit, and replan for single-model workflows.
- Immutable workflow profile persisted before baseline capture.

### Changed

- Generated both primary orchestrator prompts from one shared template and profile fragments.
- `SINGLE_MODEL` final assurance now requires final validation, fresh cumulative mini review, and post-mini identity confirmation instead of Terra final review.

### Compatibility

- Existing `orchestrator` workflows retain Terra senior planning and Terra final review. Select `orchestrator-single-model` when no model override may occur.

## 2.3.0 - 2026-07-31

### Changed

- Removed `caveman` from Orchestrator agent filenames and preserved optional Caveman skill support inside hidden workflow prompts.

### Migration

- Run `update --prune-legacy` to remove prior `-caveman` filenames.

## 2.2.0 - 2026-07-30

### Added

- Official Caveman installer handoff after repository installation.
- Managed global `AGENTS.md` guidance for using Caveman when installed.
- Installation, update, and status through GitHub Git Trees/Blobs API without cloning the repository.
- Remote bootstrap commands using `raw.githubusercontent.com`.
- `--repository`, `--ref`, and `GITHUB_TOKEN` support for forks, tags, and private repositories.
- Ordered `orchestrator-00` through `orchestrator-80` agent filenames for one readable flat group; primary agent remains `orchestrator` in UI.

### Changed

- Orchestrator no longer requires or explicitly loads Caveman.
- Hidden workflow agents conditionally use Caveman ultra mode and continue normally when skill is unavailable.
- CLI manages agents, protocols, and global guidance while preserving unrelated global instructions; it does not bundle or install a Caveman copy.
- Existing local `--source` workflows remain supported.
- Run `update --prune-legacy` to remove prior Orchestrator v2 agent files; built-in and unknown user prompts remain untouched.

## 2.1.0 - 2026-07-30

### Added

- `bin/opencode-agents` CLI with safe `install`, backed-up `update`, and `status` commands.
- CLI smoke tests.
- Explicit `2.1.0` version marker in every agent prompt.
- Cross-platform Python CLI runnable from repository root.
- Repository scope reduced to Orchestrator v2 agents and their direct workflow roles.
- Portable protocol-path rendering for installed agent prompts.
- `update --prune-legacy` for explicit removal of former repository agents.

### Compatibility

- Python CLI requires Python 3.9 or newer. Use `python3` on Linux/macOS or `py -3` on Windows.

### Migration

- Replace manual prompt copying with root CLI: `python3 opencode-agents.py install` on Linux/macOS or `py -3 opencode-agents.py install` on Windows.
- Run `update --prune-legacy` once to remove only former repository agent names; unknown user prompts remain untouched.

## 2.0.0 - 2026-07-30

### Added

- Shared Orchestrator Protocol v2.
- Task-bound `.orchestrator` workflow artifacts.
- Immutable request ledger and content identity model.
- Recon and pre-dispatch prototype gates.
- Verifiable stage boundaries and GREEN review readiness.
- Dedicated bootstrap, executor, validator, mini-reviewer, aggregator, and final-reviewer roles.
- Risk-based parallel mini reviews and independent Terra final review.
- Repository maintenance guidance.

### Changed

- Product mutation runs sequentially.
- Stage checkpoints use immutable snapshots and delta patches instead of temporary Git commits.
- Only senior planner and final reviewer pin Terra; operational agents inherit the selected model.
- Final evidence binds product, validation, review scope, mini-review bundle, and post-review identity.

### Removed

- Mutable `.tmp` planning layout for Orchestrator v2.
- Review of non-buildable intermediate states.
- Explicit Luna/Sol model pins for operational roles.
- Final `git reset --mixed` workflow.
