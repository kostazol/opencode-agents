from __future__ import annotations

from final_common import prepare

prepare.step4_protocol.TEST = r'''
import assert from "node:assert/strict"
import test from "node:test"

import {
  ProtocolError,
  semanticStageFingerprint,
  validateAnalysis,
} from "../runtime/orchestrator.js"
import { analysisFixture } from "./helpers.mjs"

function requiredEntry(analysis) {
  const entry = analysis.nfr_applicability.find((item) => item.status === "required")
  assert.ok(entry, "fixture must contain a required NFR applicability entry")
  return entry
}

test("duplicate and contradictory applicability categories are rejected", () => {
  const duplicate = analysisFixture()
  duplicate.nfr_applicability.push(structuredClone(duplicate.nfr_applicability[0]))
  assert.throws(() => validateAnalysis(duplicate), ProtocolError)

  const contradictory = analysisFixture()
  const copy = structuredClone(contradictory.nfr_applicability[0])
  copy.status = "deferred"
  copy.owner = null
  copy.acceptance = []
  contradictory.nfr_applicability.push(copy)
  assert.throws(() => validateAnalysis(contradictory), ProtocolError)
})

test("required category needs a real NFR with the same category and owner", () => {
  const analysis = analysisFixture()
  const entry = requiredEntry(analysis)
  const matching = analysis.nfrs.find((item) => item.category === entry.category && item.stage === entry.owner)
  assert.ok(matching)
  matching.category = "performance-capacity"
  assert.throws(() => validateAnalysis(analysis), ProtocolError)
})

test("required category acceptance must be linked by its matching NFR", () => {
  const analysis = analysisFixture()
  const entry = requiredEntry(analysis)
  const matching = analysis.nfrs.find((item) => item.category === entry.category && item.stage === entry.owner)
  assert.ok(matching)
  const unrelated = analysis.acceptance.find((item) => item.stage === entry.owner && !matching.acceptance.includes(item.id))
  assert.ok(unrelated)
  entry.acceptance = [unrelated.id]
  assert.throws(() => validateAnalysis(analysis), ProtocolError)
})

test("semantic stage fingerprint includes REQ, NFR, contracts, and risks", () => {
  const source = analysisFixture()
  const stage = source.stages.find((item) => item.nfrs.length > 0).id
  const baseline = semanticStageFingerprint(source, stage)

  const variants = []
  const requirement = structuredClone(source)
  requirement.requirements.find((item) => item.stage === stage).text += " changed"
  variants.push(requirement)

  const nfr = structuredClone(source)
  nfr.nfrs.find((item) => item.stage === stage).text += " changed"
  variants.push(nfr)

  const contract = structuredClone(source)
  const relatedContract = contract.contracts.find((item) => item.producer === stage || item.consumers.includes(stage))
  assert.ok(relatedContract)
  relatedContract.text += " changed"
  variants.push(contract)

  const risk = structuredClone(source)
  risk.stages.find((item) => item.id === stage).risks.push("new semantic risk")
  variants.push(risk)

  for (const variant of variants) assert.notEqual(semanticStageFingerprint(variant, stage), baseline)
})

test("valid NFR traceability remains accepted", () => {
  assert.doesNotThrow(() => validateAnalysis(analysisFixture()))
})
'''
