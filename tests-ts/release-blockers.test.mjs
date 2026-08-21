import assert from "node:assert/strict"
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"

import {
  ProtocolError,
  WorkflowStore,
  newState,
  reserveNext,
  stagesFromAnalysis,
  validateAnalysis,
  validateState,
} from "../runtime/orchestrator.js"

import { analysisFixture, event } from "./helpers.mjs"

const DIGEST = "0".repeat(64)

async function writeArtifact(root, relative, metadata, body = "# Artifact\n") {
  const destination = path.join(root, ...relative.split("/"))
  await mkdir(path.dirname(destination), { recursive: true })
  const lines = [
    "---",
    `schema_version: ${metadata.schema_version ?? 1}`,
    `artifact: ${metadata.artifact}`,
    `stage: ${metadata.stage ?? "none"}`,
    `revision: ${metadata.revision}`,
    `source_revision: ${metadata.source_revision ?? 0}`,
    `status: ${metadata.status}`,
    "---",
    body.trimEnd(),
    "",
  ]
  await writeFile(destination, lines.join("\n"), "utf8")
}

async function createStoreRoot(base) {
  const root = path.join(base, "1_orchestrator", "sample")
  await mkdir(root, { recursive: true })
  return root
}

async function advanceStoreToPlanning(base) {
  const root = await createStoreRoot(base)
  const analysis = analysisFixture()
  const store = new WorkflowStore(base, "sample")

  let reserved = await store.reserve()
  assert.equal(reserved.action.action, "DISCOVER")
  await writeFile(path.join(root, "analysis.json"), JSON.stringify(analysis, null, 2) + "\n", "utf8")
  await writeArtifact(root, "discovery.md", {
    artifact: "discovery",
    revision: reserved.action.revision,
    source_revision: 0,
    status: "READY_FOR_REVIEW",
  })
  let applied = await store.apply(
    event(reserved.action, "discovery_result", { revision: reserved.action.revision, status: "READY_FOR_REVIEW" }),
    reserved.state.state_revision,
  )

  reserved = await store.reserve(applied.state.state_revision)
  assert.equal(reserved.action.action, "REVIEW_DISCOVERY")
  await writeArtifact(root, reserved.action.output, {
    artifact: "discovery-review",
    revision: reserved.action.revision,
    source_revision: reserved.action.revision,
    status: "PASS",
  })
  applied = await store.apply(
    event(reserved.action, "discovery_review_result", { revision: reserved.action.revision, status: "PASS" }),
    reserved.state.state_revision,
  )

  reserved = await store.reserve(applied.state.state_revision)
  assert.equal(reserved.action.action, "APPROVE_MAP")
  applied = await store.apply(
    event(reserved.action, "map_decision", { decision: "APPROVE" }),
    reserved.state.state_revision,
  )
  return { store, root, analysis, state: applied.state }
}

test("planner REVIEW is rejected when its reserved output artifact is absent", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-missing-plan-output-"))
  const { store, state } = await advanceStoreToPlanning(base)
  const reserved = await store.reserve(state.state_revision)
  assert.equal(reserved.action.action, "PLAN_STAGE")
  await assert.rejects(
    () => store.apply(
      event(reserved.action, "stage_plan_result", { revision: reserved.action.revision, status: "REVIEW" }),
      reserved.state.state_revision,
    ),
    ProtocolError,
  )
})

test("reviewer PASS is rejected when its reserved review artifact is absent", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-missing-review-output-"))
  const { store, root, state } = await advanceStoreToPlanning(base)
  let reserved = await store.reserve(state.state_revision)
  await writeArtifact(root, reserved.action.output, {
    artifact: "technical-stage",
    stage: reserved.action.stage,
    revision: reserved.action.revision,
    source_revision: reserved.action.source_revision ?? 1,
    status: "REVIEW",
  })
  let applied = await store.apply(
    event(reserved.action, "stage_plan_result", { revision: reserved.action.revision, status: "REVIEW" }),
    reserved.state.state_revision,
  )

  reserved = await store.reserve(applied.state.state_revision)
  assert.equal(reserved.action.action, "REVIEW_STAGE")
  await assert.rejects(
    () => store.apply(
      event(reserved.action, "stage_review_result", { revision: reserved.action.revision, status: "PASS" }),
      reserved.state.state_revision,
    ),
    ProtocolError,
  )
})

test("agent result is rejected when a reserved input changes", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-stale-input-"))
  const root = await createStoreRoot(base)
  await writeFile(path.join(root, "feedback.md"), "initial feedback\n", "utf8")
  const store = new WorkflowStore(base, "sample")
  const reserved = await store.reserve()
  assert.equal(reserved.action.action, "DISCOVER")

  await writeFile(path.join(root, "feedback.md"), "changed after reserve\n", "utf8")
  await writeFile(path.join(root, "analysis.json"), JSON.stringify(analysisFixture(), null, 2) + "\n", "utf8")
  await writeArtifact(root, "discovery.md", {
    artifact: "discovery",
    revision: reserved.action.revision,
    status: "READY_FOR_REVIEW",
  })

  await assert.rejects(
    () => store.apply(
      event(reserved.action, "discovery_result", { revision: reserved.action.revision, status: "READY_FOR_REVIEW" }),
      reserved.state.state_revision,
    ),
    /stale|changed|digest|snapshot/i,
  )
})

