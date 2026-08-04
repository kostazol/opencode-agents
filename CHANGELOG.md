# Changelog

## 5.0.0 - 2026-08-04

### Changed

- Replace the previous analyst/executor network with four planning-only `orchestrator-*` agents: analyst, discovery, stage planner, and stage reviewer.
- Make `plan.md` a durable table of contents and plan/review exactly one stage before advancing to the next stage.
- Add resumable `RUN` and one-transition `STEP` modes backed by readable discovery, question, stage, and review artifacts.
- Consolidate repository research and material question formation in one fresh discovery role with concise positive prompts.
- Retire known unmodified 4.1.1 agent files during update while preserving customized files.

### Removed

- Remove execution agents, pair review, Sol backtrack authority, task files, planning journals, lineage IDs, generation IDs, approval hashes, and verbatim handoff contracts.

## 4.1.1 - 2026-08-04

### Fixed

- Treat stage, pair, and Sol corrective statuses as immediate native-loop controller transitions instead of user-facing restart or replan blockers.
- Rebuild malformed and `REJECTED` retries from complete authoritative state with exact rejection evidence; forbid summary-only repair handoffs.
- Add isolated live-model replanning acceptance covering `REVISE`, `REVISE_STAGE`, fresh revision review, and `FINALIZE` without executor calls, synthetic turns, or product writes.
- Make live acceptance fail fast on fatal provider/child-task errors, use async initial prompts, and enforce bounded no-progress and total timeouts.
- Align live harness isolation with OpenCode smoke-test flags, use session-scoped V2 question APIs and V2 wait with documented legacy fallback, and emit per-phase timing/token telemetry.

## 4.1.0 - 2026-08-03

### Changed

- Replace one-shot clarification with an unbounded pre-RESTAGE cycle: native current-batch questions, fresh `DISCOVERY` research after answers, and fresh question review.
- Gate RESTAGE on terminal `PASS_NO_QUESTIONS` tied to latest discovery and cumulative decisions; close all discovery and questions after accepted RESTAGE.
- Add separate discovery, question-review, and batch identities without reusing post-approval generation semantics.
- Extend native-question live-model acceptance to one answer, additional discovery, a second two-question batch, terminal review, approval, and full planning finalization.
- Let discovery/planning roles resolve OpenCode runtime contracts from project-owned `.opencode` evidence, exact installed version, official docs, and upstream source/types; missing local SDK artifacts no longer create a user blocker.

## 4.0.0 - 2026-08-03

### Changed

- **Breaking:** reduce public surface to exactly two primary agents: `orchestrator-analyst` and `orchestrator-executor`; remove single-model variants.
- Make OpenCode's native agentic task loop the sole runtime harness. Remove recovery plugin, custom workflow certificates, idle recovery, and synthetic continuation.
- Keep analyst orchestration on fresh subagents, one native `question` batch, exact approval, per-stage review, and ordered adjacent-pair review.
- Invoke pinned Sol only as authority for demonstrated substantive backtracking; remove whole-plan Sol final review.
- Forbid progress-only final text during autonomous work; phase updates must continue immediately with the next tool call.
- Add mandatory isolated live-model analyst acceptance test covering approval, revision-1 two-stage and pair reviews without `REVISE`, finalization, and absence of executor calls or synthetic turns.
- Add native-question live-model acceptance covering three user decisions, two-to-three-stage RESTAGE expansion, adjacent-pair coordination, and final three-task readiness.
- Preserve executor's one-task, clean-worktree, non-detached-HEAD, no-Git-mutation flow with fresh implementation and review roles.
- Make installation agents-only. Retire known project-owned old plugin and single-model files while preserving unknown and customized files.

### Removed

- Remove plugin lifecycle as workflow infrastructure because it duplicated native scheduling, introduced hidden recovery state, and made workflow correctness depend on synthetic messages instead of explicit agent contracts.

## 3.0.1 - 2026-08-03

### Fixed

