from __future__ import annotations

from pathlib import Path
import sys

from common import compile_runtime, expect_failure, node_test, write_files


PROTOCOL_APPEND = r'''
function canonicalFingerprintJson(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value)
  if (Array.isArray(value)) return `[${value.map(canonicalFingerprintJson).join(",")}]`
  return `{${Object.entries(value as Record<string, unknown>)
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, item]) => `${JSON.stringify(key)}:${canonicalFingerprintJson(item)}`)
    .join(",")}}`
}

function validateNfrApplicabilityTraceability(analysis: Analysis): void {
  const stageById = new Map(analysis.stages.map((stage) => [stage.id, stage]))
  const acceptanceById = new Map(analysis.acceptance.map((acceptance) => [acceptance.id, acceptance]))
  const seen = new Map<string, string>()

  for (const [index, applicability] of analysis.nfr_applicability.entries()) {
    const field = `analysis.nfr_applicability[${index}]`
    const previous = seen.get(applicability.category)
    if (previous !== undefined) {
      throw new ProtocolError(`${field}.category`, previous === applicability.status ? "duplicate applicability category" : "contradictory applicability category", {
        category: applicability.category,
        first_status: previous,
        duplicate_status: applicability.status,
      })
    }
    seen.set(applicability.category, applicability.status)

    if (applicability.status !== "required") continue
    if (!applicability.owner) throw new ProtocolError(`${field}.owner`, "required category must have an owner stage")
    const owner = stageById.get(applicability.owner)
    if (!owner) throw new ProtocolError(`${field}.owner`, "required category owner must be a real stage", applicability.owner)

    const matching = analysis.nfrs.filter((nfr) => nfr.category === applicability.category && nfr.stage === applicability.owner)
    if (!matching.length) {
      throw new ProtocolError(field, "required category must have a real NFR with the same category and owner stage", {
        category: applicability.category,
        owner: applicability.owner,
      })
    }
    const matchingIds = new Set(matching.map((nfr) => nfr.id))
    for (const nfr of matching) {
      if (!owner.nfrs.includes(nfr.id)) throw new ProtocolError(`${field}.owner`, "owner stage must list the matching NFR", nfr.id)
    }

    const linkedAcceptance = new Set(matching.flatMap((nfr) => nfr.acceptance))
    if (!applicability.acceptance.length) throw new ProtocolError(`${field}.acceptance`, "required category must have linked acceptance")
    for (const acceptanceId of applicability.acceptance) {
      if (!linkedAcceptance.has(acceptanceId)) {
        throw new ProtocolError(`${field}.acceptance`, "acceptance must be linked by an NFR of this category and owner", {
          acceptance: acceptanceId,
          matching_nfrs: [...matchingIds],
        })
      }
      const acceptance = acceptanceById.get(acceptanceId)
      if (!acceptance || acceptance.stage !== applicability.owner) {
        throw new ProtocolError(`${field}.acceptance`, "acceptance must belong to the owner stage", acceptanceId)
      }
    }
  }
}

export function validateAnalysis(input: unknown): Analysis {
  const analysis = validateAnalysisBase(input)
  validateNfrApplicabilityTraceability(analysis)
  return analysis
}

export function semanticStageFingerprint(analysisInput: unknown, stageIdValue: string): string {
  const analysis = validateAnalysis(analysisInput)
  const stage = analysis.stages.find((item) => item.id === stageIdValue)
  if (!stage) throw new ProtocolError("stage", "unknown stage for semantic fingerprint", stageIdValue)
  const requirementIds = new Set(stage.requirements)
  const nfrIds = new Set(stage.nfrs)
  const requirements = analysis.requirements.filter((item) => item.stage === stage.id || requirementIds.has(item.id))
  const nfrs = analysis.nfrs.filter((item) => item.stage === stage.id || nfrIds.has(item.id))
  const contractIds = new Set([...stage.contracts_consumed, ...stage.contracts_produced])
  const contracts = analysis.contracts.filter((item) => item.producer === stage.id || item.consumers.includes(stage.id) || contractIds.has(item.id))
  const acceptanceIds = new Set([...requirements.flatMap((item) => item.acceptance), ...nfrs.flatMap((item) => item.acceptance)])
  const scenarioIds = new Set([...requirements.flatMap((item) => item.scenarios), ...nfrs.flatMap((item) => item.scenarios)])
  const applicability = analysis.nfr_applicability.filter((item) => item.owner === stage.id || nfrs.some((nfr) => nfr.category === item.category))
  const semantic = {
    stage: {
      id: stage.id,
      title: stage.title,
      slug: stage.slug,
      depends_on: stage.depends_on,
      affected_area: stage.affected_area,
      risks: stage.risks,
    },
    requirements,
    nfrs,
    contracts,
    acceptance: analysis.acceptance.filter((item) => item.stage === stage.id || acceptanceIds.has(item.id)),
    scenarios: analysis.scenarios.filter((item) => item.stage === stage.id || scenarioIds.has(item.id)),
    applicability,
    decisions: analysis.decisions,
  }
  return createHash("sha256").update(canonicalFingerprintJson(semantic)).digest("hex")
}
'''


