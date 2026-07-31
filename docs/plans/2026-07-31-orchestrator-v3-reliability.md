# Orchestrator v3 reliability implementation plan

## Purpose

Fix incident classes documented in `docs/incidents/2026-07-31-python-static-tools-workflow.md`:

- missing or ad hoc lane-input manifests and `LANE_INPUT_ID` values;
- stale or duplicate lanes after a changed review input;
- stage review scopes that can include earlier accepted work;
- repairable security findings converted into terminal blockers by a numeric retry budget;
- no safe reconciliation after interruption, agent update, or plan correction.

This plan supersedes v2 rules that prohibit workflow Git commits. It is a major protocol change and releases as version `3.0.0`.

## Decisions approved

1. Accepted implementation stages create and retain real Git commits in current branch. No automatic squash, reset, amend, rebase, branch switch, or force push occurs.
2. A dirty baseline requires explicit user consent before workflow continues. Agent never automatically stashes, resets, restores, checks out, or relocates user changes.
3. Unresolved stage stays at its current small-diff boundary. `OPENAI_COLLABORATION` runs two mini-review/repair cycles, then Terra adjudicates demonstrated risks; `SINGLE_MODEL` continues mini-review/repair cycles without limit.
4. Terra does not search speculatively for findings. It resolves false positives or requires planning-authority replan; only after a Terra-directed replan/repair fails for same cause may Terra return `WAITING_FOR_USER`.
5. Add a dedicated Terra-pinned `orchestrator-75-escalation-reviewer`. `orchestrator-80-final-reviewer` remains final-only.
6. Final repairable findings have no numeric blocker limit. Final cycle exposes durable progress and remains interruptible by user.
7. Interrupted or updated workflows reconcile repository facts and artifacts before any execution. Major protocol migration requires explicit user consent.

## Core invariants

- Product-mutating implementation remains sequential.
- A stage mini review receives only delta from previous accepted checkpoint to current frozen product snapshot. It never receives cumulative prior-stage diff as its primary review patch.
- Final review receives immutable baseline artifact/initial-HEAD attribution, cumulative workflow diff through current checkpoint, and accepted-stage review ledger.
- Validator exclusively creates lane-input manifests and calculates `LANE_INPUT_ID`.
- Each review input owns one immutable review epoch. No artifact from another epoch may authorize repair, acceptance, aggregation, or completion.
- Checkpointer is only role allowed to create workflow commits. It commits exact declared workflow paths only after mini/Terra PASS, preserves user-owned staged entries, and refreshes committed workflow-path index entries before stage acceptance.
- `.orchestrator/**`, credentials, ignored secret-bearing files, user baseline changes, and undeclared files never enter workflow commits.
- A terminal `BLOCKED` state means work cannot safely proceed without external fact, access, or user decision. A repairable finding alone never produces it.

## Human-readable workflow status

Bootstrap creates mutable convenience view:

```text
.orchestrator/tasks/<workflow-id>/status.md
```

`status.md` is not authorization evidence; `plan/master.md`, validator artifacts, and observed repository state remain authoritative. It gives user a short current position without reading workflow internals:

```text
# Workflow status
Updated: <UTC timestamp>
Workflow: <id> | Protocol: <version> | Profile: <profile>
State: <phase>
Progress: Stage <n> of <total> — <stage ID/result>
Step: <dispatch|execution|validation|mini review|checkpoint|repair|escalation|final review|recovery>
Attempt: <normal repair n/2|escalation|final cycle n|none>
Review: <epoch/lens summary or pending>
Checkpoint: <commit ID|pending>
Current product snapshot: <ID>
Last confirmed result: <one line>
Next action: <one line>
Attention: <none|user decision/blocker>
```

Bootstrap creates initial status. Planner owns updates before dispatch, after every consumed terminal report, on repair/escalation/final-cycle transitions, and on recovery/migration. An interrupted task leaves last confirmed state plus explicit `IN_FLIGHT` action; it never claims an unverified result.

Primary also emits one concise session progress line after each user-visible boundary, for example:

```text
Workflow: stage 2/5 (WP0) | mini review | repair 1/2 | epoch: 8f31…
```

At final-cycle start it reports that final review may take several iterations and gives `status.md` path. `STATUS` mode returns this path and current concise state without mutation.