- Ask reviewed material decisions through one native OpenCode `question` batch with readable Russian wording, detailed option consequences, recommendations, and custom answers instead of caveman-compressed prose.
- Keep autonomous analyst work in the same root turn: a `RUNNING` certificate now requires immediate next-tool dispatch and progress text cannot terminate work.
- Treat repeated question waits as controller-owned interaction state instead of inferring that every user message answered the question.
- Make recovery fail closed without a current `RUNNING` certificate and cap synthetic continuations to two per explicit user turn so the plugin remains an emergency path.

## 3.0.0 - 2026-08-02

### Changed

- **Breaking:** replace monolithic analyst planning with fresh decomposition, independent question review, mandatory RESTAGE analysis, and explicit stage approval before any task write.
- Plan and independently review one approved stage at a time, then validate adjacent stage pairs in order with right-side correction preferred.
- Restrict left-stage edits to proven minor changes; route substantive backtracking through Sol authority in standard workflow and explicit user choice in single-model workflow.
- Replace free-form terminal-response parsing with schema-validated `workflow_certificate` tool calls and a certificate-driven OpenCode recovery guard.
- Preserve agent, model, and variant on recovery; support `session.status` idle plus compatibility `session.idle`, deterministic continuation IDs, persisted deduplication, and stage-aware progress frontiers.
- Expand user-facing Russian phase updates with current stage, active action, stop reason, and exact next user command.

### Added

- Add dedicated decomposer, question reviewer, and adjacent-pair reviewer subagents.
- Add stage identity, revision, sequence, and approval metadata to analyst task files while preserving executor contracts.

## 2.4.1 - 2026-08-02

### Fixed

- Preserve analyst task-tool handoffs as lossless protocol data instead of caveman-compressed summaries, aliases, absolute paths, or omitted upstream responses.
- Make analyst primary own compact canonical workflow state, retire superseded stage outputs, diagnose controller versus subagent degradation, and correct fresh role prompts without shifting internal failures to user.
- Count planning finding recurrence only for the same concrete defect so newly discovered omitted paths do not create false fourth-occurrence blockers.
- Keep explicit follow-up turns after a reported blocker under user control until planner or reviewer work starts, preventing guard repetition after informational answers.

## 2.4.0 - 2026-08-02

### Added

- Reassess existing partially implemented plans against completed task evidence and current repository state without creating a suffixed replacement target.
- Support independently reviewed progressive planning checkpoints through `PARTIAL_READY` when implementation must produce evidence required for later planning.
- Preserve completed tasks as immutable history, supersede obsolete unexecuted tasks, and create corrective tasks for demonstrated gaps in completed outcomes.
- Allow one exhaustive clarification batch after initial evidence discovery and in-memory planning, then keep all resumed planning and review autonomous.

### Changed

- Certify `READY`, `PARTIAL_READY`, and reassessment-only `SATISFIED` outcomes with matching planner, reviewer, partition, uncertainty, and final-response fields.
- Reject draft, superseded, and already complete tasks as executor inputs while preserving the one-task execution contract.

### Fixed

- Restrict analyst workflow guard continuation to sessions whose latest user and assistant messages identify the same supported analyst agent, with an early session-level non-analyst rejection.

## 2.3.1 - 2026-08-02

### Fixed

- Treat a session absent from OpenCode's status map as idle, matching the runtime API that stores only busy and retry sessions.
- Continue incomplete analyst workflows after `session.idle` instead of silently returning before synthetic continuation dispatch.

## 2.3.0 - 2026-08-02

### Added

- Install an auto-discovered runtime plugin that resumes prematurely idle analyst workflows in the same session with the original agent and model.
- Require matching final parent, planner, and fresh-review certificates before the plugin accepts analyst `READY` or `BLOCKED` completion.
- Persist synthetic continuation markers and enforce duplicate, no-progress, total-attempt, child-session, cancellation, error, and active-session guards.

### Changed

- Install and update project-owned JavaScript plugins alongside agent prompts while preserving unknown user plugins.

## 2.2.1 - 2026-08-02

### Fixed

- Normalize semantically complete singular, unnumbered, and imperfectly numbered plan-review findings before planner revision.
- Preserve reviewer output verbatim through revision and recover rejected planner handoffs from readable current task files without requiring unavailable planner PASS metadata.
- Treat metadata-only reviewer blocking and presentation-only planner rejection as malformed internal workflow responses that must retry without yielding to the user.

