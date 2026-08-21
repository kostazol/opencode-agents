
import assert from "node:assert/strict"
import test from "node:test"
import { parseLegacyPlan, parseLegacySnapshot } from "../runtime/orchestrator.js"

test("legacy parser keeps evidence in a separate snapshot and returns explicit discovery state", () => {
  const content = "# Legacy\n## S01: First\n- Status: PASS\n- Revision: 2\n"
  const snapshot = parseLegacySnapshot(content, "legacy")
  assert.equal(snapshot.stages[0].status, "pass")
  const state = parseLegacyPlan(content, "legacy")
  assert.equal(state.status, "discovery")
  assert.equal(state.legacy_migrated, true)
  assert.deepEqual(state.stages, [])
})
