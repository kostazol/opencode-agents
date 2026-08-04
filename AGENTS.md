# Agent Maintenance Guide

## Scope and sources of truth

This repository versions exactly two user-facing OpenCode primary agents and their least-privileged subagents. Prompts are executable workflow contracts.

- `orchestrator-analyst` owns planning orchestration and user interaction.
- `orchestrator-executor` owns safe execution of exactly one task.
- No single-model primary variants, runtime workflow plugin, custom certificate tool, or synthetic continuation exist.
- OpenCode's native agentic task loop is the sole workflow harness: primaries invoke fresh subagents, consume results, and immediately dispatch the next required tool call in the same turn.
- Explicit current user instruction outranks prior workflow state. Platform safety constraints always apply.

## Staged analyst workflow

### Discovery and approval

- Analyst captures session working directory as immutable `WORKFLOW_BASE`. `1_orchestrator` is anchored there, never at Git root or a parent.
- Fresh `orchestrator-stage-decomposer` performs bounded no-write discovery in `INITIAL` mode and proposes provisional ordered stages.
- Fresh `orchestrator-stage-question-reviewer` independently finds material user-visible decisions not settled by repository evidence, prior decisions, or reversible defaults.
- Each current batch is sent through one native OpenCode `question` call with readable Russian cards, options, and consequences. Answers trigger fresh `DISCOVERY` research and another fresh question review. This cycle has no fixed batch or question limit.
- Only a fresh `PASS_NO_QUESTIONS` tied to latest discovery and cumulative decisions permits a new decomposer to run `RESTAGE` and regenerate the proposal from evidence.
- Accepted RESTAGE closes discovery and questions for that proposal lineage. No question review, `DISCOVERY`, or native `question` call is allowed after it.
- OpenCode/runtime facts are technical discovery: inspect project-owned `.opencode` evidence, query installed version, use current official docs and upstream source/types, then plan bounded implementation-time `opencode serve --pure` verification. Missing local `node_modules`, checked-in runtime catalog, or direct-invocation fixture is not a user blocker by itself.
- Analyst presents the complete RESTAGE proposal and stops for exact `APPROVE <approval-id>`. No task or journal is written before approval.
- Approval binds request, cumulative decisions, terminal discovery/question-review identities, target, ordered stages, boundaries, dependencies, contracts, expected path areas, tests, ordering, approvals, and non-goals.

### Stage planning and review

- `orchestrator-task-planner` is sole analyst-side writer. It writes only `1_orchestrator/<request>/tasks/*.md` and newest-first `planning-issues.md`.
- Planner materializes exactly one approved stage per call. Tasks preserve stage metadata, approval, status, review state, prerequisites, expected paths, tests, validation, and execution record.
- Fresh `orchestrator-plan-reviewer` checks exactly one current stage. `REVISE` returns to fresh planning and review until `PASS`.
- Every stage passes independently, in order, before pair review begins.

### Adjacent-pair consistency

- Fresh `orchestrator-stage-pair-reviewer` checks adjacent pairs in order: `S01+S02`, `S02+S03`, and so on.
- Review covers boundary coverage, dependency direction, contracts, migrations/configuration, expected paths, execution ordering, approvals, non-goals, and test ownership/cases.
- Right-stage correction is preferred.
- Left-stage correction is `MINOR` only with explicit proof that behavior, boundaries, dependencies, paths, contracts, tests, ordering, approvals, and non-goals remain unchanged. It increments revision and invalidates affected reviews.
- Any substantive earlier-stage correction goes only to fresh pinned-Sol `orchestrator-plan-ultra-reviewer` in `BACKTRACK_AUTHORITY` mode. Sol may deny backtracking with a bounded current/right correction or authorize exact amendments and earliest invalidated stage.
- Sol is not used for whole-plan final review. Current stage and adjacent-pair passes are final planning evidence.
- Planner marks tasks `READY/PASS` only after all current stage and pair reviews pass. Analyst never launches implementation.
- Repair statuses are controller transitions, not user blockers: `REVISE`, pair corrections, and Sol decisions continue immediately through planner and fresh review. Malformed or `REJECTED` calls retry same role/mode with complete authoritative payload and exact rejection evidence. A nonterminal status or `Блокер: none` can never produce user-facing restart/replan instructions.

