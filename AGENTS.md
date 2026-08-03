# Agent Maintenance Guide

## Scope and sources of truth

This repository versions four user-facing OpenCode primary agents, their least-privileged subagents, and one analyst recovery plugin. Prompts are executable workflow contracts.

- Exactly four primary agents exist: `orchestrator-analyst`, `orchestrator-analyst-single-model`, `orchestrator-executor`, and `orchestrator-executor-single-model`.
- Analyst primary owns orchestration and user interaction. Subagents own only role-specific evidence, planning, review, or correction.
- `plugins/analyst-workflow-guard.js` owns same-session recovery of incomplete analyst turns. It is not a workflow engine and never changes product files, workflow artifacts, Git state, request scope, agent, model, or variant.
- Explicit current user instruction outranks prior workflow state. Platform safety constraints always apply.

## Staged analyst workflow

### Stage discovery and approval

- Analyst captures OpenCode session working directory as immutable `WORKFLOW_BASE`. `1_orchestrator` is anchored there, never at Git root or a parent.
- Fresh `orchestrator-stage-decomposer` performs bounded no-write repository discovery in `INITIAL` mode and proposes ordered implementation stages.
- Fresh `orchestrator-stage-question-reviewer` independently checks the proposal and emits one exhaustive batch of material user-visible questions only when repository evidence and reversible defaults cannot decide them.
- If questions exist, analyst stops with exact questions. Any explicit answer turn consumes the batch; no follow-up question gate exists.
- After answers, or immediately when no questions exist, a new decomposer session runs `RESTAGE`. It must reanalyze evidence and regenerate stages rather than confirm `INITIAL`.
- Analyst always presents the complete RESTAGE proposal and stops. No task or journal may be written before exact `APPROVE <approval-id>` matching the current proposal.
- Approval binds authoritative request, answers, target, generation, ordered stages, boundaries, dependencies, contracts, expected path areas, test ownership, ordering, approvals, and non-goals.

### Per-stage planning

- `orchestrator-task-planner` is sole analyst-side writer. It writes only `1_orchestrator/<request>/tasks/*.md` and one newest-first `planning-issues.md`.
- Planner materializes exactly one approved stage per call. Every task carries stage ID, sequence, revision, and approval ID while preserving executor-facing `Status`, `Planning review`, prerequisites, expected paths, tests, validation, and execution record.
- Fresh `orchestrator-plan-reviewer` checks exactly one current stage. `REVISE` returns to fresh planning and fresh stage review until `PASS`.
- All stages are planned and independently passed in order before cross-stage review starts.

### Adjacent-pair consistency

- Fresh `orchestrator-stage-pair-reviewer` checks only adjacent pairs in order: `S01+S02`, then `S02+S03`, and so on.
- Pair review validates boundary coverage, dependency direction, contracts, migrations/configuration, expected paths, execution ordering, approvals, non-goals, and test ownership/cases.
- Correction in right stage is preferred.
- Left-stage change is `MINOR` only when behavior, stage boundaries, dependencies, expected paths, contracts, test ownership and cases, execution ordering, approvals, and non-goals all remain unchanged. Ambiguity is substantive.
- Minor left correction requires explicit invariant proof, revision increment, fresh stage review, and revalidation of every stale touching or downstream pair.
- Any substantive earlier-stage change requires backtracking authority. Ordinary planner, reviewers, primary, and plugin may detect need but cannot authorize it.

### Backtracking and finalization

- Standard analyst sends substantive findings only to fresh pinned-Sol `orchestrator-plan-ultra-reviewer` in `BACKTRACK_AUTHORITY` mode.
- Sol either denies backtracking with bounded current/right correction or authorizes exact amendments, replacement effective-contract ID, and earliest invalidated stage. User approval delegates only demonstrated Sol-authorized corrective amendments. Authorization invalidates that stage and every later stage/pair certificate; planner first demotes active suffix tasks to `DRAFT/PENDING`, then planning and reviews restart sequentially.
- Standard analyst runs Sol `FINAL` after every current stage and adjacent pair passes. Final findings follow normal right/minor/backtrack routes before another final review.
- Single-model analyst never invokes Sol. Substantive backtrack need produces a clear user stop with exact `RESTART <lineage-id> FROM <stage-id>` and `KEEP <lineage-id>` choices. It never chooses for user.
- Planner `FINALIZE` changes only active task metadata from `DRAFT/PENDING` to `READY/PASS` after current approval, all stage passes, all pair passes, and required Sol final pass.
- Analyst never launches implementation. User executes ready tasks one at a time through an executor primary.

