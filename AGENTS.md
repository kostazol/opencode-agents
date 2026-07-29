# Agent Maintenance Guide

## Scope

This repository versions OpenCode agent prompts and shared protocols. Treat prompt changes as executable workflow changes: review permissions, state transitions, artifacts, and failure paths with the same care as application code.

## Sources of truth

- `protocols/orchestrator-v2.md` owns shared workflow invariants, IDs, gates, handoff schemas, and final-state rules.
- Each file under `agents/` owns only its role, permissions, modes, procedure, and compact response contract.
- Agent frontmatter must remain valid OpenCode configuration.
- Explicit user instructions and platform safety constraints outrank repository prototypes.

## Change process

1. Read `README.md`, this file, the shared protocol, and every directly affected agent.
2. Identify all producers and consumers of changed states, IDs, artifacts, modes, and response fields.
3. Prefer updating the shared protocol once over duplicating the same rule across role prompts.
4. Keep role prompts action-oriented: inputs, gates, procedure, output, terminal states.
5. Use positive gate language. Keep explicit prohibitions only for security, secrets, product ownership, reviewer independence, and Git history/index safety.
6. Preserve role separation and least-privilege permissions.
7. Run configuration validation after installation and obtain an independent prompt review before release.

## Prompt size

- Store source and test prototypes as `path#symbol` references; do not copy code bodies into prompts or artifacts.
- Keep examples to one canonical schema when necessary.
- Remove superseded rules instead of appending corrections.
- Keep full logs, plans, patches, and evidence in workflow artifacts; agent responses return paths, IDs, verdicts, and decisive blockers.
- Avoid repeating protocol text in every role prompt.

## Model policy

- Pin Terra only for `planner-senior-caveman` and `final-reviewer-caveman` unless an explicit design decision changes this policy.
- Leave bootstrap, cheap planner, executor, validator, mini reviewer, and aggregator model-agnostic so they inherit the selected/default model.
- Model changes require rationale in `CHANGELOG.md`.

## Orchestrator invariants

- Baseline capture precedes product mutation.
- `.gitignore` setup remains an explicit, attributable product change.
- Read-only recon precedes prototype baseline validation.
- Every product-mutating stage is sequential and ends buildable/testable.
- Exact prototype gate runs before every dispatch.
- Review starts only after readiness PASS.
- Parallel mini reviewers share immutable inputs and unique lane IDs.
- Aggregation preserves source findings before deduplication.
- Repairs regenerate affected validation and content IDs.
- Final repair restarts complete final validation and cumulative mini review.
- Terra PASS reaches completion only after post-review identity confirmation.
- Repository history and user index remain unchanged.

## Cross-file checks

When adding or changing a mode, state, ID, or artifact, verify:

- producer agent;
- consumer agent;
- orchestrator transition;
- protocol definition;
- permission to read/write exact path;
- response enum compatibility;
- stale and failure behavior;
- retry budget and terminal state;
- identity invalidation and recomputation.

## Permissions

- Keep wildcard denial before specific allows because OpenCode applies the last matching rule.
- Shared protocol consumers need explicit `external_directory` access to `/home/kostaz/.config/opencode/protocols/orchestrator-v2.md`.
- Reviewers may write only their supplied review artifact class.
- Planner agents do not implement or run tests.
- ID ownership follows protocol: bootstrap owns request/initial IDs, validator owns plan/product/evidence/review-input IDs, aggregator owns mini/final-review IDs, and planner agents only consume them.
- Hidden workflow subagents remain callable by orchestrator but are less likely to be invoked directly.

## Validation

Install or synchronize changed files into `~/.config/opencode/`, then run:

```bash
opencode debug config >/dev/null
```

Verify every modified text file:

- UTF-8;
- LF line endings unless the original requires otherwise;
- preserve each existing file's final-newline state;
- new files use one final newline and no additional blank line at EOF;
- no credentials or secret values.

Independent review must return no required correctness or operability findings before version release.

## Versioning

- Update `VERSION` for released configuration changes.
- Update `CHANGELOG.md` with behavior, compatibility, and migration notes.
- Use semantic versions:
  - major: incompatible protocol/state/installation change;
  - minor: backward-compatible workflow or agent capability;
  - patch: clarification or defect correction without contract expansion.
- Tag released commits as `v<VERSION>`.

## Repository exclusions

Do not add:

- `opencode.json` or provider configuration;
- auth/session/account databases;
- MCP tokens or environment files;
- `.env` files;
- tool output;
- project `.orchestrator/` workflow artifacts;
- user repository source, patches, or validation logs.
