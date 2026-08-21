
import assert from "node:assert/strict"
import test from "node:test"
import { newState, requestReopen, stagesFromAnalysis } from "../runtime/orchestrator.js"
import { analysisFixture } from "./helpers.mjs"

test("reopening a passed stage includes transitive dependents and requires approval", () => {
  const analysis = analysisFixture()
  const state = newState("reopen")
  state.analysis_status = "approved"
  state.analysis_revision = 1
  state.stages = stagesFromAnalysis(analysis)
  for (const stage of state.stages) { stage.status = "pass"; stage.revision = 1; stage.human_status = "pass"; stage.human_revision = 1 }
  state.status = "ready"
  const reopened = requestReopen(state, ["S01"], "contract changed", "reviewer")
  assert.equal(reopened.status, "waiting_reopen_approval")
  assert.deepEqual(reopened.reopen.affected, ["S01", "S02"])
})
