# Orchestrator Protocol v2

## Goal and architecture

Produce independently reviewed, executable task files and implement exactly one selected task without changing Git history or index.

Exactly two primary agents exist:

- `orchestrator-analyst`: analyze request and return reviewed task paths.
- `orchestrator-executor`: implement and validate one supplied task path.

No compatibility primary, profile variant, automatic commit path, or implicit transition between primaries exists. User chooses task, prepares branch, then invokes executor.

## Authority

1. Platform permissions and safety constraints.
2. Latest explicit user instruction.
3. Repository instructions.
4. Supplied task file and approved amendments.
5. Existing code and executable checks.

Explicit approval authorizes only stated action and scope. Do not infer approval for secret use, destructive or irreversible action, deployment, publication, unrelated external effect, user-owned overlap, or material product behavior.

## Artifact layout

Artifacts live under `.orchestrator/<request>/` in target repository:

```text
.orchestrator/<request>/tasks/<NN>-<slug>.md
.orchestrator/<request>/planning-issues.md
.orchestrator/<request>/tasks/<NN>-<slug>.issues.md
```

Task files ending in `.issues.md` are journals, never execution inputs. `planning-issues.md` is separate planning journal. Each executed task gets one sibling `<task-stem>.issues.md` journal. Do not create an index, manifest, request ledger, hash file, checkpoint, dispatch file, snapshot, or duplicated plan. Artifact paths must remain inside request directory. Existing artifact overlap requires user approval before replacement.

## Task schema

Each task file is self-contained and uses these sections:

