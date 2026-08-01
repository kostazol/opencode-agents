# Agent Maintenance Guide

## Scope

This repository versions OpenCode agent prompts and shared protocol. Prompts are executable workflow. Keep roles small, autonomous, least-privileged, and understandable from repository files alone.

## Sources of truth

- `protocols/orchestrator.md` owns shared workflow, artifact schemas, retry rules, safety gates, progress, and response contracts.
- Exactly two user-facing primary agents exist: `orchestrator-analyst` and `orchestrator-executor`. Do not add aliases, compatibility primaries, or profile-generated variants.
- Analyst support roles own reconnaissance, Terra task planning, and independent Terra plan review. Executor support roles own implementation, ordinary review, Terra adjustment, and Terra final review or loop diagnosis.
- Each agent file owns only role-specific inputs, permissions, procedure, and compact output.
- Explicit current user instruction outranks prior workflow state. Platform safety constraints always apply.

## Workflow rules

- Analyst creates self-contained task Markdown files under `.orchestrator/<request>/tasks/` and one separate newest-first planning issue journal. It creates no index, manifest, ledger, hash, checkpoint, or product change.
- Every task is a working vertical slice. It may name ordered prerequisite task paths, expected product paths, acceptance criteria, implementation and integration evidence, test work, and validation commands.
- Terra performs planning. A fresh, independent Terra role reviews every task set before analyst returns task paths.
- Executor accepts exactly one task file. User prepares and selects execution branch. Executor never creates or changes branches and never stages or commits.
- Executor requires `HEAD` and product worktree clean at start; workflow-owned `.orchestrator/**` changes are allowed. It records immutable `START_COMMIT` after preflight.
- Fresh implementation and ordinary-review roles alternate. Terra adjuster converts findings into bounded task corrections and approves any expected-path expansion before product edits. Terra final reviewer alone can complete task.
- Same demonstrated finding gets at most three ordinary repair attempts before Terra loop diagnosis. Different findings may continue only while measurable progress occurs. Any Terra finding returns through adjuster, fresh executor, and fresh ordinary reviewer before another Terra final review.
- Standard build, test, restore, and localhost test activity runs autonomously in trusted repositories. Secret use, deploy, publish, destructive action, unrelated external effect, material product choice, and overlap with user-owned changes require user decision.
- Preserve user-owned staged, unstaged, and untracked changes. Never stage, commit, reset, restore, clean, checkout, switch, rebase, merge, stash, push, or rewrite history.
- Report concise Russian phase updates. Never expose journals, finding IDs, internal handoffs, or other workflow internals to user; analyst may return task paths and executor may repeat supplied task path.

## Permissions

- Keep default deny and grant least privilege. Put broad permission rules before narrower exceptions because last match wins.
- Git read-only inspection may be allowed. Deny all Git mutation in permissions and prompts.
- Analyst roles write only `.orchestrator/**/*.md`. They do not edit product files or Git state.
- Only implementation role edits product files; it cannot edit `.orchestrator/**`. Executor primary records factual execution status in supplied task. No executor-side role may edit another task or planning journal.
- Planning reviewer, ordinary reviewer, Terra adjuster, and Terra final reviewer do not edit product files. Reviewers are read-only; planner records planning findings, and adjuster may edit only supplied task and its execution journal.
- Standard trusted build, test, restore, and localhost commands may be allowed. Deny secret-bearing commands, deployment, publication, destructive commands, and unrelated external effects pending user approval.
- Shared protocol consumers use `__OPENCODE_PROTOCOL_DIRECTORY_PATH_YAML__`, `__OPENCODE_PROTOCOL_PATH_YAML__`, and `__OPENCODE_PROTOCOL_PATH_TEXT__`. Do not commit installed paths.

## Change process

1. Read `README.md`, this file, protocol, and every affected agent.
2. Identify every producer and consumer of changed task fields, issue fields, verdicts, and permissions.
3. Keep one responsibility per role; update shared protocol once and remove superseded rules rather than layering exceptions.
4. Verify exactly two primaries, model assignments, least-privilege permissions, autonomous command boundaries, and response contracts.
5. Run `python3 tests/test-cli.py`, syntax checks, `git diff --check`, temporary installation, and `opencode debug config`.
6. Obtain independent workflow and permission review before release.

## Text and versioning

- Preserve UTF-8, LF line endings, and final-newline state. Do not add credentials or secret values.
- Update `VERSION`, `opencode-agents.py:VERSION`, every agent version marker, and `CHANGELOG.md` together for release changes.
- Major version: incompatible installation or workflow change. Minor: compatible capability. Patch: compatible correction.

## Repository exclusions

Do not add provider config, auth/session databases, MCP tokens, `.env`, user source, patches, logs, or generated target-repository `.orchestrator/` artifacts to this repository. Protocol examples and approved repository-local plans remain allowed.
