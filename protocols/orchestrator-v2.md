# Orchestrator Protocol v3

## Authority and evidence

Normative order:
1. Platform permissions and safety constraints.
2. Latest explicit user instruction; scoped corrections supersede conflicting earlier requests.
3. Repository instructions.
4. Profile-planning-authority-audited design for the current request set.

Evidence order:
1. Current observed repository state and immutable artifacts.
2. Canonical plan state.
3. Agent summaries.
4. Prototypes as guidance.

An unresolved normative conflict returns `BLOCKED`. An identity mismatch returns `STALE` without state transition.

## Workflow profiles

Select one profile before bootstrap and persist it as immutable `WORKFLOW_PROFILE` in `manifest.json`. Follow-up requests retain it:

- `OPENAI_COLLABORATION`: bounded recon by `orchestrator-20-planner`, Terra-pinned structural planning by `orchestrator-30-planner-senior`, and Terra final review by `orchestrator-80-final-reviewer`.
- `SINGLE_MODEL`: `orchestrator-25-planner-full` inherits caller model and owns recon, structural planning, audit, and replan. `orchestrator-20-planner` owns only dispatch/state work. No Terra-pinned role participates.

Profile selection is a workflow contract. An absent, invalid, or changed profile returns `BLOCKED`. `SINGLE_MODEL` completion uses final validation, fresh cumulative mini review, and post-mini identity confirmation; `FINAL_REVIEW_INPUT_ID` and Terra verdict are `not_applicable`. Manifest records protocol/config version and schema. Updates run recovery before resume.

## Workflow root

Use one stable workflow ID per user outcome. Follow-ups reuse it. `WORKSPACE_ROOT` is exact absolute active-session project directory supplied by primary orchestrator; it is never replaced by a different root found through Git discovery. `GIT_REPOSITORY_ROOT` may equal or contain `WORKSPACE_ROOT`, but is repository metadata only. `WORKFLOW_ROOT` is exact absolute `WORKSPACE_ROOT/.orchestrator/tasks/<workflow-id>/`; no artifact may use another `.orchestrator/` directory. During `INITIALIZE`, bootstrap validates caller-derived absolute roots and their equality invariant before any write, then persists all three roots. After manifest creation, every role verifies supplied roots against it. A mismatch, a relative root, or substituting `GIT_REPOSITORY_ROOT` when it differs from `WORKSPACE_ROOT` returns `STALE` before writes. Handoffs use exact absolute `WORKFLOW_ROOT`; relative artifact paths are valid only relative to that root, never Git root. Artifact-write permissions must separately allow `.orchestrator/...` and `*/.orchestrator/...`: OpenCode evaluates normalized Git-worktree-relative paths, each `*` spans path separators, and a wildcard prefix followed by `/` does not match the root-relative form.

```text
manifest.json
requests/R###.md
contract.md
baseline/
recon/index.md
recon/repository.md
recon/prototypes.md
plan/master.md
status.md
plan/structure.json
plan/audit.md
plan/dispatch/
stages/
stages/executor/
snapshots/
validation/
reviews/mini/epochs/
reviews/escalation/
reviews/final/
```

Initialization requires a Git workspace because accepted stages are checkpoint commits. Capture complete pre-setup status, tracked/staged patch, untracked hashes, branch/HEAD, repository identity, and `BASE_PRODUCT_SNAPSHOT_ID` before mutation. A non-Git workspace returns `BLOCKED` before writes. Persist baseline under new workflow root first. If `.gitignore` is baseline-user-owned and lacks required rule, stop before mutation with `OPERATIONAL_CONSENT_REQUIRED`; user resolves ownership or chooses separate worktree. Otherwise add only exact `/.orchestrator/` when missing and verify root ignored. Classify edit as attributable workflow setup and include it in product identity, traceability, inventory, and final patch. Exclude only `WORKSPACE_ROOT/.orchestrator/**` from product scope, snapshots, patches, staging, and review.