## 2.2.0 - 2026-08-02

### Changed

- Batch every independent actionable plan-review finding into one exhaustive dependency-first review response and one bounded planner revision.
- Keep analyst review loops running in the same user turn until reviewed tasks are ready or a defined workflow blocker occurs.
- Discover ignored workflow artifacts through exact target-directory glob and read operations.
- Raise both analyst primary action budgets to 200 steps.
- Return edit-free planner `REJECTED` results for invalid input, incompatible review batches, and target collisions, with autonomous analyst recovery paths.
- Keep immediate blockers separate from finding occurrence fields and resolve planner-detected request-slug collisions through deterministic suffix retries.

## 2.1.0 - 2026-08-02

### Changed

- Fold bounded no-write reconnaissance into planner `CREATE`, removing one analyst handoff while preserving acceptance-first evidence discovery.
- Require fresh plan reviewer to validate task evidence directly against repository source.
- Define mode-specific planner inputs for `CREATE`, `REVISE`, `BLOCK`, and `FINALIZE`.
- Back up and remove retired project-owned `orchestrator-recon.md` during update while preserving user agents.

## 2.0.0 - 2026-08-02

### Changed

- **Breaking:** Rename workflow artifact directory from `.orchestrator` to non-hidden `1_orchestrator` so OpenCode glob discovery does not omit it.
- Support only `1_orchestrator` workflow artifacts; no compatibility or migration path is provided.

## 1.2.3 - 2026-08-02

### Fixed

- Treat the future analyst planning target as routing metadata that is expected to be absent before planner creation.
- Prevent reconnaissance from reading or blocking on absent planning artifacts, with one corrected retry for malformed responses.

## 1.2.2 - 2026-08-01

### Fixed

- Anchor workflow `.orchestrator` artifacts to OpenCode session working directory instead of Git root or parent directories.
- Preserve the same workflow base across planning, review, execution, adjustment, and final review handoffs.

## 1.2.1 - 2026-08-01

### Fixed

- Route repairable plan ordering, dependency, test-ownership, and buildability findings through revision instead of terminal blocking.
- Treat first occurrence of every planning finding as not applicable for progress accounting.
- Require materially different corrections for no-progress occurrences two and three, then block occurrence four or greater regardless reviewer verdict.
- Restrict immediate planning blockers to access, safety, and unresolved user-visible product choices.

## 1.2.0 - 2026-08-01

### Added

- Separate single-model analyst and executor primary workflows without Sol or Terra final review roles.

### Changed

- Planning and plan review inherit caller model selection.
- Standard executor uses Terra task adjustment; single-model reviewer records its own bounded task corrections without a separate adjuster.

## 1.1.0 - 2026-08-01

### Added

- Independent Sol ultra plan review after Terra plan review PASS.
- Bounded Terra planning and review rerun after every Sol plan finding before another Sol review.

## 1.0.1 - 2026-08-01

### Fixed

- Keep planning roles self-contained and prevent obsolete global-protocol reads.
- Require exact paths for task reads and compatible grep patterns during planning.

## 1.0.0 - 2026-08-01

### Added

- Exactly two primary agents: `orchestrator-analyst` and `orchestrator-executor`.
- Read-only reconnaissance for implementation, integration, existing-test, and test-prototype evidence.
- Terra task planning into self-contained vertical-slice Markdown files under `.orchestrator/<request>/tasks/`.
- Fresh independent Terra plan review with bounded repeated-finding diagnosis.
- One-task execution through fresh implementation and ordinary-review sessions.
- Terra task adjustment, expected-path expansion authority, final review, and repair-loop diagnosis.
- Newest-first planning and execution issue journals optimized for reading only recent findings.
- Autonomous trusted build, test, restore, and localhost validation without Git mutation.
- Self-contained role prompts without runtime shared-protocol dependency.

### Safety

- User prepares execution branch; agents never create, switch, stage, commit, rewrite, or push Git state.
- Product worktree must be clean at execution start; `.orchestrator/**` remains workflow-owned.
- Secret files, production credentials, deployment, publication, destructive actions, and unrelated external effects remain outside autonomous scope.
