# Changelog

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