## Git checkpoint design

### Clean baseline

Bootstrap records baseline `HEAD`, branch, index, status, and untracked inventory. When no product-relevant user changes exist, workflow starts normally.

For every accepted stage:

1. Executor changes declared paths.
2. Validator freezes stage product snapshot and emits exact stage patch/inventory.
3. Mini lanes and aggregation pass against that frozen snapshot.
4. Checkpointer verifies product snapshot has not changed after review, creates one stage checkpoint commit, and records commit ID/tree/parent/path inventory.
5. Validator `ACCEPT_STAGE` verifies the checkpoint commit against reviewed snapshot, then creates accepted checkpoint artifacts.

The next stage begins from committed `HEAD`. Its review patch is limited to prior checkpoint commit versus its frozen current snapshot. Final review uses baseline workflow commit range to final workflow checkpoint commit.

### Dirty baseline and consent

If bootstrap finds staged, unstaged, or untracked product changes, primary shows path inventory, `HEAD`, branch, and index state. It enters `OPERATIONAL_CONSENT_REQUIRED` until user explicitly consents to continue.

Consent is persisted as immutable workflow artifact with baseline inventory hash and requested action. It authorizes reconciliation only; it does not authorize modifying or committing user-owned paths.

After consent:

- Checkpointer invokes a fixed installed helper with no arguments. Helper stages and commits only declared workflow paths using normal Git commit semantics.
- It verifies every committed path is workflow-owned and disjoint from baseline user-owned paths.
- It creates one current-branch commit, preserves user-owned staged entries, and refreshes only committed workflow-path index entries.
- Baseline/workflow path overlap returns `OPERATIONAL_CONSENT_REQUIRED` and requires user resolution or separate worktree. Changed `HEAD`, index, product, or review identity returns `STALE` and requires recovery plus fresh validation/review.

Baseline user changes remain uncommitted in working tree and excluded from workflow commit range. They remain attributable baseline evidence throughout validation and recovery.

### Commit format and restrictions

Commit subject is deterministic and identifies workflow/stage. Commit trailers include workflow ID, stage ID, prior checkpoint ID, product snapshot ID, review epoch, and plan structure ID. Checkpointer cannot create merge commits, amend, squash, reset, restore, rebase, checkout, stash, clean, push, or alter non-workflow index entries.

## Review epoch design

### Validator-owned preparation

Add validator modes:

- `PREPARE_MINI_REVIEW` creates a unique immutable epoch manifest and one lane-input manifest for every expected lane.
- `RECOVER` reconciles an interrupted workflow without product mutation.

`PREPARE_MINI_REVIEW` writes:

```text
validation/review-epochs/<epoch>/manifest.json
validation/review-epochs/<epoch>/inputs/<lens>.json
```

Each input contains exact request/plan/product/evidence/review IDs, acceptance, assigned paths/dependencies, prototype hashes, prior relevant findings, stage delta or final cumulative patch path/hash, inventory, validation evidence, lens, and computed `LANE_INPUT_ID`.

The epoch manifest contains `REVIEW_EPOCH_ID`, `REVIEW_INPUT_ID`, stage/final purpose, product snapshot, expected lens set, exact input paths/hashes, and state. Validator owns canonicalization and hashes. Planner and primary only pass generated paths and IDs.

### Immutable output layout

```text
reviews/mini/epochs/<epoch>/lanes/<lens>.md
reviews/mini/epochs/<epoch>/aggregate.md
reviews/escalation/<epoch>.md
```

Output path includes epoch and lens, so retry cannot overwrite prior evidence. Reviewer writes only its supplied lane output; aggregator writes only supplied aggregate output.

### Invalidation

Planner canonical state maps active/replaced epochs. Any changed `REVIEW_INPUT_ID` marks the prior epoch `SUPERSEDED` in canonical plan state before dispatching new lanes. Prior files remain immutable audit evidence.

Aggregator accepts exactly manifests listed by current active epoch. It rejects a missing lane, duplicate lens, wrong epoch, wrong review input, wrong lane input ID, or reused lane from another epoch as `STALE` or `BLOCKED` before aggregation. Lane reuse is forbidden after any product, evidence, scope, or review-input change. Final cumulative review never reuses lanes.