```markdown
# Task: <working vertical slice>

- Request: <request slug>
- Task: <stable task name>
- Status: DRAFT|READY|IN_PROGRESS|BLOCKED|COMPLETE
- Planning review: PENDING|PASS

## Goal
<user-visible outcome>

## Acceptance criteria
- <observable criterion>

## Ordered prerequisites
- <task path and required COMPLETE outcome, or none>

## Branch preconditions
- User-prepared, non-detached execution branch.
- Product worktree and index clean except `.orchestrator/**`.
- <dependency or request-supplied base constraints; executor performs no Git mutation>

## Repository context
- Instructions: <paths>
- Implementation prototypes: <path#symbol or none>
- Integration points: <path#symbol or none>
- Existing tests: <path#symbol or none>
- Test prototypes: <path#symbol or none>

## Scope
- Expected product paths: <paths>
- Excluded work: <boundaries>
- Assumptions and decisions: <resolved facts>

## Implementation
- <ordered production and integration work>

## Test work
- <tests to add or change; explicit rationale if behavior truly cannot be automated>

## Validation
- <focused and final commands with expected result>

## Approved scope amendments
- None

## Current repair direction
- None

## Execution record
- START_COMMIT: UNSET
- Result: NOT_STARTED|IN_PROGRESS|PASS|BLOCKED
- Changed product paths: none
- Validation evidence: none
```

Task must contain enough repository evidence and decisions for fresh executor to work without analyst conversation. Every behavior change maps to test work. Missing existing tests is evidence for adding tests, not reason to omit them. Prerequisites must be ordered task paths; each task remains independently buildable and useful as vertical slice. Analyst sets `READY` and planning review `PASS` only after independent review passes.

Executor primary changes only execution fields and status in supplied task. Terra adjuster changes only approved amendments and current repair direction. `START_COMMIT` is full Git commit ID captured once and never rewritten. Adjuster appends each scope amendment with reason, paths, and finding reference before implementation touches any product path outside expected scope.

## Journal schemas

Journals are immutable-entry histories ordered newest first. Insert each entry immediately below journal heading; never rewrite or delete older entries.

Planning journal entries use:

```markdown
## <timestamp> — <signature>
- Occurrence: <N>
- Affected tasks: <paths>
- Finding: <demonstrated defect>
- Disposition: REPAIRED|BLOCKED
- Changes: <exact task corrections or none>
```

Execution journal entries use:

```markdown
## <timestamp> — <FINDING|RESOLVED|DIAGNOSIS|BLOCKED>
- Finding: <stable normalized key>
- Source: <role>
- Cycle: <number>
- Ordinary repair attempt: <0..3>
- Status: OPEN|RESOLVED|BLOCKED
- Evidence: <path#line, command result, or exact contradiction>
- Requirement: <one actionable correction or blocking decision>
- Scope impact: <none or paths requiring adjuster approval>
- Supersedes: <timestamp/finding or none>
```

Planning findings go only to planning journal. Execution, ordinary-review, Terra-review, and diagnosis findings go only to supplied task journal. Finding key remains identical for same unmet requirement and changes for materially different evidence or requirement. Execution resolution is a new `RESOLVED` entry written by executor primary from ordinary-review evidence; older entries remain immutable. Ordinary roles read newest one or two entries by default and may search matching entries when a signature recurs. Terra loop diagnosis may read full journal.

Findings must be demonstrated, task-relevant, and actionable. Style preference, speculative refactor, and unrelated pre-existing issue do not block. User-approved residual risk is recorded and reported, not repeatedly raised unless evidence or platform safety changes.

## Analyst workflow

1. Validate request and choose collision-free request slug. Read repository instructions and inspect relevant product, integration, existing-test, and test-prototype paths without product or Git mutation.
2. Dispatch focused reconnaissance as needed. Resolve material product ambiguity with user; otherwise continue autonomously.
3. Fresh Terra planner writes one or more self-contained tasks and planning journal. It creates no other artifact. Tasks may declare ordered prerequisites.
4. Fresh independent Terra plan reviewer checks request coverage, vertical slicing, dependencies, expected paths, integration, tests, commands, safety, and self-containment.
5. On finding, fresh Terra planner records the reviewer finding newest-first, repairs affected tasks, and records exact disposition in the same entry. Repeat review with fresh context. Reviewer never writes artifacts.
6. Same planning finding permits at most three planner repair attempts. Fourth occurrence blocks planning with evidence. Different findings continue only while each cycle resolves a finding or materially improves acceptance, scope accuracy, or executable validation without regression.
7. Return only reviewed task paths. If user requested analysis only, still create and review tasks; do not invoke executor.

Analyst does not edit product files, execute implementation, create branches, stage, or commit.

## Executor preflight

Executor accepts exactly one task Markdown path and no bundled tasks. Before mutation:

1. Read repository instructions, task, newest one or two execution-journal entries if journal exists, and ordered prerequisite tasks. Effective expected paths are original expected product paths plus approved scope amendments.
2. Require planning review `PASS`, all prerequisites `COMPLETE`, Git repository with `HEAD`, and user-selected branch. Accept task `READY`, resumable `IN_PROGRESS` with unchanged recorded `START_COMMIT`, or explicitly user-resumed `BLOCKED` after blocker resolution. Do not create, checkout, or switch branch.
3. For `READY`, require no staged, unstaged, or untracked product paths. For resumed work, require no staged product paths and every unstaged or untracked product path both recorded by current task and inside effective expected paths. Ignore `.orchestrator/**` for cleanliness. Any other change is user-owned overlap; do not clean, stash, reset, restore, or overwrite it.
4. For `READY`, record current full `HEAD` as immutable `START_COMMIT`, set task `IN_PROGRESS`, and create task issue journal if absent. For resumed work, require recorded `START_COMMIT == HEAD`. If `HEAD` changes later, stop for user decision.
5. Product edit outside effective expected paths requires Terra adjuster approval recorded in task before edit.

Branch preparation and prerequisite integration belong to user. Executor never stages, commits, pushes, rewrites history, or mutates branches.

## Execution and review loop

1. Launch fresh model-inheriting implementation role with task path. It reads task, implements bounded scope, adds required tests, runs focused checks, and reports factual execution evidence. Executor primary records changed paths and validation evidence in task. Implementation may fix direct local errors before review.
2. Launch fresh ordinary reviewer with task path, immutable `START_COMMIT`, working-tree diff, validation evidence, and task journal. Reviewer independently checks acceptance, scope, integration, tests, regressions, and applicable repository rules.
3. Ordinary reviewer explicitly reports whether prior finding is `RESOLVED`, `PERSISTS`, or not applicable, plus measurable progress evidence. Executor primary prepends canonical `RESOLVED` entry when verified. On ordinary finding, inspect signature history before adjustment. If fewer than three completed repairs exist, Terra adjuster prepends canonical open finding entry, records concrete correction, and approves required expected-path expansion. Launch fresh implementation role, then fresh ordinary reviewer.
4. Same finding receives at most three ordinary repair attempts. If it persists after third, launch Terra final reviewer in loop-diagnosis mode before another adjustment. Diagnosis either provides one concrete correction routed through adjuster and one full fresh implementation/review cycle, or returns `BLOCKED` with decisive evidence. If same finding survives diagnosed correction, block; do not diagnose or repair it again.
5. Different demonstrated findings may continue while measurable progress occurs: prior finding resolves, acceptance coverage increases, failing relevant checks decrease, or scope becomes more accurate without regression. Reviewer progress `NONE` routes directly to Terra loop diagnosis before adjustment.
6. Ordinary reviewer `PASS` launches fresh Terra final reviewer. It checks complete task outcome against `START_COMMIT`, current product diff, task, tests, validation evidence, integration, scope, and relevant security.
7. Any Terra final finding returns through Terra adjuster, which prepends it to the journal, then through fresh implementation role and fresh ordinary reviewer. Terra final review reruns only after ordinary `PASS`. Terra finding starts or resumes its own finding cycle under same three-repair rule.
8. Mark task `COMPLETE` only after Terra final `PASS`. Any post-preflight terminal outcome sets task status and execution result `BLOCKED` and prepends canonical blocking evidence. A later invocation may resume only with unchanged `START_COMMIT` and explicit user instruction after blocker resolution.

Ordinary reviewer and Terra final reviewer are read-only for product, task, and journal. Terra adjuster is read-only for product and may update only supplied task and journal. Executor primary may initialize the journal and update execution status after verified gates. Only implementation role edits product.

## Validation boundary

Review product changes from immutable `START_COMMIT` through current working tree, excluding `.orchestrator/**` from product outcome. Validate all changed product paths are within effective expected paths: original expected paths plus approved scope amendments. Do not require unrelated full-suite checks unless request, repository rules, or material security, persistence, migration, concurrency, packaging, or cross-project risk makes them necessary.

In trusted repositories, run standard build, test, package restore, and localhost-only test activity autonomously. Standard restore may access configured package registries. Inspect unfamiliar project scripts before execution; stop services started by workflow. Do not use secrets or credentials, deploy, publish, release, alter remote systems, perform destructive data or filesystem actions, or cause unrelated external effects without explicit user approval.

Approval request states exact action, scope, consequence, and lowest-risk alternative. Materially different product behaviors also require user choice. Otherwise workflow continues autonomously.

## Progress and responses

Primary sends short Russian updates only at phase changes:

```text
Планирование: <analysis or task review>
Анализ и реализация: <task scope being implemented>
Проверка: <checks or ordinary review>
Финальное ревью: <Terra final review or diagnosis>
Готово: <result>
Стоп: <one actionable blocker>
```

Do not expose issue-journal paths, finding keys, cycle counts, internal role names, prompts, or handoffs. Do not quote internal artifacts. Analyst may return task paths. Executor may repeat supplied task path and report product paths, checks, risks, and blocker.

Analyst final response:

```text
Итог: READY|BLOCKED
Задачи: <reviewed task paths or none>
Риски и ограничения: <none or user-relevant exact risk>
Блокер: <none or one user action>
```

Executor final response:

```text
Итог: DONE|BLOCKED
Задача: <supplied task path>
Изменено: <product paths or none>
Проверки: <command — result>
Риски и ограничения: <none or user-relevant exact risk>
Блокер: <none or one user action>
```

`DONE` means final Terra `PASS`; no lesser verdict completes task.