test("correction routing carries the review and previous artifact sources", () => {
  const analysis = validateAnalysis(analysisFixture())

  const discovery = newState("sample")
  discovery.status = "discovery"
  discovery.analysis_status = "draft"
  discovery.analysis_revision = 1
  discovery.convergence.DISCOVERY = { fingerprint: DIGEST, evidence_digest: DIGEST, repeats: 1, last_revision: 1 }
  const discoveryAction = reserveNext(discovery).action
  assert.ok(discoveryAction.inputs.includes("reviews/discovery.md"))

  const technical = newState("sample")
  technical.status = "planning"
  technical.analysis_status = "approved"
  technical.analysis_revision = 1
  technical.stages = stagesFromAnalysis(analysis)
  technical.current_stage = "S01"
  technical.stages[0].revision = 1
  technical.convergence["TECHNICAL:S01"] = { fingerprint: DIGEST, evidence_digest: DIGEST, repeats: 1, last_revision: 1 }
  const previousTechnical = technical.stages[0].details
  const previousTechnicalReview = technical.stages[0].review
  const technicalAction = reserveNext(technical, analysis).action
  assert.ok(technicalAction.inputs.includes(previousTechnical))
  assert.ok(technicalAction.inputs.includes(previousTechnicalReview))

  const human = newState("sample")
  human.status = "human_reviewing"
  human.analysis_status = "approved"
  human.analysis_revision = 1
  human.stages = stagesFromAnalysis(analysis)
  human.current_stage = "S01"
  for (const stage of human.stages) {
    stage.status = "pass"
    stage.revision = 1
  }
  human.stages[0].human_revision = 1
  human.convergence["HUMAN:S01"] = { fingerprint: DIGEST, evidence_digest: DIGEST, repeats: 1, last_revision: 1 }
  const previousHuman = human.stages[0].human_review
  const previousHumanReview = human.stages[0].human_review_review
  const humanAction = reserveNext(human, analysis).action
  assert.ok(humanAction.inputs.includes(previousHuman))
  assert.ok(humanAction.inputs.includes(previousHumanReview))
})

test("NFR applicability rejects duplicate categories and unbacked required claims", () => {
  const duplicate = analysisFixture()
  duplicate.nfr_applicability.push({
    category: "compatibility-migration",
    status: "not_applicable",
    evidence: "contradicts required entry",
    owner: null,
    acceptance: [],
  })
  assert.throws(() => validateAnalysis(duplicate), ProtocolError)

  const unbacked = analysisFixture()
  unbacked.nfrs[0].category = "performance-capacity"
  assert.throws(() => validateAnalysis(unbacked), ProtocolError)
})

test("legal-state matrix rejects READY and pending transitions without an approved PASS graph", () => {
  const emptyReady = newState("sample")
  emptyReady.status = "ready"
  emptyReady.analysis_status = "approved"
  assert.throws(() => validateState(emptyReady), ProtocolError)

  const pendingInReady = reserveNext(newState("sample")).state
  pendingInReady.status = "ready"
  pendingInReady.analysis_status = "approved"
  assert.throws(() => validateState(pendingInReady), ProtocolError)

  const emptyApproval = newState("sample")
  emptyApproval.status = "waiting_plan_approval"
  emptyApproval.analysis_status = "approved"
  assert.throws(() => validateState(emptyApproval), ProtocolError)
})

test("APPROVE_PLAN cannot be reserved without the complete current artifact graph", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-incomplete-approval-"))
  const root = await createStoreRoot(base)
  const analysis = validateAnalysis(analysisFixture())
  const state = newState("sample")
  state.status = "waiting_plan_approval"
  state.analysis_status = "approved"
  state.analysis_revision = 1
  state.stages = stagesFromAnalysis(analysis)
  for (const stage of state.stages) {
    stage.status = "pass"
    stage.revision = 1
    stage.human_status = "pass"
    stage.human_revision = 1
  }
  await mkdir(path.join(root, ".orchestrator"), { recursive: true })
  await writeFile(path.join(root, ".orchestrator", "state.json"), JSON.stringify(state, null, 2) + "\n", "utf8")
  await writeFile(path.join(root, "analysis.json"), JSON.stringify(analysis, null, 2) + "\n", "utf8")
  await assert.rejects(() => new WorkflowStore(base, "sample").reserve(), ProtocolError)
})

test("legacy validation backs up the source plan and next returns an actionable migration step", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-legacy-resume-"))
  const root = await createStoreRoot(base)
  const legacy = `---
status: ready
current_stage: none
---
# Legacy plan

## Stage map

### S01 — Первый этап
- Status: PASS
- Revision: 3
- Depends on: none
- Details: stages/01-first-stage.md
- Review: reviews/01.md
`
  await writeFile(path.join(root, "plan.md"), legacy, "utf8")
  const store = new WorkflowStore(base, "sample")
  await store.validate()
  assert.equal(await readFile(path.join(root, ".orchestrator", "legacy-plan.md"), "utf8"), legacy)
  const reserved = await store.reserve()
  assert.ok(["DISCOVER", "RESOLVE_BLOCKER"].includes(reserved.action.action))
  if (reserved.action.action === "RESOLVE_BLOCKER") {
    assert.match(reserved.action.reason, /analysis|migration|legacy/i)
  }
})
