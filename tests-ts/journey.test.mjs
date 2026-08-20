import assert from "node:assert/strict"
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"

import {
  ProtocolError,
  WorkflowStore,
  affectedStageClosure,
  applyEvent,
  newState,
  parseJsonStrict,
  reserveNext,
  validateAnalysis,
} from "../runtime/orchestrator.js"

import { analysisFixture, event, advanceToPlanning } from "./helpers.mjs"

test("deterministic uninterrupted workflow reaches COMPLETE", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-complete-"))
  let { state, analysis } = await advanceToPlanning(base)

  for (const stageId of ["S01", "S02"]) {
    let reserved = reserveNext(state, analysis)
    assert.equal(reserved.action.action, "PLAN_STAGE")
    assert.equal(reserved.action.stage, stageId)
    state = (await applyEvent(base, reserved.state, event(reserved.action, "stage_plan_result", { revision: 1, status: "REVIEW" }), analysis)).state
    reserved = reserveNext(state, analysis)
    assert.equal(reserved.action.action, "REVIEW_STAGE")
    state = (await applyEvent(base, reserved.state, event(reserved.action, "stage_review_result", { revision: 1, status: "PASS" }), analysis)).state
  }
  assert.equal(state.status, "human_reviewing")

  for (const stageId of ["S01", "S02"]) {
    let reserved = reserveNext(state, analysis)
    assert.equal(reserved.action.action, "PLAN_HUMAN_REVIEW")
    assert.equal(reserved.action.stage, stageId)
    state = (await applyEvent(base, reserved.state, event(reserved.action, "human_plan_result", { revision: 1, status: "REVIEW" }), analysis)).state
    reserved = reserveNext(state, analysis)
    assert.equal(reserved.action.action, "REVIEW_HUMAN_REVIEW")
    state = (await applyEvent(base, reserved.state, event(reserved.action, "human_review_result", { revision: 1, status: "PASS" }), analysis)).state
  }
  assert.equal(state.status, "waiting_plan_approval")

  let reserved = reserveNext(state, analysis)
  assert.equal(reserved.action.action, "APPROVE_PLAN")
  state = (await applyEvent(base, reserved.state, event(reserved.action, "plan_decision", { decision: "APPROVE" }), analysis)).state
  assert.equal(state.status, "ready")
  reserved = reserveNext(state, analysis)
  assert.equal(reserved.action.action, "COMPLETE")
  assert.equal(reserved.action.transition_id, null)
})