Validator checkpoint-delta inventory is checkpoint authority: every uncommitted workflow-owned product path since prior accepted checkpoint must enter `STAGE` or `FINAL` checkpoint request, including bootstrap `SETUP_PRODUCT_PATHS`. First checkpoint therefore contains setup edit plus first stage delta. `FINAL_REPAIR` request uses validator `FINAL` checkpoint-delta inventory, never cumulative final inventory. Executor write permissions remain limited to its stage capsule; setup paths are inherited reviewed inventory, not executor writes. Later checkpoint inventory begins at prior accepted checkpoint and excludes already committed setup paths.

`manifest.json` is an immutable bootstrap index: protocol/config version, workflow ID, absolute `WORKSPACE_ROOT`, `GIT_REPOSITORY_ROOT`, `WORKFLOW_ROOT`, baseline paths, first request path, Git baseline, and initialization result. Runtime state lives in `plan/master.md`. Bootstrap creates `status.md`; planner maintains it as human-readable non-authoritative view. It records updated UTC time, phase, stage/total, step, attempt, review epoch, checkpoint commit, product snapshot, last confirmed result, next action, and attention. Before dispatch planner records `IN_FLIGHT`; interruption never claims an unverified result. Primary reports concise status after every user-visible boundary and on final-cycle start.

Each user task or correction gets a new immutable request file. Preserve APIs, CLI, schemas, acceptance, exact errors, commands, and constraints. Replace credential values with `[REDACTED_SECRET]`. `contract.md` normalizes the active request set and records supersession links; request text remains authoritative.

## Identity

Ordering counters:
- `PLAN_REVISION`: canonical plan-state change;
- `STRUCTURE_REVISION`: structural design change;
- `WAVE_REVISION`: dispatched snapshot change.

Content IDs:
- `REQUEST_SET_ID`: ordered immutable request files plus supersession map;
- `PLAN_STRUCTURE_ID`: canonical schema-versioned `plan/structure.json` hash covering goal, acceptance, constraints, exclusions, decisions, stages, dependencies, waves, barriers, reads/writes, consistency boundaries, prototype requirements/novelty, validation, review profiles, pass conditions, and planning-authority-approved structural deviations;
- `BASE_PRODUCT_SNAPSHOT_ID`: immutable pre-setup product baseline;
- `PRODUCT_SNAPSHOT_ID`: sorted path/type/mode/content/deletion/intended-untracked manifest hash, excluding workflow artifacts;
- `EVIDENCE_BUNDLE_ID`: baseline classification, commands, toolchain, results, artifacts, and pre/post product IDs;
- `REVIEW_SCOPE_ID`: baseline, delta/cumulative patch, inventory, prototypes, accepted implementation variances, prior findings, acceptance, lane assignments, and their hashes;
- `REVIEW_INPUT_ID`: request set, plan structure, product snapshot, evidence bundle, and review scope IDs;
- `DISPATCH_AUTHORIZATION_ID`: workflow/profile, request/plan/expected-product IDs, current and target post-activation revisions, active stage or repair cycle, validator-resolved capsule or repair-manifest and prototype/evidence hashes, validation manifest, declared writes, and target dispatch phase;
- `CHECKPOINT_COMMIT_ID`: accepted stage Git commit/tree/parent, declared filesystem and Git-object inventory, reviewed product snapshot, and review epoch;
- `REVIEW_EPOCH_ID`: current review-input purpose, product snapshot, expected lens manifests, and review cycle;
- `LANE_INPUT_ID`: validator-produced lens-specific path, dependency, contract, prototype, prior-finding, stage/final patch, inventory, and evidence hashes;
- `MINI_REVIEW_BUNDLE_ID`: current lane verdict files plus aggregate hash;
- `FINAL_REVIEW_INPUT_ID`: `OPENAI_COLLABORATION` review input plus mini-review bundle IDs; `not_applicable` for `SINGLE_MODEL`.

Compute IDs as lowercase SHA-256 of UTF-8 canonical JSON: schema/version domain tag, sorted object keys, preserved array order, no insignificant whitespace, and explicit relative paths. An artifact containing its own ID excludes that ID field from hashed payload. `MINI_REVIEW_BUNDLE_ID` hashes lane files plus aggregate payload with `MINI_REVIEW_BUNDLE_ID` and `FINAL_REVIEW_INPUT_ID` removed.