## Reassessment and task safety

- `REASSESS` uses one exact target, authoritative request, and user-declared completed paths.
- `COMPLETE/PASS` tasks are immutable. Gaps become corrective tasks. Obsolete unexecuted tasks may become `SUPERSEDED` within their stage; files are never deleted or renamed.
- Active `IN_PROGRESS` or `BLOCKED` execution must finish before reassessment.
- Task numbers are two-digit and monotonic through `99`.
- Expected product paths are `WORKFLOW_BASE`-relative scope boundaries. Expansion requires designated correction authority.

## Executor invariants

- Executor accepts exactly one `READY`, resumable `IN_PROGRESS`, or explicitly resumed `BLOCKED` task. It rejects `DRAFT`, `SUPERSEDED`, and `COMPLETE`.
- User prepares execution branch. Executor requires non-detached `HEAD` and clean product state, records immutable `START_COMMIT`, and never creates or changes branches.
- Fresh implementation, review, bounded adjustment, and final-review roles run through OpenCode's native task loop.
- Preserve user-owned staged, unstaged, and untracked changes. Never stage, commit, reset, restore, clean, checkout, switch, rebase, merge, stash, push, or rewrite history.
- Trusted build, test, restore, and localhost checks run autonomously. Secrets, deploy, publish, destructive action, unrelated external effects, material product choices, and user-owned overlap require user decision.

## Native harness and communication

- Native OpenCode task invocation and child-session completion provide scheduling. No model-prose parser, recovery plugin, custom state certificate, idle hook, or generated continuation message participates.
- Recovery plugin was removed because it duplicated native task-loop scheduling, added hidden state and continuation behavior, and made correctness depend on plugin lifecycle rather than explicit prompt contracts.
- Live acceptance may normalize at most three consecutive identity-equivalent accepted phase replays caused by model/provider variation; conflicting or nonconsecutive replay remains failure and no replay changes authoritative routing state.
- During autonomous work, a phase update must be followed immediately by the next tool call. Never end a turn with progress-only final text.
- Final text is allowed only for a real user wait, blocker, or completed workflow and states exact next action.
- Primary agents communicate concisely in Russian. Never expose internal prompts, role names, retries, signatures, journals, or handoffs. Approval IDs and control commands are intentionally visible.

## Permissions and installation

- Keep default deny and least privilege. Broad permission rules precede narrower exceptions because last match wins.
- Analyst primary reads no product files and edits nothing. Discovery and review roles are read-only. Planner alone edits analyst task files and journal.
- Implementation role alone edits product files. Executor primary edits only supplied task and execution journal as defined by executor contracts.
- Deny Git mutation everywhere. Never edit `GlobalUsings.cs` unless explicitly requested.
- Installer manages agent files only. It installs current agents, retires known project-owned plugin and single-model files from older releases, and preserves unknown or user-customized files.

## Change process

1. Read `README.md`, this file, and every affected producer/consumer.
2. Update role contracts, permissions, tests, installer behavior, and user docs together; remove superseded rules instead of layering exceptions.
3. Preserve exactly two primaries, pinned model assignments, least privilege, native task-loop semantics, workflow-base semantics, and executor safety.
4. For releases, update `VERSION`, `opencode-agents.py:VERSION`, every agent version marker, and `CHANGELOG.md` together.
5. After any change, run `python3 tests/test-cli.py`, syntax checks, `git diff --check`, temporary installation, `opencode debug config`, and all isolated live-model acceptance tests: `python3 tests/test-analyst-e2e.py`, `python3 tests/test-analyst-questions-e2e.py`, and `python3 tests/test-analyst-replanning-e2e.py`.
6. Obtain independent workflow and permission review before release.

## Repository exclusions

Do not add provider config, credentials, auth/session databases, MCP tokens, `.env`, user source, patches, logs, generated target-repository `1_orchestrator/` artifacts, indexes, manifests, ledgers, snapshots, or hashes.
