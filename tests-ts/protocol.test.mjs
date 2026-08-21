
import assert from "node:assert/strict"
import test from "node:test"
import { ProtocolError, parseJsonStrict, validateAnalysis } from "../runtime/orchestrator.js"
import { analysisFixture } from "./helpers.mjs"

test("strict JSON rejects duplicate keys", () => assert.throws(() => parseJsonStrict('{"a":1,"a":2}'), ProtocolError))
test("analysis fixture satisfies executable traceability", () => assert.doesNotThrow(() => validateAnalysis(analysisFixture())))
test("contract consumer without producer dependency is rejected", () => {
  const analysis = analysisFixture()
  analysis.stages[1].depends_on = []
  assert.throws(() => validateAnalysis(analysis), /depend on producer/i)
})