`REVIEWED_INDEX_DIGEST` is validator-owned checkpoint input. Validator obtains it only from installed checkpoint helper `--index-digest` mode run with Git root as working directory. Helper hashes every stage entry from `git ls-files -s -z`, ordered by decoded path then stage, as repeated path bytes, NUL, ASCII stage, NUL, raw metadata, NUL; no paths are excluded. Checkpointer copies exact output into request and helper rejects drift before commit.

Authoring agents write canonical unhashed inputs. Designated ID producers: bootstrap computes `REQUEST_SET_ID` and initialization base/current product IDs; validator `IDENTITY` computes plan, later product, evidence, review-scope, and review-input IDs; validator `PREPARE_MINI_REVIEW` computes review-epoch and lane-input IDs; validator `AUTHORIZE_DISPATCH` computes `DISPATCH_AUTHORIZATION_ID`; checkpointer computes checkpoint commit ID; aggregator computes mini-review bundle and final-review-input IDs from validator-bound inputs. Aggregator records `FINAL_REVIEW_INPUT_ID: not_applicable` for `SINGLE_MODEL`. Each producer writes canonicalization/hash evidence. Planner agents consume produced IDs; they do not synthesize cryptographic hashes.

Status-only plan updates preserve content IDs. Changed content recomputes affected IDs before further execution or review.

## Baseline and request changes

Baseline capture precedes product mutation. Bootstrap records branch/HEAD, index, staged/unstaged/untracked product inventory and baseline ownership. A clean baseline permits checkpoint commits. A dirty baseline requires primary to show this inventory and obtain explicit user consent persisted under workflow root before execution. Consent never authorizes stash, reset, restore, checkout, branch switch, or committing baseline-user paths. A declared write overlapping baseline-user paths returns `OPERATIONAL_CONSENT_REQUIRED`, distinct from Terra-only review-risk `WAITING_FOR_USER`. Read-only recon may then identify candidate behavior and prototypes. Baseline validation classifies:
- `GREEN`: required unaffected behavior passes;
- `EXPECTED_RED`: failure precisely demonstrates requested defect and unrelated required checks pass;
- `BLOCKED`: unrelated failures or attribution gaps prevent reliable work.

Run direct affected/prototype tests and affected project validation. Run full baseline when requested, required by acceptance, or justified by security, concurrency, persistence, migration, runner, or repository-wide contract risk. Record `NOT_REQUIRED` with rationale otherwise.

A follow-up request appends the ledger, recomputes `REQUEST_SET_ID`, freezes new dispatch, and marks active dispatch stale. Inventory actual changes, then invoke profile planning authority for replan against the whole request set. Reuse accepted evidence only when its content and contract scope remain valid.

## Recovery and correction

Primary never resumes from session memory. Before any resumed dispatch it calls validator `RECOVER`, which records workspace roots, branch/HEAD, index/status, baseline-user inventory, checkpoint commit chain, current product snapshot, artifact hashes, and actual changed paths. It classifies checkpoint, validation, and review artifacts as `CURRENT`, `SUPERSEDED`, `STALE`, `MISSING`, or `UNVERIFIED` without mutating product. Planner `RECOVER_AND_REPLAN` consumes this report, preserves an accepted stage only when commit, reviewed snapshot, validation, review, and dependency scope remain valid, and records incomplete changes without deleting them. A user correction appends immutable request, freezes active dispatch, runs recovery, then invokes profile planning authority against whole request set. New IDs and fresh review epochs are required before execution.

## Verifiable planning units

Every dispatched implementation stage is one independently observable, buildable, testable consistency boundary with acceptance IDs, dependencies, workspace path, exclusive product writes, exact artifact writes, direct integrations/state, prototype requirement, validation, review profile, and pass condition.

Inseparable non-buildable operations are ordered substeps inside one stage and one executor task. Intermediate broken state gets no handoff, review, snapshot checkpoint, or parallel exposure. Planning, authorization, investigation, baseline, artifact, and validation stages may remain separate when they have machine-verifiable results.

Product-mutating stages execute sequentially in the shared worktree. Read-only validation and review tasks may run in parallel on one frozen snapshot.