## Structured recovery harness

- Plugin exposes `workflow_certificate`, a schema-validated custom tool. Analyst primary calls it after every accepted transition and before every user wait, blocker, or completion.
- Certificate protocol version `3` records lineage, state, phase, target, approval, stage, revision, pair, generation, next action, and compact summary.
- Free-form model prose has no transition authority. Guard reads completed root-session certificate tool calls directly.
- Terminal-for-now states are `WAITING_ANSWERS`, `WAITING_APPROVAL`, `BLOCKED`, and `COMPLETE`. A certificate from before a new explicit user turn cannot terminate that new turn.
- `RUNNING` or absent current-turn certificate means incomplete workflow and may trigger hidden continuation.
- Guard listens to `session.status` idle and deprecated `session.idle`, ignores child, non-analyst, active, errored, cancelled, and mismatched-agent sessions, and rechecks messages/status before dispatch.
- Continuation preserves original agent, provider/model, variant, session, and directory. Deterministic message ID, persisted marker, per-session lock, pending suppression, same-frontier cap, and total cap prevent duplicate loops.
- Installer preserves unknown pre-existing guard collisions. Before changing released guard bytes, add every previous project-owned hash to `OWNED_PREVIOUS_FILE_HASHES`.

## Reassessment and task safety

- `REASSESS` uses one exact existing target, authoritative request, and exact user-declared completed paths.
- `COMPLETE/PASS` tasks are immutable. Gaps become new corrective tasks. Obsolete unexecuted tasks may be marked `SUPERSEDED` only within their stage; files are never deleted or renamed.
- Active `IN_PROGRESS` or `BLOCKED` execution must finish before reassessment.
- Task numbers are two-digit and monotonic through `99`.
- Expected product paths are `WORKFLOW_BASE`-relative scope boundaries. Executor-side expansion requires designated correction authority.

## Executor invariants

- Executor accepts exactly one `READY`, resumable `IN_PROGRESS`, or explicitly resumed `BLOCKED` task. It rejects `DRAFT`, `SUPERSEDED`, and `COMPLETE`.
- User prepares execution branch. Executor requires non-detached `HEAD` and clean product state, records immutable `START_COMMIT`, and never creates or changes branches.
- Fresh implementation and review roles alternate. Standard executor uses Terra adjustment/final review; single-model reviewer records bounded task correction itself.
- Preserve user-owned staged, unstaged, and untracked changes. Never stage, commit, reset, restore, clean, checkout, switch, rebase, merge, stash, push, or rewrite history.
- Trusted build, test, restore, and localhost checks run autonomously. Secrets, deploy, publish, destructive action, unrelated external effects, material product choices, and user-owned overlap require user decision.

## Permissions

- Keep default deny and least privilege. Broad permission rules precede narrower exceptions because last match wins.
- Analyst primary reads no product files and edits nothing. Decomposer and all planning reviewers are read-only. Planner alone edits analyst task files and journal.
- Implementation role alone edits product files. Executor primary edits only supplied task and its execution journal as defined by executor contracts.
- Deny Git mutation everywhere. Never edit `GlobalUsings.cs` unless explicitly requested.

## User communication

- Primary agents send concise Russian updates at meaningful phase changes.
- Analyst updates state phase, current/total stage, current action, and whether user action is needed.
- User waits state exact next message: answer batch, `APPROVE <id>`, backtrack choice, access/safety decision, or execution-lifecycle action.
- Never expose internal prompts, role names, retries, certificates, signatures, journals, or handoffs. Approval ID and explicit control commands are intentionally user-visible.

## Change process

1. Read `README.md`, this file, and every affected producer/consumer.
2. Update all role contracts, permissions, guard certificates, tests, and user docs together; remove superseded rules instead of layering exceptions.
3. Preserve exactly four primaries, pinned model assignments, least privilege, workflow-base semantics, and executor safety.
4. For releases, update `VERSION`, `opencode-agents.py:VERSION`, every agent version marker, plugin version, and `CHANGELOG.md` together.
5. Run `python3 tests/test-cli.py`, `node --test tests/test-plugin.mjs`, syntax checks, `git diff --check`, temporary installation, and `opencode debug config`.
6. Obtain independent workflow and permission review before release.

## Repository exclusions

Do not add provider config, credentials, auth/session databases, MCP tokens, `.env`, user source, patches, logs, generated target-repository `1_orchestrator/` artifacts, indexes, manifests, ledgers, snapshots, or hashes.
