
import assert from "node:assert/strict"
import test from "node:test"

import {
  ProtocolError,
  newState,
  reserveNext,
  stagesFromAnalysis,
  validateState,
} from "../runtime/orchestrator.js"
import { analysisFixture } from "./helpers.mjs"

const hash = "a".repeat(64)
const marker = (revision = 1) => ({ fingerprint: hash, evidence_digest: "b".repeat(64), repeats: 1, last_revision: revision })

function approvedState() {
  const analysis = analysisFixture()
  const state = newState("routing")
  state.analysis_revision = 1
  state.analysis_status = "approved"
  state.stages = stagesFromAnalysis(analysis)
  return { state, analysis }
}

test("discovery correction receives the failed discovery review", () => {
  const state = newState("discovery-correction")
  state.analysis_revision = 1
  state.analysis_status = "draft"
  state.convergence.DISCOVERY = marker()
  const result = reserveNext(state)
  assert.equal(result.action.mode, "CORRECTION")
  assert.ok(result.action.inputs.includes("reviews/discovery.md"))
  assert.ok(result.action.inputs.includes("discovery.md"))
})

test("technical correction receives current stage and failed technical review", () => {
  const { state, analysis } = approvedState()
  state.status = "planning"
  state.current_stage = "S01"
  state.stages[0].status = "planning"
  state.stages[0].revision = 2
  state.convergence["TECHNICAL:S01"] = marker(2)
  const result = reserveNext(state, analysis)
  assert.equal(result.action.mode, "TECHNICAL_CORRECTION")
  assert.ok(result.action.inputs.includes(state.stages[0].details))
  assert.ok(result.action.inputs.includes(state.stages[0].review))
})

test("human correction receives current human artifact and failed human review", () => {
  const { state, analysis } = approvedState()
  state.status = "human_reviewing"
  state.current_stage = "S01"
  for (const stage of state.stages) {
    stage.status = "pass"
    stage.revision = 1
  }
  state.stages[0].human_status = "planning"
  state.stages[0].human_revision = 2
  state.convergence["HUMAN:S01"] = marker(2)
  const result = reserveNext(state, analysis)
  assert.equal(result.action.mode, "HUMAN_REVIEW_CORRECTION")
  assert.ok(result.action.inputs.includes(state.stages[0].human_review))
  assert.ok(result.action.inputs.includes(state.stages[0].human_review_review))
})

test("ready and waiting_plan_approval reject empty or incomplete stage maps", () => {
  const empty = newState("impossible-ready")
  empty.status = "ready"
  empty.analysis_status = "approved"
  assert.throws(() => validateState(empty), ProtocolError)

  const { state } = approvedState()
  state.status = "waiting_plan_approval"
  state.current_stage = null
  assert.throws(() => validateState(state), ProtocolError)
})

test("pending action must be legal for status and current stage", () => {
  const { state, analysis } = approvedState()
  state.status = "planning"
  state.current_stage = "S01"
  state.stages[0].status = "planning"
  state.stages[0].revision = 1
  const reserved = reserveNext(state, analysis).state
  reserved.pending.action = "REVIEW_STAGE"
  assert.throws(() => validateState(reserved, analysis), /does not match|illegal/i)
})