## Dispatch authorization

Primary orchestrators do not inspect product code or use generic exploration agents. They dispatch only named workflow roles and only after rereading canonical workflow artifacts. An implementation executor input contains references and IDs, never copied source bodies, inferred plans, or ad hoc write lists.

Planner first writes an inactive candidate dispatch manifest with `TARGET_PHASE: EXECUTING`. Validator `AUTHORIZE_DISPATCH` verifies canonical workflow inputs and computes `DISPATCH_AUTHORIZATION_ID` over its authorization payload with `DISPATCH_AUTHORIZATION_ID` and operational `ACTIVE` fields omitted. Validator persists that canonical payload hash, never a raw candidate-file hash. Planner then verifies the authorization artifact and activates only those omitted operational fields plus canonical plan state. Raw `plan/master.md` and dispatch-file hashes may therefore change during activation; they are not stale or contradictory when the authorization payload, expected product ID, and authorized target revisions still match. Stage and local repair dispatches use the same sequence; planner `AUTHORIZE_REPAIR` accepts aggregated local findings or exact validator readiness failures and creates a bounded repair manifest and candidate before validator authorization. Structural repairs return to profile planning authority instead.

An active implementation dispatch requires current `manifest.json`, `contract.md`, audited `plan/master.md`, exact stage capsule or repair manifest, dispatch manifest, validator authorization artifact, `DISPATCH_AUTHORIZATION_ID`, `PLAN_STRUCTURE_ID`, expected `PRODUCT_SNAPSHOT_ID`, prototype gate `PASS|NOVEL_APPROVED`, declared product/artifact write sets, and plan-bound validation manifest. Executor validates the canonical authorization payload, expected post-activation revisions, and artifact paths, never raw pre-activation file hashes. It then may read repository instructions and compute the current product manifest. Mutation starts only after expected product identity and canonical phase `EXECUTING` match. Missing, unreadable, stale, or contradictory authorization returns `BLOCKED` before mutation.

## Prototype gate

Recon records bounded candidates. Before every dispatch, dispatcher planner refines exact current references against audited stage and product state:
- primary implementation `path#symbol` or `none` for approved novelty;
- primary test `path#symbol` or `none` for approved novelty;
- optional integration reference;
- one-line similarity;
- two to four practices to apply;
- target-specific differences;
- source/dependency/config hashes and validation evidence.

Use at most one primary and two supplemental references. Store references, not copied source/test bodies. User contract and audited design control behavior.

States:
- `PASS`: applicable references and current GREEN evidence;
- `VALIDATION_REQUIRED`: exact validation manifest emitted;
- `VALIDATION_FAILED`: requested validation failed; return evidence for profile planning-authority decision;
- `NOVEL_APPROVED`: profile planning authority recorded search coverage, rationale, design source, and exact test strategy;
- `BLOCKED`: required reference, approval, or evidence absent.

Only `PASS` or `NOVEL_APPROVED` permits implementation dispatch. One unchanged-input validation retry is allowed; repeated failure escalates profile planning authority or blocks.

## Execution and validation

Executor reads request, capsule, prototypes, and repository instructions only after dispatch authorization; writes declared paths; reports ownership or contract contradiction before out-of-scope mutation. Behavior changes follow RED, minimal implementation, GREEN targeted checks, then affected checks. `RED_DEFERRED` needs exact reason and new/updated tests before review. Other artifacts use applicable validators. Before execution, reject validation commands containing unquoted shell control operators, fallback branches, backgrounding, command substitution, output redirection, or explicit exit rewriting. Run accepted commands directly and record each command's own exit and bounded decisive output. Validator runs each allowlisted read-only Git inspection as one direct command, never a compound shell command; binary patch collection uses `--no-ext-diff --no-textconv`. Git mutations remain restricted to checkpoint helper. Executor never creates Git commits.

Review readiness requires complete inventory, current product snapshot, build/validator PASS, changed-symbol-to-test mapping, applicable new/updated tests, targeted/affected checks, requested/risk-required broad checks, diff check, and evidence bundle. Evidence records direct command exits and bounded output. Failure returns `review: NOT_RUN`; planner terminalizes the failed dispatch before the authorized local validation-repair sequence or structural replan.

