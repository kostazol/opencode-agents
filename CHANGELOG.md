# Changelog

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
