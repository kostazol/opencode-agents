# Agent Maintenance Guide

## Scope

This repository versions OpenCode agent prompts. Prompts are executable workflow. Keep roles small, autonomous, least-privileged, self-contained, and understandable from repository files alone.

## Sources of truth

- Primary prompts own orchestration loops and user contracts. Each subagent prompt owns only its role-specific inputs, permissions, procedure, artifact fields, and compact output.
- Exactly four user-facing primary agents exist: `orchestrator-analyst`, `orchestrator-analyst-single-model`, `orchestrator-executor`, and `orchestrator-executor-single-model`. Do not add aliases, compatibility primaries, or profile-generated variants.
- Analyst planner owns bounded no-write evidence discovery and model-inheriting task planning; fresh planning reviewer validates repository evidence and plan quality; standard analyst adds independent Sol ultra plan review. Executor support roles own model-inheriting implementation and review; standard executor uses Terra adjustment and final review or loop diagnosis, while single-model reviewer records bounded task corrections itself.
- Each agent file owns only role-specific inputs, permissions, procedure, and compact output.
- Explicit current user instruction outranks prior workflow state. Platform safety constraints always apply.

## Workflow rules

- Analyst creates self-contained task Markdown files under `1_orchestrator/<request>/tasks/` and one separate newest-first planning issue journal. It creates no index, manifest, ledger, hash, checkpoint, or product change.
- Workflow `1_orchestrator` is anchored to immutable OpenCode session working directory, never Git root or a parent directory. Every handoff preserves that workflow base; Git root is only for Git-state inspection. Nested-cwd execution maps Git-root-relative status paths through a canonical product prefix, excludes only the exact workflow `1_orchestrator` prefix, and treats outside-base paths as user-owned overlap.
- Every task is a working vertical slice. It may name ordered prerequisite task paths, expected product paths, acceptance criteria, implementation and integration evidence, test work, and validation commands.
- Planner `CREATE` completes bounded acceptance-first repository evidence discovery before decomposition or any write. Evidence blockers leave target absent. Planning reviewer validates task evidence directly against repository source.
- Standard analyst runs on user-selected Terra and adds fresh independent Sol review after model-inheriting plan review PASS; every Sol finding returns through fresh planning and review before another Sol review. Single-model analyst dispatches only model-inheriting roles and has no Sol review.
- Every planning reviewer exhaustively reviews the whole current plan and returns all independent demonstrated actionable findings in one dependency-first, high-impact batch. Each signature keeps independent occurrence and progress counts. Planner validates the complete batch, applies all mutually compatible bounded corrections in one revision, and records one newest-first planning issue entry per finding.
- Repairable plan-internal findings at occurrences `1` through `3`, including ordering, dependency, test ownership, path allocation, decomposition, and buildability, always return through planning revision. First occurrence has progress `NOT_APPLICABLE`; occurrences `2` and `3` with `NONE` require a materially different correction. `BLOCKED` requires access, safety, unresolved user-visible product choice, or occurrence `4` or greater.
- After every valid planner `CREATE` or `REVISE` pass, analyst dispatches the required fresh reviewer immediately in the same user turn. Incomplete review, many distinct findings or cycles, elapsed time, context growth, and voluntary model or tool budgeting never justify yielding, asking the user to repeat/continue/restart, or synthesizing a blocker.
- Planner rejects malformed or contradictory mode input, target collisions, and incompatible review batches without edits. Rejection is never a user blocker: analysts retry bounded malformed planner calls, return rejected revisions to fresh review, restart rejected finalization review chains, and advance deterministic `-2`, `-3`, ... target suffixes after rejected creation collisions without inspecting workflow directories.
- Reviewers and planner enumerate existing workflow artifacts from the exact supplied target directory so Git-ignore rules cannot hide task files from base-root globbing.
- Executor accepts exactly one task file. User prepares and selects execution branch. Executor never creates or changes branches and never stages or commits.
- Executor requires `HEAD` and product worktree clean at start; workflow-owned `1_orchestrator/**` changes are allowed. It records immutable `START_COMMIT` after preflight.
- Fresh implementation and ordinary-review roles alternate. Standard executor runs on user-selected Luna, sends findings through Terra adjuster before repair, and requires Terra final review to complete. Single-model reviewer records bounded task corrections and approved path expansion before fresh implementation; single-model executor completes after reviewer PASS.
- Same demonstrated execution finding gets at most three ordinary repair attempts. Standard executor then invokes Terra loop diagnosis; single-model executor blocks. Different execution findings may continue only while measurable progress occurs. Any Terra finding returns through adjuster, fresh executor, and fresh ordinary reviewer before another Terra final review.
- Standard build, test, restore, and localhost test activity runs autonomously in trusted repositories. Secret use, deploy, publish, destructive action, unrelated external effect, material product choice, and overlap with user-owned changes require user decision.
- Preserve user-owned staged, unstaged, and untracked changes. Never stage, commit, reset, restore, clean, checkout, switch, rebase, merge, stash, push, or rewrite history.
- Report concise Russian phase updates. Never expose journals, finding IDs, internal handoffs, or other workflow internals to user; analyst may return task paths and executor may repeat supplied task path.

## Permissions

- Keep default deny and grant least privilege. Put broad permission rules before narrower exceptions because last match wins.
- Git read-only inspection may be allowed. Deny all Git mutation in permissions and prompts.
- Analyst roles write only `1_orchestrator/**/*.md`. They do not edit product files or Git state.
- Only implementation role edits product files; it cannot edit `1_orchestrator/**`. Executor primary records factual execution status in supplied task. No executor-side role may edit another task or planning journal.
- Planning reviewer, standard ordinary reviewer, Terra adjuster, single-model ordinary reviewer, and Terra final reviewer do not edit product files. Standard reviewers are read-only; planner records planning findings, Terra adjuster and single-model ordinary reviewer may edit only supplied task and its execution journal.
- Standard trusted build, test, restore, and localhost commands may be allowed. Deny secret-bearing commands, deployment, publication, destructive commands, and unrelated external effects pending user approval.

## Change process

1. Read `README.md`, this file, and every affected agent.
2. Identify every producer and consumer of changed task fields, issue fields, verdicts, and permissions.
3. Keep one responsibility per role; update every producer and consumer of a changed contract and remove superseded rules rather than layering exceptions.
4. Verify exactly four primaries, model assignments, least-privilege permissions, autonomous command boundaries, and response contracts.
5. Run `python3 tests/test-cli.py`, syntax checks, `git diff --check`, temporary installation, and `opencode debug config`.
6. Obtain independent workflow and permission review before release.

## Text and versioning

- Preserve UTF-8, LF line endings, and final-newline state. Do not add credentials or secret values.
- Update `VERSION`, `opencode-agents.py:VERSION`, every agent version marker, and `CHANGELOG.md` together for release changes.
- Major version: incompatible installation or workflow change. Minor: compatible capability. Patch: compatible correction.

## Repository exclusions

Do not add provider config, auth/session databases, MCP tokens, `.env`, user source, patches, logs, or generated target-repository `1_orchestrator/` artifacts to this repository. Approved repository-local plans remain allowed.
