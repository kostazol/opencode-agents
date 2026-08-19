#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage
from fixture_validation import PlanFrontmatter, mutate_stage_map_entry, parse_plan_frontmatter, parse_stage_map_entry, validate_fixture_state


with SystemWorkspace(start_on_enter=False) as system:
    plan = seed_plan(system.workspace, [("PASS", "Value contract"), ("MAP_CHANGE_REQUIRED", "Value consumer"), ("PROPOSED", "Value docs")], "S02", "waiting-map-approval")
    write_passed_stage(system.workspace, 1, "Value contract")
    for stage_id in ("S02", "S03"):
        mutate_stage_map_entry(plan, stage_id, revision=1)
    for stage_id in ("S01", "S02", "S03"):
        mutate_stage_map_entry(plan, stage_id, human_review_revision=1)
    with plan.open("a", encoding="utf-8") as output:
        output.write("\n## Pending map change\n\n- Source: reviews/02.md\n- Evidence: consumer and docs share one observable contract.\n- Affected stages: S02, S03\n- Replacement entries:\n  - S02 — Потребитель и документация значения; Depends on S01; Affected area: модуль значения; Primary risks: нарушение контракта возврата; Consumes: контракт значения; Produces: документированный контракт значения; Details: stages/02-value-consumer-and-docs.md; Review: reviews/02.md; Human review: stages/02-value-consumer-and-docs.human-review.md; Human review review: reviews/02-human-review.md.\n  - S03 — Документация значения; Depends on S02; Affected area: документация значения; Primary risks: устаревшее описание контракта; Consumes: документированный контракт значения; Produces: документация значения; Details: stages/03-value-docs.md; Review: reviews/03.md; Human review: stages/03-value-docs.human-review.md; Human review review: reviews/03-human-review.md.\n")
    initial = parse_stage_map_entry(plan, "S02")
    assert (initial.status, initial.revision, initial.human_review_revision, initial.human_review_status) == ("MAP_CHANGE_REQUIRED", 1, 1, "PENDING"), initial
    validate_fixture_state(plan, "S01", system.workspace / "1_orchestrator/e2e/stages/01-value-contract.md", system.workspace / "1_orchestrator/e2e/reviews/01.md", expected_plan=PlanFrontmatter("waiting-map-approval", "S02"), expected_stage_status="PASS", expected_artifact_status="REVIEW", expected_review_status="PASS")
    validate_fixture_state(plan, "S02", expected_plan=PlanFrontmatter("waiting-map-approval", "S02"), expected_stage_status="MAP_CHANGE_REQUIRED")
    validate_fixture_state(plan, "S03", expected_plan=PlanFrontmatter("waiting-map-approval", "S02"), expected_stage_status="PROPOSED")
    assert not (system.workspace / "1_orchestrator/e2e/stages/02-value-consumer.md").exists()
    assert not (system.workspace / "1_orchestrator/e2e/reviews/02.md").exists()
    system.start()
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md\nAPPROVE MAP CHANGE")
    state = parse_plan_frontmatter(plan)
    assert state == PlanFrontmatter("planning", "S02"), (state, messages)
    s02 = parse_stage_map_entry(plan, "S02")
    assert (s02.status, s02.revision, s02.human_review_revision, s02.human_review_status) == ("PROPOSED", 2, 2, "PENDING"), s02
    assert (s02.details, s02.review, s02.human_review, s02.human_review_review) == ("stages/02-value-consumer-and-docs.md", "reviews/02.md", "stages/02-value-consumer-and-docs.human-review.md", "reviews/02-human-review.md"), s02
    s03 = parse_stage_map_entry(plan, "S03")
    assert (s03.status, s03.revision, s03.human_review_revision, s03.human_review_status) == ("PROPOSED", 2, 2, "PENDING"), s03
    assert (s03.details, s03.human_review) == ("stages/03-value-docs.md", "stages/03-value-docs.human-review.md"), s03
    system.assert_task_sequence(messages, [])
print("map change approval E2E passed")
