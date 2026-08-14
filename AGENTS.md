# Agent Maintenance Guide

## Product contract

Repository versions four planning-only OpenCode agents:

- `orchestrator-analyst` is the sole primary and workflow router.
- `orchestrator-discovery` researches repository evidence, records material questions, and creates the stage map.
- `orchestrator-stage-planner` plans one approved stage.
- `orchestrator-stage-reviewer` reviews one current stage revision.

All agent names start with `orchestrator-`. Prompts use short positive instructions, one clear responsibility, readable inputs, a direct method, and one compact result contract.

## Workflow

`plan.md` is the table of contents and durable workflow index. Architecture and risk planning proceeds one stage at a time. A fresh reviewer gates each technical stage. After all technical stages pass, planner creates one sibling Russian `.human-review.md` plan per stage and fresh reviewer gates its fidelity. All human reviews at `PASS` wait for user `APPROVE PLAN`; only that approval produces `READY`. User remarks persist in `feedback.md` and restart discovery for affected stages.

Stage `PASS` certifies a future implementation plan, not completed product work. Planning keeps product and Git state unchanged. Reviewers inspect current repository state and distinguish existing partial outputs from paths planned for later creation.

Human-readable questions, options, recommendations, stage-map prose, stage files, reviews, assumptions, decisions, and summaries use Russian. Protocol tokens, required section headings, paths, commands, and code identifiers remain exact.

The primary continues through transitions until user input, approval, blocker, or completion. Resume derives the next action from artifacts and remains safe after interruption between an artifact write and index update. Test-only transition checkpoints live in the E2E harness, outside production prompts.

Artifacts are limited to:

```text
1_orchestrator/<request>/discovery.md
1_orchestrator/<request>/questions.md
1_orchestrator/<request>/feedback.md
1_orchestrator/<request>/plan.md
1_orchestrator/<request>/stages/<NN>-<slug>.md
1_orchestrator/<request>/stages/<NN>-<slug>.human-review.md
1_orchestrator/<request>/reviews/<NN>.md
1_orchestrator/<request>/reviews/<NN>-human-review.md
```

## Questions and approval

Discovery resolves technical facts from repository evidence and official version-sensitive sources. One current batch contains at most five material user decisions. Options explain consequences and put the evidence-supported recommendation first. Answers are persisted before follow-up discovery.

The user approves the complete stage map with exact `APPROVE`. Detailed stage files appear after approval.

## Stage planning and review

Planner reads the index, discovery, direct dependency stages, current stage, and current review. It writes one concise stage file with outcome, architecture, reference patterns, evidence- or risk-backed mandatory constraints, key external, integration, and dependency contracts, material risks, coarse implementation actions, and mandatory business test scenarios and validations. Every mandatory case gives preconditions or input, action, expected observable output, error, state, or side effect, and contract-significant values or equivalence classes. Acceptance signals and verification direction remain explicit. Test names, files, fixtures, mocks, framework structure, assertion mechanics, and additional implementation-discovered tests stay open.

Reviewer reads the same approved boundary and writes one review file. It gates decision sufficiency, repository fit, risks, key contracts, mandatory business-scenario and validation coverage, observable acceptance, and appropriate detail rather than document volume. In human-review mode it gates fidelity, completeness of user-visible expectations, and understandable Russian language. `REVISE` returns actionable current-stage findings and always continues through a new planner revision plus fresh review. `MAP_CHANGE_REQUIRED` presents the smallest evidence-backed delta for user approval.

## Permissions

Primary reads and updates workflow state and delegates only the current workflow transition to the three planning subagents. Discovery writes top-level discovery artifacts. Planner writes one current technical stage or human-review file. Reviewer writes one current technical or human-review review file. Product evidence access is read-only. Git mutation is denied. Secret-bearing paths remain denied.

## Tests

Fast tests cover inventory, permissions, installer retirement, prompt contracts, artifact schemas, and routing rules. Small system E2E tests load the real user OpenCode config directory read-only while using temporary HOME, session database, state, cache, and product workspace. External plugins stay disabled in micro-E2E so their installation and cache cannot mutate the working environment. Each micro-E2E seeds one durable state, adds a harness-only checkpoint, and checks one transition. Together the seeded snapshots cover continuation from every durable state.

Main transition cases:

1. Discovery writes a question batch.
2. Pending questions invoke native `question` and persist answers.
3. An approved stage map starts S01 planning.
4. `PASS` S01 with additional stages starts S02 planning.
5. `REVIEW` starts fresh stage review.
6. `REVISE` resumes the same stage at the next revision.
7. All technical stages at `PASS` start human-review planning and review.
8. All human reviews at `PASS` wait for `APPROVE PLAN` or feedback.
9. `APPROVE PLAN` sets workflow `ready`; feedback restarts discovery for affected stages.
10. Every durable intermediate state resumes correctly.

## Change process

1. Read README, this guide, and every affected producer/consumer.
2. Keep prompts, permissions, installer behavior, tests, and docs aligned.
3. Preserve unknown and customized installed files during retirement.
4. For releases, update `VERSION`, installer `VERSION`, every agent marker, tests, and `CHANGELOG.md` together.
5. Run fast tests, syntax checks, `git diff --check`, temporary install/update tests, `opencode debug config`, and all micro-E2E tests.

## Russian agent documentation

`docs/orchestrator-*.md` are Russian documentation copies of matching authoritative `agents/orchestrator-*.md` prompts. At the end of every task that changes an agent prompt, update its Russian copy and verify both files remain semantically synchronized. Preserve protocol tokens, statuses, required headings, paths, commands, code identifiers, YAML permission structure, and compact result blocks exactly. Finish prompt-changing work only after this synchronization check passes.

## Repository exclusions

Keep credentials, provider auth, session databases, MCP tokens, `.env`, user source, generated target-repository `1_orchestrator/` artifacts, logs, patches, and test workspaces outside version control.
