# Replace orchestration with analyst and executor primaries

## Goal

Replace current workflow with exactly two primary agents: an analyst that produces independently reviewed task files, and an executor that implements and validates exactly one task file without committing Git changes.

## Decisions

- Task artifacts live under `.orchestrator/<request>/` in target repositories.
- Analyst emits only self-contained task files; no index or manifest.
- Tasks may declare ordered prerequisite task files and must remain working vertical slices.
- User prepares each execution branch; executor does not create branches or commits.
- Product worktree must be clean at executor start except workflow-owned `.orchestrator/**` files.
- Task scope uses expected paths. Terra adjuster must approve and record scope expansion before executor changes new paths.
- Standard build, test, restore, and localhost test commands may run autonomously in trusted repositories. Secrets, deployment, publication, and unrelated external effects remain denied.
- Planning and execution findings use newest-first issue journals. Ordinary agents read only the latest one or two entries unless loop diagnosis requires full history.
- Repeated identical finding receives up to three ordinary repair attempts. Terra performs loop diagnosis after recurrence and either provides a concrete correction or blocks. Different demonstrated findings may continue.
- Final Terra finding returns to adjuster, fresh executor, and ordinary reviewer. Final Terra reruns after ordinary reviewer PASS.
- Old primary agents and compatibility paths are removed without aliases or migration behavior.

## Task 1 — Define protocol and roles

- [x] Replace repository workflow rules and shared protocol with analyst/executor contracts.
- [x] Define task-file and newest-first issue-journal schemas.
- [x] Define branch preflight, dependency, repair-loop, final-review, and completion gates.
- Expected paths: `AGENTS.md`, `protocols/orchestrator.md`.

## Task 2 — Implement analyst primary

- [x] Add `orchestrator-analyst` primary.
- [x] Adapt reconnaissance for implementation, integration, existing-test, and test-prototype discovery.
- [x] Add Terra task planner and independent Terra plan reviewer.
- [x] Restrict writes to `.orchestrator/**/*.md`; deny product and Git mutation.
- Expected paths: `agents/orchestrator-analyst.md`, `agents/orchestrator-recon.md`, `agents/orchestrator-task-planner.md`, `agents/orchestrator-plan-reviewer.md`.

## Task 3 — Implement executor primary

- [x] Make `orchestrator-executor` primary accepting exactly one task MD.
- [x] Add model-inheriting task executor and task reviewer.
- [x] Add Terra task adjuster and Terra final reviewer with loop-diagnosis mode.
- [x] Permit product edits only in implementation role; keep reviewers read-only.
- [x] Harden secret patterns and Git diff command permissions.
- Expected paths: `agents/orchestrator-executor.md`, `agents/orchestrator-task-executor.md`, `agents/orchestrator-task-reviewer.md`, `agents/orchestrator-task-adjuster.md`, `agents/orchestrator-final-reviewer.md`.

## Task 4 — Simplify installation and documentation

- [x] Remove template/profile rendering, stage-commit helper integration, and superseded roles.
- [x] Install direct agent files, protocol, and global guidance only.
- [x] Update README and changelog for exactly two primaries and no automatic commits.
- Expected paths: `opencode-agents.py`, `README.md`, `CHANGELOG.md`, `agents/profiles/openai.md`, `agents/profiles/single-model.md`, `agents/orchestrator-main.template.md`, `agents/orchestrator-baseline.md`, `agents/orchestrator-planner.md`, `agents/orchestrator-single-model-planner.md`, `agents/orchestrator-stage-validator.md`, `agents/orchestrator-committer.md`, `agents/orchestrator-validator.md`, `helpers/stage-commit.py`.

## Task 5 — Replace tests and validate

- [x] Assert exactly two primary agents and required subagent model/permission contracts.
- [x] Test direct installation, update preservation of unknown agents, GitHub source, and target safety.
- [x] Test permission behavior for secrets, Git mutation, external diff/write options, separators, standard checks, and localhost commands.
- [x] Run `python3 tests/test-cli.py`, `python3 -m py_compile opencode-agents.py tests/test-cli.py`, `git diff --check`, temporary install, and `opencode debug config`.
- [x] Obtain independent workflow and permission reviews; repair demonstrated findings.
- Expected paths: `tests/test-cli.py`, `tests/test-cli.sh`.