Executor `DEVIATION` is terminal evidence without validator `GATE_REPORT`: planner deactivates dispatch and returns profile planning authority. Every non-deviation stage outcome uses validator-produced `GATE_REPORT`.

After planner records `CHECKPOINT_READY`, checkpointer writes one unique canonical request and invokes installed cross-platform helper with no shell arguments. Request binds all roots, reviewed filesystem/Git-object states, expected `HEAD`/branch, declared workspace paths, and Git-root-relative baseline-user paths. Helper supports nested workspaces, builds/verifies an isolated literal-path tree, refreshes only declared real-index entries, compare-and-swap advances expected branch, preserves non-workflow staged entries, verifies exact commit delta, recovers idempotently after artifact failure, computes `CHECKPOINT_COMMIT_ID`, and persists result. It never stashs, resets, restores, checks out, cleans, amends, rebases, squashes, merges, or pushes. Validator `ACCEPT_STAGE` verifies commit/tree/parent/inventory against reviewed snapshot, then creates immutable checkpoint manifest, delta, validation index, review index, and coverage ledger. Accepted stage commits remain in branch after final PASS.

## Mini review

Profiles:
- `LOW`: one `combined-low` lane;
- `STANDARD`: parallel `goal-scope`, `correctness-tests`, and `architecture-integration` lanes;
- `HIGH_RISK`: STANDARD plus `security-recovery`.

Validator `PREPARE_MINI_REVIEW` creates one immutable epoch manifest at `validation/review-epochs/<epoch>/manifest.json` and one lane input at `validation/review-epochs/<epoch>/inputs/<lens>.json`. Each lane receives only this current manifest, `REVIEW_INPUT_ID`, `REVIEW_EPOCH_ID`, `LANE_INPUT_ID`, complete assigned scope, and unique output at `reviews/mini/epochs/<epoch>/lanes/<lens>.md`. Stage inputs contain only previous accepted checkpoint-to-current frozen snapshot delta; final inputs contain immutable baseline artifact/initial-HEAD attribution, accepted checkpoint chain, and baseline-to-current cumulative workflow delta. Finding IDs are `<cycle>-<lens>-F###`.

Aggregation first verifies exact active epoch and all expected validator-owned lane inputs, preserves mechanical union with source review path/hash, then groups duplicate root causes without dropping or lowering findings. It records epoch, lane IDs, coverage, `MINI_REVIEW_BUNDLE_ID`, and `MINI_GATE: PASS|FAIL|BLOCKED|STALE`. A new `REVIEW_INPUT_ID` supersedes prior epoch in canonical planner state before dispatch; prior files remain audit-only. Reuse is forbidden after product, evidence, scope, or review-input change. Final cumulative review creates fresh lanes without reuse.

Required findings are acceptance violations, reachable regressions, change-caused architecture/contract breaks, security/data/trust violations, missing required evidence, or unintended/missing scope. Optional findings do not trigger repair.

Finding format:
`<ID> | required|optional | critical|high|medium|low | <path#symbol|artifact|contract> | criterion: <ID> | evidence: <fact> | impact: <concrete> | fix: <bounded>`

Each unresolved stage remains on its current checkpoint boundary until resolved; next stage never absorbs its review debt. `OPENAI_COLLABORATION` runs two mini-review/repair cycles, then sends current aggregate, validation, and current epoch to Terra escalation adjudication. Terra evaluates only demonstrated unresolved findings and their actual risks; it does not perform a speculative search for more findings. Terra `PASS` may resolve false-positive mini findings and permits checkpoint. A confirmed risk requires profile planning-authority repair/replan, then restarts two fresh mini cycles. Terra may return `WAITING_FOR_USER` only after its prior replan/repair for that cause completed and evidence proves no safe resolution within user contract. `SINGLE_MODEL` repeats fresh mini-review/repair cycles without numeric budget or user-decision terminal path. Numeric budget exhaustion alone never returns `BLOCKED`.

## Deviations

