
import assert from "node:assert/strict"
import { mkdir, mkdtemp, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"

import { WorkflowStore } from "../runtime/orchestrator.js"
import { analysisFixture, event, writeArtifact } from "./helpers.mjs"

test("complete store journey creates and validates real artifacts", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-real-journey-"))
  const root = path.join(base, "1_orchestrator", "journey")
  await mkdir(root, { recursive: true })
  const store = new WorkflowStore(base, "journey")
  const analysis = analysisFixture()

  let step = await store.reserve()
  await writeFile(path.join(root, "analysis.json"), JSON.stringify(analysis, null, 2) + "\n")
  await writeArtifact(root, "discovery.md", { artifact: "discovery", revision: 1, source_revision: 0, status: "READY_FOR_REVIEW" })
  let applied = await store.apply(event(step.action, "discovery_result", { revision: 1, status: "READY_FOR_REVIEW" }), step.state.state_revision)
  assert.equal(applied.state.status, "discovery_review")

  step = await store.reserve(applied.state.state_revision)
  await writeArtifact(root, "reviews/discovery.md", { artifact: "discovery-review", revision: 1, source_revision: 1, status: "PASS" })
  applied = await store.apply(event(step.action, "discovery_review_result", { revision: 1, status: "PASS", findings: [], evidence: ["analysis schema", "discovery evidence"] }), step.state.state_revision)
  assert.equal(applied.state.status, "waiting_map_approval")

  step = await store.reserve(applied.state.state_revision)
  applied = await store.apply(event(step.action, "map_decision", { decision: "APPROVE" }), step.state.state_revision)
  assert.equal(applied.state.status, "planning")

  for (const expectedStage of ["S01", "S02"]) {
    step = await store.reserve(applied.state.state_revision)
    assert.equal(step.action.action, "PLAN_STAGE")
    assert.equal(step.action.stage, expectedStage)
    await writeArtifact(root, step.action.output, { artifact: "technical-stage", stage: expectedStage, revision: step.action.revision, source_revision: step.action.source_revision, status: "REVIEW" })
    applied = await store.apply(event(step.action, "stage_plan_result", { revision: step.action.revision, status: "REVIEW" }), step.state.state_revision)

    step = await store.reserve(applied.state.state_revision)
    assert.equal(step.action.action, "REVIEW_STAGE")
    await writeArtifact(root, step.action.output, { artifact: "technical-review", stage: expectedStage, revision: step.action.revision, source_revision: step.action.source_revision, status: "PASS" })
    applied = await store.apply(event(step.action, "stage_review_result", { revision: step.action.revision, status: "PASS", findings: [], evidence: ["technical artifact"] }), step.state.state_revision)
  }
  assert.equal(applied.state.status, "human_reviewing")

  for (const expectedStage of ["S01", "S02"]) {
    step = await store.reserve(applied.state.state_revision)
    assert.equal(step.action.action, "PLAN_HUMAN_REVIEW")
    await writeArtifact(root, step.action.output, { artifact: "human-review", stage: expectedStage, revision: step.action.revision, source_revision: step.action.source_revision, status: "REVIEW" })
    applied = await store.apply(event(step.action, "human_plan_result", { revision: step.action.revision, status: "REVIEW" }), step.state.state_revision)

    step = await store.reserve(applied.state.state_revision)
    assert.equal(step.action.action, "REVIEW_HUMAN_REVIEW")
    await writeArtifact(root, step.action.output, { artifact: "human-review-review", stage: expectedStage, revision: step.action.revision, source_revision: step.action.source_revision, status: "PASS" })
    applied = await store.apply(event(step.action, "human_review_result", { revision: step.action.revision, status: "PASS", findings: [], evidence: ["human artifact"] }), step.state.state_revision)
  }
  assert.equal(applied.state.status, "waiting_plan_approval")

  step = await store.reserve(applied.state.state_revision)
  assert.equal(step.action.action, "APPROVE_PLAN")
  assert.ok(step.action.inputs.includes("reviews/discovery.md"))
  assert.ok(step.action.inputs.includes("reviews/02-human-review.md"))
  applied = await store.apply(event(step.action, "plan_decision", { decision: "APPROVE" }), step.state.state_revision)
  assert.equal(applied.state.status, "ready")

  const complete = await store.reserve(applied.state.state_revision)
  assert.equal(complete.action.action, "COMPLETE")
  assert.equal((await store.validate()).valid, true)
})