## Stage review and escalation flow

### Standard stage flow

```text
executor
validator STAGE
validator PREPARE_MINI_REVIEW
fresh mini lanes
aggregator
checkpointer after MINI_GATE PASS
validator ACCEPT_STAGE
planner advances
```

Validator `STAGE` emits only previous accepted checkpoint-to-current frozen snapshot patch for mini review. It also stores cumulative state for later final review, but does not provide it as stage lane primary scope.

### Two mini-review cycles

For a required local root cause, planner terminalizes prior dispatch and creates authorized bounded repair. Each repair is followed by fresh validation, new review input, new epoch, and fresh lanes. The current stage remains active and next stage cannot start while unresolved findings remain.

### Terra adjudication without terminal block

After two unresolved mini-review cycles, `OPENAI_COLLABORATION` uses:

```text
orchestrator-75-escalation-reviewer (Terra)
```

The escalation reviewer adjudicates only supplied unresolved findings against acceptance, code, validation, current stage delta, and prior cause history. It writes an independent verdict under `reviews/escalation/`; it does not search for additional speculative findings.

- `PASS`: checkpointer commits stage; validator accepts; planner dispatches next ready stage.
- confirmed local or structural risk: profile planning authority replans, then fresh mini-review cycles restart on same stage boundary.
- `WAITING_FOR_USER`: only after Terra-directed replan/repair for same cause completed and evidence proves no safe resolution within contract.
- `SINGLE_MODEL`: bypasses Terra and continues fresh mini-review/repair cycles without numeric limit.

## Final cycle

Planner persists final-cycle status before final validation:

```text
FINAL_CYCLE_STARTED
FINAL_CYCLE_NUMBER: <n>
CURRENT_PRODUCT_SNAPSHOT_ID: <ID>
CURRENT_REVIEW_INPUT_ID: <ID|pending>
OPEN_CAUSE_KEYS: <list>
```

Primary reports that final review is active, may take multiple repair/review iterations, and can be interrupted by user.

Each final iteration runs:

```text
validator FINAL
validator PREPARE_MINI_REVIEW
fresh cumulative mini lanes
aggregator
Terra final review after MINI_GATE PASS
post-review identity validation
```

Required local findings create authorized repair, new checkpoint commit after review PASS, new snapshot, and a new final iteration. There is no numeric maximum for repairable final findings or Terra cycles. Repeated cause keys require recorded root-cause comparison and escalation rationale; identical repair cannot be silently repeated. In `OPENAI_COLLABORATION`, only Terra may return `WAITING_FOR_USER` after its replan/repair proves a user decision is required; `SINGLE_MODEL` continues review/repair cycles.

## Recovery, correction, and migration

### Recovery before resume

Primary never resumes from session memory. It calls validator `RECOVER`, then planner `RECOVER_AND_REPLAN`.

Validator records current repository facts: workspace roots, branch/HEAD, index/status, baseline inventory, checkpoint commit chain, product snapshot, artifact hashes, current plan IDs, and actual changed-path inventory. It classifies each checkpoint/validation/review artifact as `CURRENT`, `SUPERSEDED`, `STALE`, `MISSING`, or `UNVERIFIED`.

Planner preserves an accepted stage only when checkpoint commit, reviewed product snapshot, acceptance evidence, and current dependency scope validate. It does not delete incomplete changes. Unaccepted changes are recorded as actual product state and require user decision when they conflict with plan ownership.

### User correction and replan

User correction appends immutable request, freezes active dispatch, and triggers recovery/reconciliation before profile planning authority replans whole active request set. Valid accepted work is reused only after scope/dependency validation. New plan/review IDs and epochs are generated before new execution.

### Agent update and protocol migration

Manifest records protocol/config version and required artifact schemas. Patch/minor compatible update runs recovery compatibility checks. Major version mismatch enters `MIGRATION_REQUIRED` and creates a read-only migration report covering retained commits, valid accepted stages, stale artifacts, required ID recomputation, and plan changes.

Primary asks explicit user consent before a major migration mutates plan state or resumes execution. v2 workflow artifacts are never treated as v3 authorization without this migration/replan.

## Files and responsibilities

### Protocol and generated primary sources

