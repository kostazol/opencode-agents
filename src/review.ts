import { createHash } from "node:crypto"
import { readFile } from "node:fs/promises"
import path from "node:path"
import { AGENT_ACTIONS, EVENT_BY_ACTION, REPEAT_LIMIT, Analysis, EventInput, JsonRecord, PendingAction, ProtocolError, StageState, State, affectedStageClosure, array, boolean, canonicalRelative, clone, exactFields, record, strings, text, validateAnalysis } from "./orchestrator.js"
import { normalizeProgress, sha, stableJson, stageMap, stagesFromAnalysis, validateState } from "./state.js"

function isWithin(base: string, candidate: string): boolean {
  const relative = path.relative(path.resolve(base), path.resolve(candidate))
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative))
}

export function choice(payload: JsonRecord, field: string, values: string[]): string {
  const value = payload[field]
  if (typeof value !== "string" || !values.includes(value)) throw new ProtocolError(`event.payload.${field}`, "unsupported value", value)
  return value
}

export function requireRevision(payload: JsonRecord, expected: number): void {
  if (payload.revision !== expected) throw new ProtocolError("event.payload.revision", `must equal reserved revision ${expected}`, payload.revision)
}

export function block(state: State, pending: PendingAction, reason: string, detail: string, retryable = true): JsonRecord {
  const resume = state.status
  state.status = "blocked"
  state.blocker = { reason, detail, resume_status: resume, retryable, source_transition: pending.transition_id }
  return { status: "blocked", reason, retryable }
}

async function evidenceSignature(base: string, payload: JsonRecord): Promise<{ fingerprint: string; evidence: string; summary: string }> {
  const raw = array(payload.findings, "event.payload.findings")
  if (!raw.length) throw new ProtocolError("event.payload.findings", "REVISE requires findings")
  const identities: Array<[string, string]> = []
  const evidence: Array<[string, string, string, string]> = []
  const summary: string[] = []
  for (const [index, value] of raw.entries()) {
    const item = record(value, `event.payload.findings[${index}]`)
    exactFields(item, ["code", "scope", "message", "evidence"], `event.payload.findings[${index}]`)
    const code = text(item.code, `event.payload.findings[${index}].code`).toUpperCase()
    const scope = text(item.scope, `event.payload.findings[${index}].scope`).toLowerCase()
    const message = text(item.message, `event.payload.findings[${index}].message`).replace(/\s+/g, " ")
    const paths = strings(item.evidence, `event.payload.findings[${index}].evidence`, false)
    identities.push([code, scope])
    for (const relative of paths) {
      const canonical = canonicalRelative(relative, `event.payload.findings[${index}].evidence`)
      const absolute = path.resolve(base, canonical)
      if (!isWithin(base, absolute)) throw new ProtocolError("event.payload.findings.evidence", "path escapes workflow base", canonical)
      let content: string
      try {
        content = await readFile(absolute, "utf8")
      } catch (error) {
        throw new ProtocolError("event.payload.findings.evidence", "evidence file is unavailable", { path: canonical, error: String(error) })
      }
      evidence.push([code, scope, canonical, sha(content)])
    }
    summary.push(`${code}@${scope}: ${message}`)
  }
  if (new Set(identities.map((item) => item.join("@"))).size !== identities.length) throw new ProtocolError("event.payload.findings", "duplicate code/scope")
  identities.sort()
  evidence.sort()
  return { fingerprint: sha(identities), evidence: sha(evidence), summary: summary.join("; ") }
}

export async function recordRevise(base: string, state: State, key: string, revision: number, payload: JsonRecord): Promise<{ stalled: boolean; summary: string }> {
  const signature = await evidenceSignature(base, payload)
  const previous = state.convergence[key]
  const repeats = previous && previous.fingerprint === signature.fingerprint && previous.evidence_digest === signature.evidence ? previous.repeats + 1 : 1
  state.convergence[key] = { fingerprint: signature.fingerprint, evidence_digest: signature.evidence, repeats, last_revision: revision }
  return { stalled: repeats >= REPEAT_LIMIT, summary: signature.summary }
}

export function proposeReopen(state: State, analysis: Analysis, payload: JsonRecord, requestedBy: "reviewer" | "user"): JsonRecord {
  const seeds = strings(payload.affected_stages, "event.payload.affected_stages", false)
  const reason = text(payload.reason ?? payload.remarks, "event.payload.reason").replace(/\s+/g, " ")
  const affected = affectedStageClosure(analysis, seeds)
  state.reopen = { requested_by: requestedBy, reason, seeds, affected, resume_status: state.status, resume_stage: state.current_stage }
  state.status = "waiting_reopen_approval"
  return { status: state.status, affected, reason }
}

export function applyReopen(state: State, analysis: Analysis, payload: JsonRecord): JsonRecord {
  if (!state.reopen) throw new ProtocolError("state.reopen", "no reopening proposal")
  const decision = choice(payload, "decision", ["APPROVE", "REJECT"])
  const proposal = state.reopen
  if (decision === "REJECT") {
    state.status = proposal.resume_status
    state.current_stage = proposal.resume_stage
    state.reopen = null
    return { status: state.status, reopened: [] }
  }
  const affected = affectedStageClosure(analysis, proposal.seeds)
  if (JSON.stringify(affected) !== JSON.stringify(proposal.affected)) throw new ProtocolError("state.reopen", "proposal is stale for current dependency graph")
  const stages = stageMap(state)
  for (const id of affected) {
    const stage = stages.get(id)!
    stage.status = "proposed"
    stage.human_status = "pending"
  }
  state.status = "planning"
  state.current_stage = affected[0]
  state.reopen = null
  state.convergence = Object.fromEntries(Object.entries(state.convergence).filter(([key]) => !affected.some((id) => key.includes(id))))
  return { status: state.status, reopened: affected, current_stage: state.current_stage }
}

export function feedbackText(payload: JsonRecord): string {
  return text(payload.remarks, "event.payload.remarks").replace(/\s+/g, " ")
}

