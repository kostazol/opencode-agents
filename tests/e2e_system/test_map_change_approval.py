#!/usr/bin/env python3

from harness import SystemWorkspace, seed_plan, write_passed_stage
from fixture_validation import assert_fixture_state, replace_required


with SystemWorkspace(start_on_enter=False) as system:
    plan = seed_plan(system.workspace, [("PASS", "Value contract"), ("MAP_CHANGE_REQUIRED", "Value consumer"), ("PROPOSED", "Value docs")], "S02", "waiting-map-approval")
    write_passed_stage(system.workspace, 1, "Value contract")
    replace_required(plan, "- Revision: 0", "- Revision: 1", expected_count=2)
    replace_required(plan, "- Human review revision: 0", "- Human review revision: 1", expected_count=3)
    with plan.open("a", encoding="utf-8") as output:
        output.write("\n## Pending map change\n\n- Source: reviews/02.md\n- Evidence: consumer and docs share one observable contract.\n- Affected stages: S02, S03\n- Replacement entries:\n  - S02 — Потребитель и документация значения; Depends on S01; Affected area: модуль значения; Primary risks: нарушение контракта возврата; Consumes: контракт значения; Produces: документированный контракт значения; Details: stages/02-value-consumer-and-docs.md; Review: reviews/02.md; Human review: stages/02-value-consumer-and-docs.human-review.md; Human review review: reviews/02-human-review.md.\n  - S03 — Документация значения; Depends on S02; Affected area: документация значения; Primary risks: устаревшее описание контракта; Consumes: документированный контракт значения; Produces: документация значения; Details: stages/03-value-docs.md; Review: reviews/03.md; Human review: stages/03-value-docs.human-review.md; Human review review: reviews/03-human-review.md.\n")
    assert_fixture_state(plan, "waiting-map-approval", "S02", "S02", {"Status": "MAP_CHANGE_REQUIRED", "Revision": "1", "Human review revision": "1", "Human review status": "PENDING"})
    assert not (system.workspace / "1_orchestrator/e2e/stages/02-value-consumer.md").exists()
    assert not (system.workspace / "1_orchestrator/e2e/reviews/02.md").exists()
    system.start()
    messages = system.run_transition("RESUME: 1_orchestrator/e2e/plan.md\nAPPROVE MAP CHANGE")
    content = plan.read_text(encoding="utf-8")
    assert "status: planning" in content, (content, messages)
    assert "current_stage: S02" in content
    assert "- Status: PROPOSED" in content
    s02 = content.split("### S02", 1)[1]
    assert "- Revision: 2" in s02, s02
    assert "- Human review revision: 2" in s02, s02
    assert "- Human review status: PENDING" in s02, s02
    assert "- Details: stages/02-value-consumer-and-docs.md" in s02, s02
    assert "- Review: reviews/02.md" in s02, s02
    assert "- Human review: stages/02-value-consumer-and-docs.human-review.md" in s02, s02
    assert "- Human review review: reviews/02-human-review.md" in s02, s02
    s03 = content.split("### S03", 1)[1]
    assert "- Status: PROPOSED" in s03 and "- Revision: 2" in s03, s03
    assert "- Human review revision: 2" in s03 and "- Human review status: PENDING" in s03, s03
    assert "- Details: stages/03-value-docs.md" in s03 and "- Human review: stages/03-value-docs.human-review.md" in s03, s03
    system.assert_task_sequence(messages, [])
print("map change approval E2E passed")
