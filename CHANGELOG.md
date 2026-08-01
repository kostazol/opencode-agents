# Changelog

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
