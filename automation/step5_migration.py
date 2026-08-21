from __future__ import annotations

from pathlib import Path
import sys

from common import compile_runtime, expect_failure, node_test, write_files


RENDER_TS = r'''
import { createHash } from "node:crypto"
import type { Analysis, JsonRecord, State } from "./schema.js"
import { ProtocolError } from "./schema.js"
import { newState } from "./state.js"

export interface LegacyStageSnapshot {
  id: string
  title: string
  slug: string
  status: "proposed" | "planning" | "review" | "pass"
  revision: number
  human_status: "pending" | "planning" | "review" | "pass"
  human_revision: number
  details: string
  review: string
  human_review: string
  human_review_review: string
  semantic_fingerprint: string | null
}

export interface LegacySnapshot {
  schema_version: 1
  request_id: string
  source_sha256: string
  stages: LegacyStageSnapshot[]
}

function yaml(value: string | null): string {
  return value === null ? "null" : value
}

export function renderPlan(state: State, analysis?: Analysis): string {
  const lines = [
    "---",
    `schema_version: ${state.schema_version}`,
    `request_id: ${state.request_id}`,
    `state_revision: ${state.state_revision}`,
    `status: ${state.status}`,
    `analysis_revision: ${state.analysis_revision}`,
    `analysis_status: ${state.analysis_status}`,
    `current_stage: ${yaml(state.current_stage)}`,
    `legacy_migrated: ${state.legacy_migrated}`,
    "---",
    "",
    `# Plan: ${state.request_id}`,
    "",
    `Workflow status: **${state.status}**`,
    "",
  ]
  if (analysis) {
    lines.push("## Request", "", analysis.request.summary, "")
    if (analysis.request.outcomes.length) {
      lines.push("### Outcomes", "", ...analysis.request.outcomes.map((item) => `- ${item}`), "")
    }
  }
  lines.push("## Stage map", "")
  if (!state.stages.length) lines.push("No approved stage map yet.", "")
  for (const stage of state.stages) {
    lines.push(
      `### ${stage.id}: ${stage.title}`,
      "",
      `- Slug: ${stage.slug}`,
      `- Depends on: ${stage.depends_on.length ? stage.depends_on.join(", ") : "none"}`,
      `- Technical status: ${stage.status}`,
      `- Technical revision: ${stage.revision}`,
      `- Human status: ${stage.human_status}`,
      `- Human revision: ${stage.human_revision}`,
      `- Technical artifact: ${stage.details}`,
      `- Technical review: ${stage.review}`,
      `- Human artifact: ${stage.human_review}`,
      `- Human review: ${stage.human_review_review}`,
      "",
    )
  }
  if (state.pending) {
    lines.push(
      "## Pending transition",
      "",
      `- Transition: ${state.pending.transition_id}`,
      `- Action: ${state.pending.action}`,
      `- Actor: ${state.pending.actor}`,
      `- Stage: ${yaml(state.pending.stage)}`,
      `- Revision: ${state.pending.revision ?? "null"}`,
      `- Reason: ${state.pending.reason}`,
      "",
    )
  }
  if (state.blocker) lines.push("## Blocker", "", `- Reason: ${state.blocker.reason}`, `- Detail: ${state.blocker.detail}`, "")
  return lines.join("\n").trimEnd() + "\n"
}

function normalizeStatus(value: string | undefined, fallback: LegacyStageSnapshot["status"]): LegacyStageSnapshot["status"] {
  const normalized = value?.trim().toLowerCase().replace(/^pass(?:ed)?$/, "pass")
  return new Set(["proposed", "planning", "review", "pass"]).has(normalized ?? "") ? normalized as LegacyStageSnapshot["status"] : fallback
}

function normalizeHumanStatus(value: string | undefined): LegacyStageSnapshot["human_status"] {
  const normalized = value?.trim().toLowerCase().replace(/^pass(?:ed)?$/, "pass")
  return new Set(["pending", "planning", "review", "pass"]).has(normalized ?? "") ? normalized as LegacyStageSnapshot["human_status"] : "pending"
}

function legacyValue(block: string, names: string[]): string | undefined {
  for (const name of names) {
    const match = block.match(new RegExp(`^\\s*(?:[-*]\\s*)?${name}\\s*:\\s*(.+?)\\s*$`, "im"))
    if (match) return match[1].replace(/^`|`$/g, "").trim()
  }
  return undefined
}

function canonicalLegacyPath(value: string | undefined, fallback: string): string {
  if (!value) return fallback
  const normalized = value.replace(/\\\\/g, "/").replace(/^\.\//, "")
  if (normalized.startsWith("../") || normalized.startsWith("/") || /^[A-Za-z]:\//.test(normalized)) return fallback
  return normalized
}

export function parseLegacySnapshot(content: string, requestId: string): LegacySnapshot {
  if (!content.trim()) throw new ProtocolError("legacy-plan.md", "must not be empty")
  const heading = /^(?:#{2,4})\s+(?:Stage\s+)?(S\d{2})\s*(?::|[-—])?\s*(.*?)\s*$/gim
  const matches = [...content.matchAll(heading)]
  const stages: LegacyStageSnapshot[] = []
  for (const [index, match] of matches.entries()) {
    const start = match.index ?? 0
    const end = index + 1 < matches.length ? matches[index + 1].index ?? content.length : content.length
    const block = content.slice(start, end)
    const id = match[1]
    const title = match[2]?.trim() || `Legacy ${id}`
    const ordinal = Number(id.slice(1))
    const rawSlug = legacyValue(block, ["Slug"])
    const slug = rawSlug && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(rawSlug) ? rawSlug : title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || `legacy-${id.toLowerCase()}`
    const revision = Math.max(0, Number.parseInt(legacyValue(block, ["Technical revision", "Revision"]) ?? "0", 10) || 0)
    const humanRevision = Math.max(0, Number.parseInt(legacyValue(block, ["Human revision"]) ?? "0", 10) || 0)
    const status = normalizeStatus(legacyValue(block, ["Technical status", "Status"]), revision > 0 ? "review" : "proposed")
    const humanStatus = normalizeHumanStatus(legacyValue(block, ["Human status"]))
    const prefix = String(ordinal).padStart(2, "0")
    const fingerprint = legacyValue(block, ["Semantic fingerprint", "Fingerprint"])
    stages.push({
      id,
      title,
      slug,
      status,
      revision: status === "pass" ? Math.max(1, revision) : revision,
      human_status: humanStatus,
      human_revision: humanStatus === "pass" ? Math.max(1, humanRevision) : humanRevision,
      details: canonicalLegacyPath(legacyValue(block, ["Technical artifact", "Details"]), `stages/${prefix}-${slug}.md`),
      review: canonicalLegacyPath(legacyValue(block, ["Technical review", "Review"]), `reviews/${prefix}.md`),
      human_review: canonicalLegacyPath(legacyValue(block, ["Human artifact"]), `stages/${prefix}-${slug}.human-review.md`),
      human_review_review: canonicalLegacyPath(legacyValue(block, ["Human review"]), `reviews/${prefix}-human-review.md`),
      semantic_fingerprint: fingerprint && /^[0-9a-f]{64}$/i.test(fingerprint) ? fingerprint.toLowerCase() : null,
    })
  }
  return {
    schema_version: 1,
    request_id: requestId,
    source_sha256: createHash("sha256").update(content).digest("hex"),
    stages,
  }
}

export function parseLegacyPlan(content: string, requestId: string): State {
  parseLegacySnapshot(content, requestId)
  const state = newState(requestId)
  state.legacy_migrated = true
  state.status = "discovery"
  state.analysis_status = "missing"
  state.stages = []
  state.current_stage = null
  return state
}

export function legacyFingerprintMatches(snapshot: LegacySnapshot, analysis: Analysis, stageId: string, fingerprint: (analysis: Analysis, stageId: string) => string): boolean {
  const legacy = snapshot.stages.find((stage) => stage.id === stageId)
  return Boolean(legacy?.status === "pass" && legacy.semantic_fingerprint && legacy.semantic_fingerprint === fingerprint(analysis, stageId))
}
'''


