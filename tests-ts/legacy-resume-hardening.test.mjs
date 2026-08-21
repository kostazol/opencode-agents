
import assert from "node:assert/strict"
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"

import {
  WorkflowStore,
  legacyFingerprintMatches,
  parseLegacySnapshot,
  semanticStageFingerprint,
} from "../runtime/orchestrator.js"
import { analysisFixture } from "./helpers.mjs"

test("legacy validate backs up plan byte-for-byte and next returns explicit discovery migration", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-legacy-resume-"))
  const root = path.join(base, "1_orchestrator", "legacy")
  await mkdir(root, { recursive: true })
  const legacy = [
    "---",
    "request_id: legacy",
    "status: planning",
    "current_stage: S01",
    "---",
    "# Legacy plan",
    "",
    "## S01: Legacy stage",
    "- Status: PASS",
    "- Revision: 4",
    "",
  ].join("\n")
  await writeFile(path.join(root, "plan.md"), legacy, "utf8")

  const store = new WorkflowStore(base, "legacy")
  const validation = await store.validate()
  assert.equal(validation.valid, true)
  assert.equal(await readFile(path.join(root, ".orchestrator", "legacy-plan.md"), "utf8"), legacy)

  const next = await store.reserve(validation.state_revision)
  assert.equal(next.action.action, "DISCOVER")
  assert.equal(next.action.mode, "LEGACY_MIGRATION")
  assert.ok(next.action.inputs.includes(".orchestrator/legacy-plan.md"))
})

test("legacy PASS is eligible only for exact semantic fingerprint", () => {
  const analysis = analysisFixture()
  const stageId = analysis.stages.find((item) => item.nfrs.length > 0).id
  const fingerprint = semanticStageFingerprint(analysis, stageId)
  const source = [
    "# Legacy plan",
    `## ${stageId}: ${analysis.stages.find((item) => item.id === stageId).title}`,
    "- Status: PASS",
    "- Revision: 3",
    `- Semantic fingerprint: ${fingerprint}`,
    "",
  ].join("\n")
  const snapshot = parseLegacySnapshot(source, "legacy")
  assert.equal(legacyFingerprintMatches(snapshot, analysis, stageId, semanticStageFingerprint), true)

  const changedRequirement = structuredClone(analysis)
  changedRequirement.requirements.find((item) => item.stage === stageId).text += " changed"
  assert.equal(legacyFingerprintMatches(snapshot, changedRequirement, stageId, semanticStageFingerprint), false)

  const changedNfr = structuredClone(analysis)
  changedNfr.nfrs.find((item) => item.stage === stageId).text += " changed"
  assert.equal(legacyFingerprintMatches(snapshot, changedNfr, stageId, semanticStageFingerprint), false)

  const changedContract = structuredClone(analysis)
  const contract = changedContract.contracts.find((item) => item.producer === stageId || item.consumers.includes(stageId))
  assert.ok(contract)
  contract.text += " changed"
  assert.equal(legacyFingerprintMatches(snapshot, changedContract, stageId, semanticStageFingerprint), false)

  const changedRisk = structuredClone(analysis)
  changedRisk.stages.find((item) => item.id === stageId).risks.push("new risk")
  assert.equal(legacyFingerprintMatches(snapshot, changedRisk, stageId, semanticStageFingerprint), false)
})

test("legacy PASS without semantic fingerprint is not preserved", () => {
  const analysis = analysisFixture()
  const stageId = analysis.stages[0].id
  const snapshot = parseLegacySnapshot(`# Legacy\n## ${stageId}: Legacy\n- Status: PASS\n- Revision: 2\n`, "legacy")
  assert.equal(legacyFingerprintMatches(snapshot, analysis, stageId, semanticStageFingerprint), false)
})
