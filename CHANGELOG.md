# Changelog

## 3.0.5 - 2026-08-01

### Fixed

- Allowed exact full-untracked porcelain status and reference-inventory forms; required validator to run each allowlisted Git inspection separately, preventing harmless commands from becoming approval-gated compound shell scripts.

### Compatibility

- Compound shell commands remain approval-gated, including `&&` and pipes. Restart OpenCode after updating agents.

## 3.0.4 - 2026-08-01

### Fixed

- Allowed validator read-only Git status, diff, revision, reference, index, and submodule command forms without confirmation; denied `diff` output/external-diff flags while Git reference mutation remains approval-gated.

### Compatibility

- Direct Git mutation remains unavailable to validator and executor; checkpoint commits still use the installed helper only. Restart OpenCode after updating agents.

## 3.0.3 - 2026-08-01

### Fixed

- Defined activation as an operational transition outside canonical dispatch authorization hashing, so expected `ACTIVE`, authorization-ID, and plan-state updates no longer stale a dispatch before executor commands begin.
- Required validator, planner, and executor to bind the same canonical authorization payload and authorized post-activation revisions rather than mutable raw artifact hashes.

### Compatibility

- Existing dispatches stopped before execution may be recovered and re-authorized; restart OpenCode after updating agents.

## 3.0.2 - 2026-08-01

### Fixed

- Granted structural planners exact `status.md` artifact writes and required them to refresh its planning state, preventing mandatory status writes from being denied during plan creation or replanning.
- Preserved least-privilege plan ownership: each workflow role retains only its required `plan/` artifact paths instead of broad `plan/**` access.

### Compatibility

- Restart OpenCode after updating agents because permissions are loaded at process start.

## 3.0.1 - 2026-07-31

### Removed

- Protocol-upgrade reports, consent, states, artifacts, planner mode, and recovery handling. Existing workflows now recover only against current artifacts.

## 3.0.0 - 2026-07-31

### Added

- Validator-owned immutable review epochs and `LANE_INPUT_ID` manifests, plus unique epoch lane and aggregate paths.
- `orchestrator-45-checkpointer` for exact accepted-stage commits through isolated index handling.
- Terra-pinned `orchestrator-75-escalation-reviewer` for demonstrated-risk adjudication after two mini cycles; `80` remains final-only.
- Human-readable workflow `status.md`, final-cycle progress, recovery/replan, and dirty-baseline consent.

### Changed

- Accepted stages now retain normal branch commits after review PASS. Workflow never rewrites history and preserves user-owned staged entries while refreshing committed workflow-path index entries.
- Stage mini reviewers receive only prior-checkpoint-to-current-stage delta; final reviewers receive cumulative checkpoint range.
- Unresolved stage security/local findings remain in current small-diff stage: after two mini-review/repair cycles Terra adjudicates only demonstrated risks, then replan/review repeats until resolution. Repairable final findings have no numeric blocker limit.

### Compatibility

- Terra escalation adds a third Terra-pinned role; `orchestrator-single-model` denies access to it.
- Restart OpenCode after updating agents because prompts and permissions are loaded at process start.

## 2.5.1 - 2026-07-31

### Fixed

- Bound workflow artifacts to explicit absolute active-session `WORKSPACE_ROOT`, preventing nested project sessions from using a parent Git root `.orchestrator` directory.
- Required bootstrap, primary orchestration, validator, and executor to reject stale or mismatched workflow roots before writing.

### Compatibility

- Existing correctly rooted workflows continue unchanged. A nested-project workflow whose immutable manifest points to a parent Git-root `.orchestrator` cannot resume under this version: retain old artifacts read-only and start a new workflow under active-session `WORKSPACE_ROOT`; do not move or rewrite immutable artifacts automatically.
- Restart OpenCode after updating agents because prompts and permissions are loaded at process start.

## 2.5.0 - 2026-07-31

### Fixed

- Removed primary-agent permission for generic exploration and required workflow-role artifact gates before executor dispatch.
- Added validator-produced dispatch authorization IDs and inactive-candidate activation for stages and local repair batches.
- Added artifact- and identity-bound executor preflight, with `BLOCKED` results for missing, stale, or contradictory inputs.
- Required direct validation command exits and evidence artifacts before stage acceptance or `DONE`.
- Denied direct executor Git command patterns, denied edit-tool `.git` writes, allowlisted exact validator read-only Git commands, and required runtime approval for other validator Git commands; both roles retain explicit prompt-level mutation prohibitions and post-command inventory checks.
- Required command-safety preflight for shell composition and prohibited undeclared bulk rewrites in executor and validator workflows.

### Compatibility

- Dispatch now requires planner candidate creation, validator `AUTHORIZE_DISPATCH`, and planner `ACTIVATE_DISPATCH`; local repairs additionally use planner `AUTHORIZE_REPAIR`.
- Executor callers must provide canonical artifact references and IDs instead of copied source, inferred plans, or ad hoc write lists.
- Restart OpenCode after updating agents because permissions are loaded at process start.

## 2.4.2 - 2026-07-31

### Fixed

- Allowed only the installed protocol directory glob at the external-directory boundary, then denied worktree-relative protocol paths except `orchestrator-v2.md` in `read` permissions. This lets every Orchestrator role read its mandatory protocol without exposing other external configuration paths.

### Compatibility

- Restart OpenCode after updating agents because permissions are loaded at process start.

## 2.4.1 - 2026-07-31

### Fixed

- Allowed root-relative `.orchestrator` artifacts explicitly, so normalized OpenCode `edit` paths can create workflow artifacts while deny-by-default remains intact.
- Added nested workspace artifact patterns and corrected bootstrap root `.gitignore` permission.
- Narrowed bootstrap and planner artifact ownership to exact canonical classes and separated mini-review lane and aggregate writes.
- Assigned `SINGLE_MODEL` final assurance to validator `POST_REVIEW` and generalized planning authority contracts across profiles.

### Compatibility

- Mini-review writes now use `reviews/mini/lanes/` and `reviews/mini/aggregate/`; regenerate pending review output paths before resuming an active workflow.
- Restart OpenCode after updating agents because permissions are loaded at process start.

## 2.4.0 - 2026-07-31

### Added

- `orchestrator-single-model` primary agent for `SINGLE_MODEL` workflows.
- Model-free `orchestrator-25-planner-full` combining reconnaissance, structural planning, audit, and replan for single-model workflows.
- Immutable workflow profile selected before baseline capture and persisted in the workflow manifest.

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
