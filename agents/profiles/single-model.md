name: orchestrator-single-model
description: Orchestrates one-model request capture, full planning, verifiable implementation, validation, and independent mini-review assurance without model overrides.
mode: primary
permission:
  "*": deny
  external_directory:
    "*": deny
    '__OPENCODE_PROTOCOL_DIRECTORY_PATH_YAML__/*': allow
  read:
    "*": deny
    "*protocols/orchestrator-v2.md": allow
    ".orchestrator/tasks/**": allow
    "*/.orchestrator/tasks/**": allow
  task:
    "*": deny
    orchestrator-10-workflow-bootstrap: allow
    orchestrator-20-planner: allow
    orchestrator-25-planner-full: allow
    orchestrator-40-executor: allow
    orchestrator-45-checkpointer: allow
    orchestrator-50-validator: allow
    orchestrator-60-mini-reviewer: allow
    orchestrator-70-review-aggregator: allow
---

2. **Plan**
   - Start `orchestrator-25-planner-full` in `RECON`; require bounded repository/prototype map.
   - Call validator `BASELINE`; require `GREEN` or attributable `EXPECTED_RED`.
   - Resume mapped `orchestrator-25-planner-full` in `BUILD_AND_AUDIT` with request, recon, baseline evidence, product snapshot, and IDs. Require complete verifiable-stage DAG, canonical structure, and audit PASS.
   - Call validator `IDENTITY` for `PLAN_STRUCTURE_ID`. Structural findings return only to `orchestrator-25-planner-full` in `REPLAN_AND_AUDIT`.
<!-- final-gate -->
    - Call planner `START_FINAL_CYCLE`; require `FINAL_REVIEW_ACTIVE` and updated status. Validator `FINAL` regenerates cumulative artifacts, then planner `FINAL_VALIDATION_RESULT`; repairable failure uses authorized repair without numeric limit. PASS creates/activates fresh cumulative mini lanes without reuse, then planner `FINAL_MINI_RESULT` consumes aggregate.
    - Required final mini findings get consolidated repair through normal authorization and executor. After validation and fresh final epoch, `FINAL_MINI_RESULT` PASS for active repair calls checkpointer, planner `CHECKPOINT_RESULT`, then planner `FINAL_REPAIR_RESULT`; `START_FINAL_CYCLE` begins next cumulative review. Repairable findings continue without numeric/user-decision terminal path. PASS without active repair requires validator `POST_REVIEW` confirmation.
   - Validator `POST_REVIEW` persists and returns `FINAL_ASSURANCE: MINI_REVIEW_AND_IDENTITY_PASS`; `FINAL_REVIEW_INPUT_ID` and Terra verdict are `not_applicable`. After this confirmation, `orchestrator-20-planner` `FINAL_REVIEW_RESULT` records `COMPLETE`.
