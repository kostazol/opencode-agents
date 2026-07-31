# Agent Maintenance Guide

## Scope

This repository versions OpenCode agent prompts and shared protocols. Treat prompt changes as executable workflow changes: review permissions, state transitions, artifacts, and failure paths with the same care as application code.

## Sources of truth

- `protocols/orchestrator-v2.md` owns shared workflow invariants, IDs, gates, handoff schemas, and final-state rules.
- Each file under `agents/` owns only its role, permissions, modes, procedure, and compact response contract.
- Caveman is optional response compression support; workflow agents must continue when it is unavailable.
- `agents/` contains generated `orchestrator-00-main` and `orchestrator-01-single-model-main` primary agents plus direct Orchestrator v2 roles, ordered with `orchestrator-10` through `orchestrator-80` filename prefixes. Maintain shared primary logic in `orchestrator-00-main.template.md` and `agents/profiles/` fragments; do not edit rendered output.
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
8. Run root `opencode-agents.py` tests and preserve Windows, Linux, and macOS compatibility.

## Prompt size

- Store source and test prototypes as `path#symbol` references; do not copy code bodies into prompts or artifacts.
- Keep examples to one canonical schema when necessary.
- Remove superseded rules instead of appending corrections.
- Keep full logs, plans, patches, and evidence in workflow artifacts; agent responses return paths, IDs, verdicts, and decisive blockers.
- Avoid repeating protocol text in every role prompt.

## Model policy

- Pin Terra only for `orchestrator-30-planner-senior` and `orchestrator-80-final-reviewer` unless an explicit design decision changes this policy.
- Leave bootstrap, planners other than senior, executor, validator, mini reviewer, and aggregator model-agnostic so they inherit the selected/default model.
- `orchestrator-single-model` must deny `task` access to both Terra-pinned roles. `SINGLE_MODEL` completes through final validation, fresh cumulative mini review, and post-mini identity confirmation.
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
- `OPENAI_COLLABORATION` reaches completion only after Terra PASS and post-review identity confirmation; `SINGLE_MODEL` uses fresh cumulative mini PASS and post-mini identity confirmation.
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
- Shared protocol consumers use `__OPENCODE_PROTOCOL_PATH_YAML__` and `__OPENCODE_PROTOCOL_PATH_TEXT__`; installer renders both placeholders to target protocol path. Do not commit machine-specific protocol paths.
- Reviewers may write only their supplied review artifact class.
- Planner agents do not implement or run tests.
- ID ownership follows protocol: bootstrap owns request/initial IDs, validator owns plan/product/evidence/review-input IDs, aggregator owns mini/final-review IDs, and planner agents only consume them.
- Hidden workflow subagents remain callable by orchestrator but are less likely to be invoked directly.
- `orchestrator-00-main` is user-facing as `orchestrator` and must not require or explicitly load Caveman; hidden workflow agents may load it conditionally and use ultra mode.

## Validation

Install or synchronize changed files with root CLI, then run:

```bash
opencode debug config >/dev/null
```

Run `python3 tests/test-cli.py` on Linux/macOS and `py -3 tests/test-cli.py` on Windows. Validate rendered prompts against selected target path and test `update --prune-legacy` without deleting unknown user prompts.

Verify every modified text file:

- UTF-8;
- LF line endings unless the original requires otherwise;
- preserve each existing file's final-newline state;
- new files use one final newline and no additional blank line at EOF;
- no credentials or secret values.

Independent review must return no required correctness or operability findings before version release.

## Versioning

- Update `VERSION` for released configuration changes.
- Keep `VERSION`, `opencode-agents.py:VERSION`, and every agent version marker identical. Increment once per committed change set; do not increment again for uncommitted follow-up fixes.
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
