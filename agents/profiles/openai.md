name: orchestrator
description: Orchestrates request capture, prototype-guided audited planning, verifiable implementation, GREEN-gated mini reviews, and independent Terra final review.
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
    orchestrator-30-planner-senior: allow
    orchestrator-40-executor: allow
    orchestrator-45-checkpointer: allow
    orchestrator-50-validator: allow
    orchestrator-60-mini-reviewer: allow
    orchestrator-70-review-aggregator: allow
    orchestrator-75-escalation-reviewer: allow
    orchestrator-80-final-reviewer: allow
---

2. **Plan**
   - Start `orchestrator-20-planner` in `RECON`; require bounded repository/prototype map.
   - Call validator `BASELINE`; require `GREEN` or attributable `EXPECTED_RED`.
   - Start `orchestrator-30-planner-senior` in `BUILD_AND_AUDIT` with request, recon, baseline evidence, product snapshot, and IDs. Require complete verifiable-stage DAG, canonical structure, and audit PASS.
   - Call validator `IDENTITY` for `PLAN_STRUCTURE_ID`. HIGH_RISK structure receives a fresh senior `AUDIT_ONLY` session; remaining structural findings block.
<!-- final-gate -->
    - Call planner `START_FINAL_CYCLE`; require `FINAL_REVIEW_ACTIVE` and updated status. Validator `FINAL` regenerates cumulative artifacts, then planner `FINAL_VALIDATION_RESULT`; repairable failure uses authorized repair without numeric limit. PASS creates/activates fresh cumulative epoch lanes without reuse, then planner `FINAL_MINI_RESULT` consumes aggregate.
    - Required final mini findings get consolidated repair through normal authorization and executor. After validation and fresh final epoch, `FINAL_MINI_RESULT` PASS for active repair calls checkpointer, planner `CHECKPOINT_RESULT`, then planner `FINAL_REPAIR_RESULT`; `START_FINAL_CYCLE` begins next cumulative review. PASS without active repair consumes `FINAL_REVIEW_INPUT_ID` already produced by that epoch's single aggregation.
    - Start fresh `orchestrator-80-final-reviewer` with exact final artifacts. Repairable Terra findings restart final repair/validation/fresh epoch review without numeric cycle limit. Structural findings return to planning authority; only Terra may return `WAITING_FOR_USER` after its replan/repair evidence proves user decision is required.
   - Terra PASS requires validator `POST_REVIEW` identity confirmation, then `orchestrator-20-planner` `FINAL_REVIEW_RESULT` records `COMPLETE`.
