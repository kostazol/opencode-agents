# Agent Maintenance Guide

## Product contract

Repository versions four planning-only OpenCode agents:

- `orchestrator-analyst` is the sole primary and workflow router.
- `orchestrator-discovery` researches repository evidence, records material questions, and creates the stage map.
- `orchestrator-stage-planner` plans one approved stage.
- `orchestrator-stage-reviewer` reviews one current stage revision.

All agent names start with `orchestrator-`. Prompts use short positive instructions, one clear responsibility, readable inputs, a direct method, and one compact result contract.

## Workflow

`plan.md` is the table of contents and durable workflow index. Detailed planning proceeds one stage at a time. A fresh reviewer gates each stage. `PASS` advances to the first later non-PASS stage. All stages at `PASS` produce `READY`.

The primary continues through transitions until user input, approval, blocker, or completion. Resume derives the next action from artifacts and remains safe after interruption between an artifact write and index update. Test-only transition checkpoints live in the E2E harness, outside production prompts.

Artifacts are limited to:

```text
1_orchestrator/<request>/discovery.md
1_orchestrator/<request>/questions.md
1_orchestrator/<request>/plan.md
1_orchestrator/<request>/stages/<NN>-<slug>.md
1_orchestrator/<request>/reviews/<NN>.md
```

## Questions and approval

Discovery resolves technical facts from repository evidence and official version-sensitive sources. One current batch contains at most five material user decisions. Options explain consequences and put the evidence-supported recommendation first. Answers are persisted before follow-up discovery.

The user approves the complete stage map with exact `APPROVE`. Detailed stage files appear after approval.

## Stage planning and review

Planner reads the index, discovery, direct dependency stages, current stage, and current review. It writes one stage file with outcome, evidence, scope, paths, contracts, steps, acceptance, tests, validation, and non-goals.

Reviewer reads the same approved boundary and writes one review file. `REVISE` returns actionable current-stage findings and always continues through a new planner revision plus fresh review. `MAP_CHANGE_REQUIRED` presents the smallest evidence-backed delta for user approval.

## Permissions

Primary reads and updates workflow state and delegates only to the three planning subagents. Discovery writes top-level discovery artifacts. Planner writes stage files. Reviewer writes review files. Product evidence access is read-only. Git mutation is denied. Secret-bearing paths remain denied.

## Tests

Fast tests cover inventory, permissions, installer retirement, prompt contracts, artifact schemas, and routing rules. Small system E2E tests load the real user OpenCode config directory read-only while using temporary HOME, session database, state, cache, and product workspace. External plugins stay disabled in micro-E2E so their installation and cache cannot mutate the working environment. Each micro-E2E seeds one durable state, adds a harness-only checkpoint, and checks one transition. Together the seeded snapshots cover continuation from every durable state.

Main transition cases:

1. Discovery writes a question batch.
2. Pending questions invoke native `question` and persist answers.
3. An approved stage map starts S01 planning.
4. `PASS` S01 with additional stages starts S02 planning.
5. `REVIEW` starts fresh stage review.
6. `REVISE` resumes the same stage at the next revision.
7. All stages at `PASS` set workflow `ready`.
8. Every durable intermediate state resumes correctly.

## Change process

1. Read README, this guide, and every affected producer/consumer.
2. Keep prompts, permissions, installer behavior, tests, and docs aligned.
3. Preserve unknown and customized installed files during retirement.
4. For releases, update `VERSION`, installer `VERSION`, every agent marker, tests, and `CHANGELOG.md` together.
5. Run fast tests, syntax checks, `git diff --check`, temporary install/update tests, `opencode debug config`, and all micro-E2E tests.

## Repository exclusions

Keep credentials, provider auth, session databases, MCP tokens, `.env`, user source, generated target-repository `1_orchestrator/` artifacts, logs, patches, and test workspaces outside version control.