- `protocols/orchestrator-v2.md`: replace with v3 protocol content or introduce versioned v3 protocol and update installer references; define IDs, states, commit policy, review epochs, recovery, and migration.
- `agents/orchestrator-00-main.template.md`: add dirty-baseline consent, checkpoint, epoch, escalation, final-progress, recovery, and migration transitions.
- `agents/profiles/openai.md` and `agents/profiles/single-model.md`: update profile workflow/final gates. `SINGLE_MODEL` has no Terra escalation/final role and uses expanded fresh mini escalation policy.
- renderer/installer source: render new roles and v3 protocol path; preserve existing target upgrade behavior.

### Existing roles

- bootstrap: capture Git baseline/dirty inventory and consent request facts; create initial `status.md`.
- planner: epoch state, repair/escalation state, recovery/replan, no stale dispatch activation, and user-facing `status.md` updates.
- executor: no checkpoint commit authority; verify expected checkpoint ancestry before mutation.
- validator: add preparation/recovery modes, produce lane inputs/epoch manifests, verify stage patches and checkpoint commits.
- mini reviewer: require exact epoch manifest/input, stage-only or final-only patch scope, epoch-specific output path.
- aggregator: aggregate exact current epoch only; calculate current mini bundle; reject stale/reused inputs.
- final reviewer: remove fixed two-round blocker, require current final epoch/progress/cause history, return repairable versus external blockers accurately.

### New roles

- `agents/orchestrator-45-checkpointer.md`: least-privilege stage commit role with narrow Git command allowlist and artifact output permission.
- `agents/orchestrator-75-escalation-reviewer.md`: Terra-pinned independent stage escalation reviewer with write permission only to supplied escalation review artifact.

### Versioning and documentation

- Update `VERSION`, `opencode-agents.py:VERSION`, every agent version marker, and `CHANGELOG.md` once to `3.0.0`.
- Retain `docs/incidents/2026-07-31-python-static-tools-workflow.md` and this plan as rationale/migration documentation.

## Test plan

1. Extend root CLI tests for install/update/render/prune behavior with new roles and versioned protocol paths.
2. Add static prompt/config assertions:
   - every expected lane has validator-owned input manifest/ID;
   - no undocumented validator mode exists;
   - lane/aggregate paths include epoch;
   - stale epoch cannot aggregate or accept;
   - stage mini scope is checkpoint delta only;
   - final scope is cumulative only;
   - `75` is Terra-pinned and inaccessible to `SINGLE_MODEL`;
   - `80` remains final-only.
   - bootstrap/planner own only designated `status.md` writes and status is explicitly non-authoritative.
3. Add Git fixture integration tests:
   - clean baseline produces one exact stage commit and preserves stage diff boundaries;
   - dirty baseline requires consent;
   - checkpoint helper preserves user-owned staged entries and excludes user paths;
   - overlap and changed-HEAD return `OPERATIONAL_CONSENT_REQUIRED`;
   - no reset/stash/rebase/squash/force-push command is permitted.
4. Add recovery fixtures:
   - interrupted before review;
   - interrupted after mini PASS but before checkpoint;
   - updated agent compatible recovery;
   - major v2-to-v3 migration requires consent;
   - corrected plan preserves valid checkpoint and invalidates affected review epochs.
5. Run installer synchronization, `opencode debug config >/dev/null`, root CLI tests, line-ending/UTF-8 checks, and independent prompt review before release.

## Acceptance criteria

- No lane can start without validator-created current lane manifest and `LANE_INPUT_ID`.
- No stale lane/aggregate/bundle can affect current dispatch, repair, acceptance, or completion.
- A mini reviewer of WPn cannot receive accepted work from WP<n as primary diff scope.
- Every accepted stage has one verifiable commit containing only declared workflow paths.
- Dirty baseline cannot continue without recorded explicit user consent and cannot alter user-owned staged entries.
- Third repairable stage finding reaches escalation, not automatic `BLOCKED`.
- Final repairable findings continue through visible final cycles until PASS, user interruption, or a genuine external decision/access condition.
- Resume/replan after interruption or agent update revalidates facts before mutation and never trusts session memory.
- User can inspect `status.md` to identify stage/total, current step, attempt, review epoch, checkpoint, next action, and required decision.
