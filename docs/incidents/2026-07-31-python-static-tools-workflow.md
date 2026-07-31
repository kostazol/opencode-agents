# Incident analysis: Python static tools workflow

## Preservation record

- Analysis date: 2026-07-31.
- Source OpenCode session: `[REDACTED_SESSION]`.
- Source workspace: `[REDACTED_EXTERNAL_WORKSPACE]`.
- Workflow root reported by source session: `[REDACTED_EXTERNAL_WORKFLOW_ROOT]`.
- Evidence source: read-only OpenCode SQLite session archive and current Orchestrator v2 prompts/protocol in this repository.
- Source workflow artifacts were no longer present when this analysis ran. Findings below cite archived subagent results; do not treat missing external artifacts as independently revalidated product evidence.

## Immutable identifiers observed

Workflow content IDs were present and internally changed with product/review inputs. Exact external-workflow IDs are redacted from this public repository. Every historical review input/bundle remains audit-only until recovery revalidates canonical artifacts and current product identity.

## Reconstructed timeline

1. WPG validation passed with one frozen snapshot and review input.
2. First WPG mini lanes all returned `BLOCKED`: each lacked `LANE_INPUT_ID` or a lane-input manifest.
3. Validator was called in undocumented `REVIEW_INPUT_REPAIR` mode. It created `validation/lane-inputs/WPG-*.json`; retried WPG lanes passed; WPG aggregate passed; validator accepted WPG.
4. WP0 validation passed with a new snapshot and review input.
5. Initial WP0 mini lanes again lacked manifests. Goal-scope explicitly reported `validation/lane-inputs/WP0-goal-scope.json` absent and `LANE_INPUT_ID: unavailable`.
6. Another undocumented `REVIEW_INPUT_REPAIR` call created WP0 lane inputs. Retried WP0 lanes found four root causes: corpus binding, missing canonical/golden evidence, dependency on ignored workflow artifacts, and unvalidated symlink/special entries.
7. First WP0 repair changed product snapshot and review input. Aggregation returned `BLOCKED`: fresh required lanes were missing while a correctness finding remained. This was not a product finding; orchestration had incomplete current lane coverage.
8. A second validator stage call, without product mutation, regenerated evidence/review scope and produced another review input. This superseded the prior input despite unchanged product snapshot.
9. Four fresh lanes bound the current input and unique lane IDs. Goal, correctness, and architecture passed. Security-recovery failed with one required medium finding.
10. Final aggregate returned `MINI_GATE: FAIL` and a bounded local integrity repair requiring complete no-follow enumeration, special-entry rejection, exact frozen root set, canonical stored manifest comparison, validation, and fresh HIGH_RISK lanes.
11. Workflow stopped rather than dispatching this repair. Only WPG had an accepted checkpoint. WP0 never passed mini review and was not accepted.

## Evidence anchors

Archived external session identifiers and artifact IDs are redacted. Decisive evidence classes were initial missing lane inputs, ad hoc lane-input repair, accepted preparatory checkpoint, incomplete post-repair lane coverage, regenerated review identity, and final local security-recovery finding.

## Root causes

### 1. No protocol-owned producer or schema for lane inputs

Protocol defines `LANE_INPUT_ID` and requires every lane to receive it. Mini reviewer requires the ID and scope before writes. Aggregator requires current lane manifests. But protocol ID ownership names only bootstrap, validator, and aggregator; it does not assign `LANE_INPUT_ID` ownership. Validator modes omit lane-input creation and its write permissions do not define a canonical lane-input artifact contract.

Result: primary improvised `REVIEW_INPUT_REPAIR`, validator improvised an undocumented mode, and early review cycles blocked.

### 2. Review inputs were regenerated without epoch ownership

The same snapshot produced multiple review inputs because evidence/scope artifacts changed. This is legitimate identity invalidation, but protocol had no review epoch index that atomically marked prior lane manifests, verdicts, and aggregates superseded. Coordinator therefore attempted partial reuse and aggregation before all lanes bound current input.

Result: stale/duplicate lane handling became prompt-dependent instead of manifest-enforced.

### 3. Artifact paths were not cycle-unique

Archived lanes repeatedly used names such as `reviews/mini/lanes/WP0-goal-scope.md`. A retry or regenerated review input can collide with an earlier lane path. Reviewer requires a unique path, but no producer allocates one from a cycle/epoch. This prevents reliable coexistence, provenance, and stale-artifact rejection.

### 4. Repair budget converted repairable local finding into terminal stop

Protocol allows two stage repair batches per unchanged root cause, then says remaining required findings trigger replan or `BLOCKED`. WP0 had already run two repair dispatches. Final required finding was local to WP0 test/evidence ownership and had an explicit bounded repair. It did not require credentials, user acceptance, external access, or a structural design change.

Result: a medium security-recovery finding was treated as terminal solely because budget expired. This is a policy failure, not evidence that repair was impossible.

## Required design corrections

1. Assign validator exclusive ownership of lane-input manifests and `LANE_INPUT_ID` computation.
2. Add one documented validator mode, for example `PREPARE_MINI_REVIEW`, invoked after `STAGE` or `FINAL`; prohibit ad hoc validator modes.
3. Write immutable inputs to `validation/review-epochs/<epoch>/inputs/<lens>.json`. `epoch` must bind `REVIEW_INPUT_ID`, review cycle, and product snapshot.
4. Allocate immutable review outputs under `reviews/mini/epochs/<epoch>/lanes/<lens>.md` and one aggregate in same epoch. Aggregator accepts only exact current epoch manifest list.
5. On any new `REVIEW_INPUT_ID`, mark previous epoch `SUPERSEDED`; no lane, aggregate, bundle, or final input from it may drive repair, acceptance, or completion. Preserve it only for audit.
6. Remove lane reuse after product mutation. Permit reuse only if same epoch/input and aggregation retry without changed evidence; final cumulative review never reuses lanes.
7. Replace terminal budget exhaustion for local repairable findings with `REPAIR_REQUIRED` then escalation. Reserve `BLOCKED` for impossible work without external fact/user decision.
8. Record final-cycle state and progress: `FINAL_CYCLE_STARTED`, iteration, current snapshot/input, repeated cause keys, escalation level, and explicit user-interrupt status.

## Safe resume position

Do not resume any historical review lane or bundle. Preserve WPG as accepted only after checking its checkpoint against current workspace. Treat WP0 as unaccepted.

1. Recompute current product snapshot, inventory, validation, evidence bundle, review scope, and review input.
2. Create a new review epoch and all current lane-input manifests.
3. Dispatch bounded repair for the remaining integrity root cause if current plan/ownership still covers it; otherwise replan.
4. Run validation, then four fresh HIGH_RISK lanes and aggregate.
5. Continue later stages only after WP0 mini PASS and `ACCEPT_STAGE`.

No historical ID above authorizes mutation.