TEST = r'''
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
  const stageId = analysis.stages[0].id
  const fingerprint = semanticStageFingerprint(analysis, stageId)
  const source = [
    "# Legacy plan",
    `## ${stageId}: ${analysis.stages[0].title}`,
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
  changedContract.contracts.find((item) => item.producer === stageId || item.consumers.includes(stageId)).text += " changed"
  assert.equal(legacyFingerprintMatches(snapshot, changedContract, stageId, semanticStageFingerprint), false)

  const changedRisk = structuredClone(analysis)
  changedRisk.stages[0].risks.push("new risk")
  assert.equal(legacyFingerprintMatches(snapshot, changedRisk, stageId, semanticStageFingerprint), false)
})

test("legacy PASS without semantic fingerprint is not preserved", () => {
  const analysis = analysisFixture()
  const stageId = analysis.stages[0].id
  const snapshot = parseLegacySnapshot(`# Legacy\n## ${stageId}: Legacy\n- Status: PASS\n- Revision: 2\n`, "legacy")
  assert.equal(legacyFingerprintMatches(snapshot, analysis, stageId, semanticStageFingerprint), false)
})
'''


def patch_store(source: str) -> str:
    source = source.replace(
        'import { validateAnalysis } from "./analysis.js"',
        'import { semanticStageFingerprint, validateAnalysis } from "./analysis.js"',
        1,
    )
    source = source.replace(
        'import { assertCompleteArtifactGraph, assertInputSnapshotsCurrent, assertPendingOutputContracts, capturePendingSnapshots } from "./artifacts.js"',
        'import { assertArtifact, assertCompleteArtifactGraph, assertInputSnapshotsCurrent, assertPendingOutputContracts, capturePendingSnapshots } from "./artifacts.js"',
        1,
    )
    source = source.replace(
        'import { parseLegacyPlan, renderPlan } from "./render.js"',
        'import { parseLegacyPlan, parseLegacySnapshot, renderPlan } from "./render.js"\nimport type { LegacySnapshot } from "./render.js"',
        1,
    )
    source = source.replace(
        'import { migrateState, newState, validateState } from "./state.js"',
        'import { migrateState, newState, normalizeProgress, validateState } from "./state.js"',
        1,
    )
    source = source.replace(
        '  readonly stateV1BackupPath: string\n  readonly request: string',
        '  readonly stateV1BackupPath: string\n  readonly legacyBackupPath: string\n  readonly legacySnapshotPath: string\n  readonly request: string',
        1,
    )
    source = source.replace(
        '    this.stateV1BackupPath = path.join(this.internal, "state-v1.json")\n  }',
        '    this.stateV1BackupPath = path.join(this.internal, "state-v1.json")\n    this.legacyBackupPath = path.join(this.internal, "legacy-plan.md")\n    this.legacySnapshotPath = path.join(this.internal, "legacy-state.json")\n  }',
        1,
    )
    legacy_old = '    if (await exists(this.planPath)) return parseLegacyPlan(await readFile(this.planPath, "utf8"), this.request)\n    return newState(this.request)'
    legacy_new = '''    if (await exists(this.planPath)) {
      const content = await readFile(this.planPath, "utf8")
      if (!(await exists(this.legacyBackupPath))) await atomicWrite(this.legacyBackupPath, content)
      const snapshot = parseLegacySnapshot(content, this.request)
      await atomicWrite(this.legacySnapshotPath, `${JSON.stringify(snapshot, null, 2)}\\n`)
      return parseLegacyPlan(content, this.request)
    }
    return newState(this.request)'''
    if legacy_old not in source:
        raise RuntimeError("cannot patch legacy loadState block")
    source = source.replace(legacy_old, legacy_new, 1)

    insertion_marker = '  private async loadAnalysis(): Promise<Analysis | undefined> {'
    restoration = r'''
  private async loadLegacySnapshot(): Promise<LegacySnapshot | undefined> {
    return await exists(this.legacySnapshotPath) ? parseJsonFile(this.legacySnapshotPath) as LegacySnapshot : undefined
  }

  private async restoreLegacyPasses(state: State, analysis: Analysis): Promise<void> {
    const snapshot = await this.loadLegacySnapshot()
    if (!snapshot) {
      state.legacy_migrated = false
      return
    }
    for (const stage of state.stages) {
      const legacy = snapshot.stages.find((item) => item.id === stage.id)
      if (!legacy || legacy.status !== "pass" || !legacy.semantic_fingerprint) continue
      if (legacy.semantic_fingerprint !== semanticStageFingerprint(analysis, stage.id)) continue
      const revision = Math.max(1, legacy.revision)
      try {
        await assertArtifact(this.root, stage.details, {
          artifact: "technical-stage",
          stage: stage.id,
          revision,
          source_revision: state.analysis_revision,
          status: "REVIEW",
        })
        await assertArtifact(this.root, stage.review, {
          artifact: "technical-review",
          stage: stage.id,
          revision,
          source_revision: revision,
          status: "PASS",
        })
      } catch {
        continue
      }
      stage.status = "pass"
      stage.revision = revision
      if (legacy.human_status === "pass") {
        const humanRevision = Math.max(1, legacy.human_revision)
        try {
          await assertArtifact(this.root, stage.human_review, {
            artifact: "human-review",
            stage: stage.id,
            revision: humanRevision,
            source_revision: revision,
            status: "REVIEW",
          })
          await assertArtifact(this.root, stage.human_review_review, {
            artifact: "human-review-review",
            stage: stage.id,
            revision: humanRevision,
            source_revision: revision,
            status: "PASS",
          })
          stage.human_status = "pass"
          stage.human_revision = humanRevision
        } catch {
          stage.human_status = "pending"
          stage.human_revision = 0
        }
      }
    }
    state.legacy_migrated = false
    normalizeProgress(state)
    if (state.status === "planning") state.current_stage = state.stages.find((stage) => stage.status !== "pass")?.id ?? state.current_stage
    if (state.status === "human_reviewing") state.current_stage = state.stages.find((stage) => stage.human_status !== "pass")?.id ?? state.current_stage
  }

'''
    if insertion_marker not in source:
        raise RuntimeError("cannot insert legacy restoration methods")
    source = source.replace(insertion_marker, restoration + insertion_marker, 1)

    apply_old = '      const result = await applyEvent(this.base, state, event, analysis, expectedStateRevision)\n      if (JSON.stringify(result.state) !== JSON.stringify(state)) await this.commit(result.state, analysis, this.journal("apply", result.state, { transition_id: event.transition_id, event_type: event.type, result: result.result }))'
    apply_new = '      const result = await applyEvent(this.base, state, event, analysis, expectedStateRevision)\n      if (event.type === "map_decision" && payload.decision === "APPROVE" && result.state.legacy_migrated && analysis) await this.restoreLegacyPasses(result.state, analysis)\n      if (JSON.stringify(result.state) !== JSON.stringify(state)) await this.commit(result.state, analysis, this.journal("apply", result.state, { transition_id: event.transition_id, event_type: event.type, result: result.result }))'
    if apply_old not in source:
        raise RuntimeError("cannot patch map approval restoration")
    return source.replace(apply_old, apply_new, 1)


def apply(root: Path, log: Path) -> list[str]:
    test_path = "tests-ts/legacy-resume-hardening.test.mjs"
    changed = write_files(root, {test_path: TEST})
    expect_failure(["node", "--test", test_path], cwd=root, log=log)

    store_path = root / "src/store.ts"
    store_source = patch_store(store_path.read_text(encoding="utf-8"))
    changed += write_files(root, {
        "src/render.ts": RENDER_TS,
        "src/store.ts": store_source,
    })
    compile_runtime(root, log=log)
    node_test(root, [test_path], log=log)
    node_test(root, ["tests-ts/release-blockers.test.mjs"], pattern="legacy|validate.*next|backup", log=log)
    return changed + ["runtime"]


if __name__ == "__main__":
    repository = Path(sys.argv[1]).resolve()
    log = Path(sys.argv[2]).resolve()
    print("\n".join(apply(repository, log)))