Executor reports facts, never self-approves variance. Dispatcher planner may record an implementation variance contained within existing result, ownership, contracts, and acceptance; include it in review scope. Contract, consistency boundary, security/persistence design, stage/DAG/wave/barrier/profile, or cross-stage ownership impact requires profile planning-authority replan and updated plan structure ID.

## Final gate

For each final product snapshot, primary calls planner `START_FINAL_CYCLE`; planner records cycle number, current IDs, open cause keys, and `FINAL_REVIEW_ACTIVE` in status before validation; primary reports this to user:
1. Run combined required validation and planner `FINAL_VALIDATION_RESULT`; repairable failure returns to unlimited authorized repair without checkpoint.
2. Regenerate cumulative patch, inventory, evidence bundle, review scope, and review input IDs.
3. Run fresh cumulative mini lanes and aggregation, then planner `FINAL_MINI_RESULT`; final-purpose failures never invoke stage escalation reviewer.
4. Required local mini findings get a consolidated repair batch through planner `AUTHORIZE_REPAIR`, validator `AUTHORIZE_DISPATCH`, planner `ACTIVATE_DISPATCH`, and executor; structural findings return to profile planning authority. Run validation and fresh final epoch. On repaired PASS run checkpointer, planner `CHECKPOINT_RESULT`, and planner `FINAL_REPAIR_RESULT`; call `START_FINAL_CYCLE` before restarting cumulative mini review. Validation/review failure closes repair dispatch without requiring checkpoint and continues unlimited repair.
5. For `OPENAI_COLLABORATION`, `MINI_GATE: PASS` creates `FINAL_REVIEW_INPUT_ID`; run fresh Terra review.
6. For `OPENAI_COLLABORATION`, `STALE`, BLOCKED, or FAIL goes directly to canonical planner state. Recoverable input regenerates final validation, cumulative artifacts, fresh mini lanes, and final input from step 1 without consuming a final cycle. Required local Terra findings use authorized repair and executor, then final validation, fresh final epoch/mini, checkpointer, `CHECKPOINT_RESULT`, `FINAL_REPAIR_RESULT`, and `START_FINAL_CYCLE`; structural findings return to profile planning authority.
7. For `OPENAI_COLLABORATION`, Terra PASS first runs validator `POST_REVIEW`. Unchanged product and mini bundle IDs then accompany PASS into canonical planner completion. Required repairable Terra findings restart final repair/validation/epoch review without numeric cycle limit. Repeated cause keys require recorded root-cause comparison and escalation rationale; identical repair cannot repeat silently.
8. For `SINGLE_MODEL`, `MINI_GATE: PASS` runs validator `POST_REVIEW` against current product and mini bundle. Unchanged identities make validator persist and return `FINAL_ASSURANCE: MINI_REVIEW_AND_IDENTITY_PASS`, permitting canonical planner completion. Any mismatch restarts final gate at step 1.

Final combined validation and mini/Terra review repairable findings continue through visible final cycles without numeric blocker limit. Structural failure escalates profile planning authority. In `OPENAI_COLLABORATION`, only Terra may enter `WAITING_FOR_USER` after Terra-directed replan/repair demonstrates external access, unsafe ambiguity, or required product decision; `SINGLE_MODEL` continues fresh review/repair cycles. New user input or materially different evidence records a new cause-key history.

Final reviewers persist exact verdicts. Terra finding IDs are `T<cycle>-F###`.

## Handoffs

Use paths and IDs instead of dumps. Every task prompt supplies its exact mode, allowed writes, expected artifact, and compact report schema. Every response includes `PROTOCOL_VERSION: 3`.

Executor:
`EXECUTOR_REPORT | <stage|repair> | PASS|FAIL|BLOCKED|DEVIATION|STALE | product: <paths|none> | expected-product: <ID> | authorization: <ID> | validation: PASS|FAIL|BLOCKED | evidence: <path|required for PASS> | blocker: <none|exact>`

Gate:
`GATE_REPORT | <stage> | PASS|FAIL|BLOCKED|DEVIATION|STALE | readiness: PASS|FAIL|BLOCKED | review: PASS|FAIL|NOT_RUN | findings: <IDs|none> | snapshot: <ID> | checkpoint: <ID|none> | accepted: <path|none> | evidence: <paths>`
