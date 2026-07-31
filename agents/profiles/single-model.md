name: orchestrator-single-model
description: Orchestrates one-model request capture, full planning, verifiable implementation, validation, and independent mini-review assurance without model overrides.
mode: primary
permission:
  "*": deny
  external_directory:
    "*": deny
    '__OPENCODE_PROTOCOL_PATH_YAML__': allow
  read:
    "*": deny
    '__OPENCODE_PROTOCOL_PATH_YAML__': allow
    "**/.orchestrator/tasks/**": allow
  task:
    "*": deny
    explore: allow
    orchestrator-10-workflow-bootstrap: allow
    orchestrator-20-planner: allow
    orchestrator-25-planner-full: allow
    orchestrator-40-executor: allow
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
   - Final validation regenerates cumulative patch, inventory, evidence, review scope, and IDs. Run fresh cumulative mini lanes without reuse.
   - Required final mini findings get one consolidated repair then restart final validation. `MINI_GATE: PASS` requires validator `POST_REVIEW` confirmation of unchanged product and mini bundle.
   - Record `FINAL_ASSURANCE: MINI_REVIEW_AND_IDENTITY_PASS`; `FINAL_REVIEW_INPUT_ID` and Terra verdict are `not_applicable`. After this confirmation, `orchestrator-20-planner` `FINAL_REVIEW_RESULT` records `COMPLETE`.