TEST = r'''
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
  assert.throws(() => validateAnalysis(duplicate), /duplicate applicability category/i)

  const contradictory = analysisFixture()
  const copy = structuredClone(contradictory.nfr_applicability[0])
  copy.status = copy.status === "required" ? "deferred" : "required"
  contradictory.nfr_applicability.push(copy)
  assert.throws(() => validateAnalysis(contradictory), /contradictory applicability category/i)
})

test("required category needs a real NFR with the same category and owner", () => {
  const analysis = analysisFixture()
  const entry = requiredEntry(analysis)
  entry.category = "security-privacy-compliance"
  assert.throws(() => validateAnalysis(analysis), /same category and owner stage/i)
})

test("required category acceptance must be linked by its matching NFR", () => {
  const analysis = analysisFixture()
  const entry = requiredEntry(analysis)
  const matching = analysis.nfrs.find((item) => item.category === entry.category && item.stage === entry.owner)
  assert.ok(matching)
  const unrelated = analysis.acceptance.find((item) => !matching.acceptance.includes(item.id))
  assert.ok(unrelated)
  entry.acceptance = [unrelated.id]
  assert.throws(() => validateAnalysis(analysis), /linked by an NFR/i)
})

test("semantic stage fingerprint includes REQ, NFR, contracts, and risks", () => {
  const source = analysisFixture()
  const stage = source.stages[0].id
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
  risk.stages[0].risks.push("new semantic risk")
  variants.push(risk)

  for (const variant of variants) assert.notEqual(semanticStageFingerprint(variant, stage), baseline)
})

test("valid NFR traceability remains accepted", () => {
  assert.doesNotThrow(() => validateAnalysis(analysisFixture()))
})
'''


def apply(root: Path, log: Path) -> list[str]:
    test_path = "tests-ts/nfr-adversarial.test.mjs"
    changed = write_files(root, {test_path: TEST})
    expect_failure(["node", "--test", test_path], cwd=root, log=log)

    analysis_path = root / "src/analysis.ts"
    source = analysis_path.read_text(encoding="utf-8")
    export_marker = "export function validateAnalysis("
    if export_marker not in source or "validateNfrApplicabilityTraceability" in source:
        raise RuntimeError("unexpected analysis.ts shape before protocol patch")
    if 'from "node:crypto"' not in source:
        source = 'import { createHash } from "node:crypto"\n' + source
    source = source.replace(export_marker, "function validateAnalysisBase(", 1)
    source = source.rstrip() + "\n\n" + PROTOCOL_APPEND.strip() + "\n"
    changed += write_files(root, {"src/analysis.ts": source})
    compile_runtime(root, log=log)
    node_test(root, [test_path], log=log)
    node_test(root, ["tests-ts/release-blockers.test.mjs"], pattern="NFR|applicability|category", log=log)
    return changed + ["runtime"]


if __name__ == "__main__":
    repository = Path(sys.argv[1]).resolve()
    log = Path(sys.argv[2]).resolve()
    print("\n".join(apply(repository, log)))
