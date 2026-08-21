from __future__ import annotations

from pathlib import Path
import sys

from common import expect_failure, write_files


ANALYSIS_TS = r'''
import { createHash } from "node:crypto"
import type { Analysis, AnalysisStage, JsonRecord } from "./schema.js"
import { ANALYSIS_SCHEMA_VERSION, CHANGE_SURFACES, NFR_CATEGORIES, ProtocolError, SURFACE_NFR, array, boolean, clone, exactFields, identifier, record, stageId, strings, text } from "./schema.js"

function sequential(items: Array<{ id: string }>, prefix: string, field: string): void {
  items.forEach((item, index) => {
    const expected = `${prefix}-${String(index + 1).padStart(3, "0")}`
    if (item.id !== expected) throw new ProtocolError(`${field}[${index}].id`, "identifiers must be contiguous and ordered", { expected, actual: item.id })
  })
}

function sameMembers(actual: string[], expected: string[], field: string): void {
  const left = [...actual].sort()
  const right = [...expected].sort()
  if (JSON.stringify(left) !== JSON.stringify(right)) throw new ProtocolError(field, "traceability list mismatch", { expected: right, actual: left })
}

function dependencyClosure(stages: AnalysisStage[]): Map<string, Set<string>> {
  const result = new Map<string, Set<string>>()
  for (const stage of stages) {
    const closure = new Set<string>()
    for (const dependency of stage.depends_on) {
      closure.add(dependency)
      for (const transitive of result.get(dependency) ?? []) closure.add(transitive)
    }
    result.set(stage.id, closure)
  }
  return result
}

export function validateAnalysis(input: unknown): Analysis {
  const source = clone(record(input, "analysis"))
  exactFields(source, [
    "schema_version", "request", "change_surfaces", "requirements", "nfrs", "decisions", "contracts",
    "acceptance", "scenarios", "nfr_applicability", "stages", "assumptions", "non_goals",
  ], "analysis")
  if (source.schema_version !== ANALYSIS_SCHEMA_VERSION) throw new ProtocolError("analysis.schema_version", `must be ${ANALYSIS_SCHEMA_VERSION}`, source.schema_version)

  const request = record(source.request, "analysis.request")
  exactFields(request, ["summary", "outcomes"], "analysis.request")
  const requestValue = { summary: text(request.summary, "analysis.request.summary"), outcomes: strings(request.outcomes, "analysis.request.outcomes", false) }
  const changeSurfaces = strings(source.change_surfaces, "analysis.change_surfaces", false)
  for (const surface of changeSurfaces) if (!CHANGE_SURFACES.has(surface)) throw new ProtocolError("analysis.change_surfaces", "unsupported change surface", surface)

  const requirements = array(source.requirements, "analysis.requirements").map((raw, index) => {
    const field = `analysis.requirements[${index}]`
    const item = record(raw, field)
    exactFields(item, ["id", "text", "stage", "acceptance", "scenarios"], field)
    return { id: identifier(item.id, "REQ", `${field}.id`), text: text(item.text, `${field}.text`), stage: stageId(item.stage, `${field}.stage`), acceptance: strings(item.acceptance, `${field}.acceptance`, false), scenarios: strings(item.scenarios, `${field}.scenarios`, false) }
  })
  sequential(requirements, "REQ", "analysis.requirements")

  const nfrs = array(source.nfrs, "analysis.nfrs").map((raw, index) => {
    const field = `analysis.nfrs[${index}]`
    const item = record(raw, field)
    exactFields(item, ["id", "text", "category", "stage", "acceptance", "scenarios"], field)
    const category = text(item.category, `${field}.category`)
    if (!NFR_CATEGORIES.has(category)) throw new ProtocolError(`${field}.category`, "unsupported NFR category", category)
    return { id: identifier(item.id, "NFR", `${field}.id`), text: text(item.text, `${field}.text`), category, stage: stageId(item.stage, `${field}.stage`), acceptance: strings(item.acceptance, `${field}.acceptance`, false), scenarios: strings(item.scenarios, `${field}.scenarios`, false) }
  })
  sequential(nfrs, "NFR", "analysis.nfrs")

  const decisions = array(source.decisions, "analysis.decisions").map((raw, index) => {
    const field = `analysis.decisions[${index}]`
    const item = record(raw, field)
    exactFields(item, ["id", "text"], field)
    return { id: identifier(item.id, "DEC", `${field}.id`), text: text(item.text, `${field}.text`) }
  })
  sequential(decisions, "DEC", "analysis.decisions")

  const contracts = array(source.contracts, "analysis.contracts").map((raw, index) => {
    const field = `analysis.contracts[${index}]`
    const item = record(raw, field)
    exactFields(item, ["id", "text", "producer", "consumers", "external", "terminal"], field)
    return {
      id: identifier(item.id, "CTR", `${field}.id`),
      text: text(item.text, `${field}.text`),
      producer: item.producer === null ? null : stageId(item.producer, `${field}.producer`),
      consumers: strings(item.consumers, `${field}.consumers`).map((value) => stageId(value, `${field}.consumers`)),
      external: boolean(item.external, `${field}.external`),
      terminal: boolean(item.terminal, `${field}.terminal`),
    }
  })
  sequential(contracts, "CTR", "analysis.contracts")

  const acceptance = array(source.acceptance, "analysis.acceptance").map((raw, index) => {
    const field = `analysis.acceptance[${index}]`
    const item = record(raw, field)
    exactFields(item, ["id", "text", "stage", "verification"], field)
    return { id: identifier(item.id, "AC", `${field}.id`), text: text(item.text, `${field}.text`), stage: stageId(item.stage, `${field}.stage`), verification: text(item.verification, `${field}.verification`) }
  })
  sequential(acceptance, "AC", "analysis.acceptance")

  const scenarios = array(source.scenarios, "analysis.scenarios").map((raw, index) => {
    const field = `analysis.scenarios[${index}]`
    const item = record(raw, field)
    exactFields(item, ["id", "text", "stage", "requirements", "expected"], field)
    return { id: identifier(item.id, "SCN", `${field}.id`), text: text(item.text, `${field}.text`), stage: stageId(item.stage, `${field}.stage`), requirements: strings(item.requirements, `${field}.requirements`, false), expected: text(item.expected, `${field}.expected`) }
  })
  sequential(scenarios, "SCN", "analysis.scenarios")

  const applicability = array(source.nfr_applicability, "analysis.nfr_applicability").map((raw, index) => {
    const field = `analysis.nfr_applicability[${index}]`
    const item = record(raw, field)
    exactFields(item, ["category", "status", "evidence", "owner", "acceptance"], field)
    const category = text(item.category, `${field}.category`)
    if (!NFR_CATEGORIES.has(category)) throw new ProtocolError(`${field}.category`, "unsupported NFR category", category)
    const status = text(item.status, `${field}.status`)
    if (!new Set(["required", "not_applicable", "deferred"]).has(status)) throw new ProtocolError(`${field}.status`, "unsupported applicability status", status)
    return { category, status: status as "required" | "not_applicable" | "deferred", evidence: text(item.evidence, `${field}.evidence`), owner: item.owner === null ? null : stageId(item.owner, `${field}.owner`), acceptance: strings(item.acceptance, `${field}.acceptance`) }
  })

  const stages = array(source.stages, "analysis.stages").map((raw, index) => {
    const field = `analysis.stages[${index}]`
    const item = record(raw, field)
    exactFields(item, ["id", "title", "slug", "depends_on", "requirements", "nfrs", "contracts_consumed", "contracts_produced", "affected_area", "risks"], field)
    const id = stageId(item.id, `${field}.id`)
    const expected = `S${String(index + 1).padStart(2, "0")}`
    if (id !== expected) throw new ProtocolError(`${field}.id`, "stages must be contiguous and ordered", { expected, actual: id })
    const slug = text(item.slug, `${field}.slug`)
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)) throw new ProtocolError(`${field}.slug`, "must be lower kebab-case", slug)
    const dependsOn = strings(item.depends_on, `${field}.depends_on`)
    for (const dependency of dependsOn) {
      const ordinal = Number(dependency.slice(1))
      if (!/^S\d{2}$/.test(dependency) || ordinal >= index + 1) throw new ProtocolError(`${field}.depends_on`, "must reference an earlier stage", dependency)
    }
    return {
      id,
      title: text(item.title, `${field}.title`),
      slug,
      depends_on: dependsOn,
      requirements: strings(item.requirements, `${field}.requirements`),
      nfrs: strings(item.nfrs, `${field}.nfrs`),
      contracts_consumed: strings(item.contracts_consumed, `${field}.contracts_consumed`),
      contracts_produced: strings(item.contracts_produced, `${field}.contracts_produced`),
      affected_area: text(item.affected_area, `${field}.affected_area`),
      risks: strings(item.risks, `${field}.risks", false),
    }
  })

  const assumptions = strings(source.assumptions, "analysis.assumptions")
  const nonGoals = strings(source.non_goals, "analysis.non_goals")
  const analysis: Analysis = {
    schema_version: ANALYSIS_SCHEMA_VERSION,
    request: requestValue,
    change_surfaces: changeSurfaces,
    requirements,
    nfrs,
    decisions,
    contracts,
    acceptance,
    scenarios,
    nfr_applicability: applicability,
    stages,
    assumptions,
    non_goals: nonGoals,
  }

  const stageById = new Map(stages.map((stage) => [stage.id, stage]))
  const requirementById = new Map(requirements.map((item) => [item.id, item]))
  const nfrById = new Map(nfrs.map((item) => [item.id, item]))
  const acceptanceById = new Map(acceptance.map((item) => [item.id, item]))
  const scenarioById = new Map(scenarios.map((item) => [item.id, item]))
  const contractById = new Map(contracts.map((item) => [item.id, item]))

  for (const item of requirements) {
    if (!stageById.has(item.stage)) throw new ProtocolError(`analysis.requirements.${item.id}.stage`, "unknown stage", item.stage)
    for (const id of item.acceptance) {
      const linked = acceptanceById.get(id)
      if (!linked || linked.stage !== item.stage) throw new ProtocolError(`analysis.requirements.${item.id}.acceptance`, "acceptance must exist in the same stage", id)
    }
    for (const id of item.scenarios) {
      const linked = scenarioById.get(id)
      if (!linked || linked.stage !== item.stage || !linked.requirements.includes(item.id)) throw new ProtocolError(`analysis.requirements.${item.id}.scenarios`, "scenario must trace back to the requirement in the same stage", id)
    }
  }
  for (const item of nfrs) {
    if (!stageById.has(item.stage)) throw new ProtocolError(`analysis.nfrs.${item.id}.stage`, "unknown stage", item.stage)
    for (const id of item.acceptance) {
      const linked = acceptanceById.get(id)
      if (!linked || linked.stage !== item.stage) throw new ProtocolError(`analysis.nfrs.${item.id}.acceptance`, "acceptance must exist in the same stage", id)
    }
    for (const id of item.scenarios) if (!scenarioById.has(id) || scenarioById.get(id)!.stage !== item.stage) throw new ProtocolError(`analysis.nfrs.${item.id}.scenarios`, "scenario must exist in the same stage", id)
  }
  for (const item of acceptance) if (!stageById.has(item.stage)) throw new ProtocolError(`analysis.acceptance.${item.id}.stage`, "unknown stage", item.stage)
  for (const item of scenarios) {
    if (!stageById.has(item.stage)) throw new ProtocolError(`analysis.scenarios.${item.id}.stage`, "unknown stage", item.stage)
    for (const requirement of item.requirements) if (!requirementById.has(requirement) || requirementById.get(requirement)!.stage !== item.stage) throw new ProtocolError(`analysis.scenarios.${item.id}.requirements`, "unknown or cross-stage requirement", requirement)
  }

  for (const stage of stages) {
    sameMembers(stage.requirements, requirements.filter((item) => item.stage === stage.id).map((item) => item.id), `analysis.stages.${stage.id}.requirements`)
    sameMembers(stage.nfrs, nfrs.filter((item) => item.stage === stage.id).map((item) => item.id), `analysis.stages.${stage.id}.nfrs`)
    for (const id of stage.requirements) if (!requirementById.has(id)) throw new ProtocolError(`analysis.stages.${stage.id}.requirements`, "unknown requirement", id)
    for (const id of stage.nfrs) if (!nfrById.has(id)) throw new ProtocolError(`analysis.stages.${stage.id}.nfrs`, "unknown NFR", id)
  }

  const closure = dependencyClosure(stages)
  for (const contract of contracts) {
    if (contract.producer !== null && !stageById.has(contract.producer)) throw new ProtocolError(`analysis.contracts.${contract.id}.producer`, "unknown stage", contract.producer)
    for (const consumer of contract.consumers) if (!stageById.has(consumer)) throw new ProtocolError(`analysis.contracts.${contract.id}.consumers`, "unknown stage", consumer)
    if (!contract.external && contract.producer === null) throw new ProtocolError(`analysis.contracts.${contract.id}.producer`, "internal contract requires a producer")
    if (contract.terminal && contract.consumers.length) throw new ProtocolError(`analysis.contracts.${contract.id}.consumers`, "terminal contract cannot have consumers")
    if (!contract.terminal && !contract.consumers.length) throw new ProtocolError(`analysis.contracts.${contract.id}.consumers`, "non-terminal contract requires consumers")
    if (contract.producer && !stageById.get(contract.producer)!.contracts_produced.includes(contract.id)) throw new ProtocolError(`analysis.contracts.${contract.id}`, "producer stage must list the contract")
    for (const consumer of contract.consumers) {
      if (!stageById.get(consumer)!.contracts_consumed.includes(contract.id)) throw new ProtocolError(`analysis.contracts.${contract.id}`, "consumer stage must list the contract", consumer)
      if (contract.producer && contract.producer !== consumer && !(closure.get(consumer)?.has(contract.producer))) throw new ProtocolError(`analysis.contracts.${contract.id}`, "consumer must depend on producer", { producer: contract.producer, consumer })
    }
  }
  for (const stage of stages) {
    for (const id of stage.contracts_produced) {
      const contract = contractById.get(id)
      if (!contract || contract.producer !== stage.id) throw new ProtocolError(`analysis.stages.${stage.id}.contracts_produced`, "contract producer mismatch", id)
    }
    for (const id of stage.contracts_consumed) {
      const contract = contractById.get(id)
      if (!contract || !contract.consumers.includes(stage.id)) throw new ProtocolError(`analysis.stages.${stage.id}.contracts_consumed`, "contract consumer mismatch", id)
    }
  }

  const requiredSurfaceCategories = new Set(changeSurfaces.flatMap((surface) => SURFACE_NFR[surface] ?? []))
  const seenApplicability = new Map<string, string>()
  for (const [index, item] of applicability.entries()) {
    const previous = seenApplicability.get(item.category)
    if (previous !== undefined) throw new ProtocolError(`analysis.nfr_applicability[${index}].category`, previous === item.status ? "duplicate applicability category" : "contradictory applicability category", { category: item.category, first_status: previous, duplicate_status: item.status })
    seenApplicability.set(item.category, item.status)
    if (item.status === "not_applicable" && (item.owner !== null || item.acceptance.length)) throw new ProtocolError(`analysis.nfr_applicability[${index}]`, "not_applicable category must not claim an owner or acceptance")
    if (item.status === "required") {
      if (!item.owner || !stageById.has(item.owner)) throw new ProtocolError(`analysis.nfr_applicability[${index}].owner`, "required category must have a real owner stage")
      const matching = nfrs.filter((nfr) => nfr.category === item.category && nfr.stage === item.owner)
      if (!matching.length) throw new ProtocolError(`analysis.nfr_applicability[${index}]`, "required category must have a real NFR with the same category and owner stage")
      const linkedAcceptance = new Set(matching.flatMap((nfr) => nfr.acceptance))
      if (!item.acceptance.length) throw new ProtocolError(`analysis.nfr_applicability[${index}].acceptance`, "required category must have linked acceptance")
      for (const acceptanceId of item.acceptance) {
        const linked = acceptanceById.get(acceptanceId)
        if (!linkedAcceptance.has(acceptanceId)) throw new ProtocolError(`analysis.nfr_applicability[${index}].acceptance`, "acceptance must be linked by an NFR of this category and owner", acceptanceId)
        if (!linked || linked.stage !== item.owner) throw new ProtocolError(`analysis.nfr_applicability[${index}].acceptance`, "acceptance must belong to owner stage", acceptanceId)
      }
    }
  }
  for (const category of requiredSurfaceCategories) if (!seenApplicability.has(category)) throw new ProtocolError("analysis.nfr_applicability", "change surface requires an explicit applicability decision", category)
  return analysis
}

function canonicalFingerprintJson(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value)
  if (Array.isArray(value)) return `[${value.map(canonicalFingerprintJson).join(",")}]`
  return `{${Object.entries(value as Record<string, unknown>).sort(([left], [right]) => left.localeCompare(right)).map(([key, item]) => `${JSON.stringify(key)}:${canonicalFingerprintJson(item)}`).join(",")}}`
}

export function semanticStageFingerprint(analysisInput: unknown, stageIdValue: string): string {
  const analysis = validateAnalysis(analysisInput)
  const stage = analysis.stages.find((item) => item.id === stageIdValue)
  if (!stage) throw new ProtocolError("stage", "unknown stage for semantic fingerprint", stageIdValue)
  const requirements = analysis.requirements.filter((item) => item.stage === stage.id)
  const nfrs = analysis.nfrs.filter((item) => item.stage === stage.id)
  const contracts = analysis.contracts.filter((item) => item.producer === stage.id || item.consumers.includes(stage.id) || stage.contracts_consumed.includes(item.id) || stage.contracts_produced.includes(item.id))
  const acceptanceIds = new Set([...requirements.flatMap((item) => item.acceptance), ...nfrs.flatMap((item) => item.acceptance)])
  const scenarioIds = new Set([...requirements.flatMap((item) => item.scenarios), ...nfrs.flatMap((item) => item.scenarios)])
  const semantic = {
    stage: { id: stage.id, title: stage.title, slug: stage.slug, depends_on: stage.depends_on, affected_area: stage.affected_area, risks: stage.risks },
    requirements,
    nfrs,
    contracts,
    acceptance: analysis.acceptance.filter((item) => item.stage === stage.id || acceptanceIds.has(item.id)),
    scenarios: analysis.scenarios.filter((item) => item.stage === stage.id || scenarioIds.has(item.id)),
    applicability: analysis.nfr_applicability.filter((item) => item.owner === stage.id || nfrs.some((nfr) => nfr.category === item.category)),
    decisions: analysis.decisions,
  }
  return createHash("sha256").update(canonicalFingerprintJson(semantic)).digest("hex")
}
'''


REVIEW_TS = r'''
import type { JsonRecord, State } from "./schema.js"
import { REPEAT_LIMIT } from "./schema.js"
import { sha } from "./state.js"

function semanticEvidence(payload: JsonRecord): JsonRecord {
  return {
    findings: payload.findings ?? [],
    required_changes: payload.required_changes ?? [],
    reason: payload.reason ?? "unspecified",
    stage: payload.stage ?? null,
  }
}

export function correctionDigests(payload: JsonRecord): { fingerprint: string; evidence_digest: string } {
  return { fingerprint: sha(semanticEvidence(payload)), evidence_digest: sha(payload.evidence ?? payload) }
}

export function recordCorrection(state: State, key: string, revision: number, payload: JsonRecord): boolean {
  const current = correctionDigests(payload)
  const previous = state.convergence[key]
  const repeats = previous && previous.fingerprint === current.fingerprint && previous.evidence_digest === current.evidence_digest ? previous.repeats + 1 : 1
  state.convergence[key] = { ...current, repeats, last_revision: revision }
  return repeats >= REPEAT_LIMIT
}

export function clearCorrection(state: State, key: string): void {
  delete state.convergence[key]
}

export function dependentStages(state: State, seeds: string[]): string[] {
  const affected = new Set(seeds)
  let changed = true
  while (changed) {
    changed = false
    for (const stage of state.stages) {
      if (!affected.has(stage.id) && stage.depends_on.some((dependency) => affected.has(dependency))) {
        affected.add(stage.id)
        changed = true
      }
    }
  }
  return state.stages.filter((stage) => affected.has(stage.id)).map((stage) => stage.id)
}
'''


EVENTS_TS = r'''
import type { Analysis, EventInput, JsonRecord, State, WorkflowStatus } from "./schema.js"
import { EVENT_BY_ACTION, ProtocolError, clone, record, strings, text } from "./schema.js"
import { clearCorrection, dependentStages, recordCorrection } from "./review.js"
import { normalizeProgress, sha, stagesFromAnalysis, validateState } from "./state.js"

function uppercase(value: unknown, field: string): string {
  return text(value, field).toUpperCase()
}

function revisionMatches(payload: JsonRecord, expected: number | null): void {
  if (payload.revision !== undefined && expected !== null && payload.revision !== expected) throw new ProtocolError("event.payload.revision", "does not match reserved revision", { expected, actual: payload.revision })
}

function resetStageProgress(state: State): void {
  for (const stage of state.stages) {
    stage.status = "proposed"
    stage.revision = 0
    stage.human_status = "pending"
    stage.human_revision = 0
  }
  state.current_stage = null
}

function block(state: State, reason: string, detail: string, resumeStatus: WorkflowStatus, transition: string, retryable = true): void {
  state.status = "blocked"
  state.current_stage = null
  state.blocker = { reason, detail, resume_status: resumeStatus, retryable, source_transition: transition }
}

export function requestReopen(stateInput: State, seedsInput: string[], reason: string, requestedBy: "reviewer" | "user" = "reviewer"): State {
  const state = clone(stateInput)
  const seeds = [...new Set(seedsInput)]
  if (!seeds.length) throw new ProtocolError("reopen.seeds", "must not be empty")
  for (const seed of seeds) {
    const stage = state.stages.find((item) => item.id === seed)
    if (!stage || stage.status !== "pass") throw new ProtocolError("reopen.seeds", "only passed stages can be reopened", seed)
  }
  const affected = dependentStages(state, seeds)
  state.reopen = { requested_by: requestedBy, reason: text(reason, "reopen.reason"), seeds, affected, resume_status: state.status, resume_stage: state.current_stage }
  state.status = "waiting_reopen_approval"
  state.current_stage = null
  state.pending = null
  return validateState(state)
}

function applyReopenDecision(state: State, payload: JsonRecord): void {
  if (!state.reopen) throw new ProtocolError("state.reopen", "reopen decision requires a pending reopen request")
  const decision = uppercase(payload.decision, "event.payload.decision")
  const reopen = clone(state.reopen)
  state.reopen = null
  if (decision === "REJECT") {
    state.status = reopen.resume_status
    state.current_stage = reopen.resume_stage
    return
  }
  if (decision !== "APPROVE") throw new ProtocolError("event.payload.decision", "must be APPROVE or REJECT", decision)
  for (const stage of state.stages) {
    if (!reopen.affected.includes(stage.id)) continue
    stage.status = "proposed"
    stage.human_status = "pending"
    stage.human_revision = 0
  }
  state.status = "planning"
  state.current_stage = state.stages.find((stage) => reopen.affected.includes(stage.id))?.id ?? null
}

export async function applyEvent(_directory: string, input: State, eventInput: EventInput, analysis?: Analysis, expectedStateRevision?: number): Promise<{ state: State; result: JsonRecord }> {
  const event = clone(eventInput)
  const state = validateState(input, analysis && input.stages.length && !input.legacy_migrated ? analysis : undefined)
  if (expectedStateRevision !== undefined && state.state_revision !== expectedStateRevision) throw new ProtocolError("expected_state_revision", "state revision conflict", { expected: expectedStateRevision, actual: state.state_revision })
  const eventDigest = sha(event)
  const applied = state.applied[event.transition_id]
  if (applied) {
    if (applied.event_digest !== eventDigest) throw new ProtocolError("event.transition_id", "journal conflict: transition was already applied with different content", event.transition_id)
    return { state, result: clone(applied.result) }
  }
  if (!state.pending) throw new ProtocolError("state.pending", "event cannot be applied without a pending transition")
  if (event.transition_id !== state.pending.transition_id) throw new ProtocolError("event.transition_id", "does not match pending transition", { expected: state.pending.transition_id, actual: event.transition_id })
  const expectedType = EVENT_BY_ACTION[state.pending.action]
  if (event.type !== expectedType && event.type !== "task_failure") throw new ProtocolError("event.type", "does not match pending action", { action: state.pending.action, expected: expectedType, actual: event.type })
  const next = clone(state)
  const pending = next.pending!
  const payload = record(event.payload, "event.payload")
  const resumeStatus = next.status
  revisionMatches(payload, pending.revision)
  next.pending = null

  if (event.type === "task_failure") {
    block(next, text(payload.reason ?? "task_failure", "event.payload.reason"), text(payload.detail ?? "Agent task failed before a valid artifact was produced.", "event.payload.detail"), resumeStatus, event.transition_id, payload.retryable !== false)
  } else if (event.type === "discovery_result") {
    const status = uppercase(payload.status, "event.payload.status")
    if (status === "READY_FOR_REVIEW") {
      if (!analysis) throw new ProtocolError("analysis.json", "discovery result requires valid analysis")
      next.stages = stagesFromAnalysis(analysis)
      next.analysis_status = "review"
      next.status = "discovery_review"
      next.current_stage = null
    } else if (status === "NEEDS_INPUT") {
      next.analysis_status = "draft"
      next.question_revision += 1
      next.status = "waiting_answers"
      resetStageProgress(next)
      next.stages = []
    } else if (status === "BLOCKED") {
      block(next, text(payload.reason ?? "discovery_blocked", "event.payload.reason"), text(payload.detail ?? "Discovery reported a blocker.", "event.payload.detail"), "discovery", event.transition_id)
    } else throw new ProtocolError("event.payload.status", "unsupported discovery result", status)
  } else if (event.type === "discovery_review_result") {
    const status = uppercase(payload.status, "event.payload.status")
    if (status === "PASS") {
      next.analysis_status = "reviewed"
      next.status = "waiting_map_approval"
      clearCorrection(next, "DISCOVERY")
    } else if (status === "REVISE") {
      next.analysis_status = "draft"
      next.status = "discovery"
      resetStageProgress(next)
      if (recordCorrection(next, "DISCOVERY", pending.revision ?? next.analysis_revision, payload)) block(next, "non_converging_discovery", "The same discovery findings and evidence repeated without semantic progress.", "discovery", event.transition_id)
    } else if (status === "BLOCKED") block(next, text(payload.reason ?? "discovery_review_blocked", "event.payload.reason"), text(payload.detail ?? "Discovery reviewer reported a blocker.", "event.payload.detail"), "discovery_review", event.transition_id)
    else throw new ProtocolError("event.payload.status", "unsupported discovery review result", status)
  } else if (event.type === "answers") {
    next.feedback_revision += 1
    next.status = "discovery"
    next.analysis_status = "draft"
  } else if (event.type === "map_decision") {
    const decision = uppercase(payload.decision, "event.payload.decision")
    if (decision === "APPROVE") {
      if (!next.stages.length) throw new ProtocolError("state.stages", "cannot approve an empty stage map")
      next.analysis_status = "approved"
      next.status = "planning"
      next.current_stage = next.stages[0].id
    } else if (decision === "REVISE") {
      next.analysis_status = "draft"
      next.status = "discovery"
      resetStageProgress(next)
    } else throw new ProtocolError("event.payload.decision", "must be APPROVE or REVISE", decision)
  } else if (event.type === "stage_plan_result") {
    const status = uppercase(payload.status, "event.payload.status")
    const stage = next.stages.find((item) => item.id === pending.stage)!
    if (status === "REVIEW") stage.status = "review"
    else if (status === "BLOCKED") block(next, text(payload.reason ?? "stage_plan_blocked", "event.payload.reason"), text(payload.detail ?? "Stage planner reported a blocker.", "event.payload.detail"), "planning", event.transition_id)
    else throw new ProtocolError("event.payload.status", "stage planner must return REVIEW or BLOCKED", status)
  } else if (event.type === "stage_review_result") {
    const reopen = Array.isArray(payload.reopen_stages) ? strings(payload.reopen_stages, "event.payload.reopen_stages", false) : []
    if (reopen.length) {
      const requested = requestReopen(next, reopen, text(payload.reason ?? "Reviewer found a stale passed-stage contract.", "event.payload.reason"), "reviewer")
      Object.assign(next, requested)
    } else {
      const status = uppercase(payload.status, "event.payload.status")
      const stage = next.stages.find((item) => item.id === pending.stage)!
      if (status === "PASS") {
        stage.status = "pass"
        clearCorrection(next, `TECHNICAL:${stage.id}`)
        next.current_stage = next.stages.find((item) => item.status !== "pass")?.id ?? null
        normalizeProgress(next)
      } else if (status === "REVISE") {
        stage.status = "planning"
        stage.revision += 1
        stage.human_status = "pending"
        stage.human_revision = 0
        next.current_stage = stage.id
        if (recordCorrection(next, `TECHNICAL:${stage.id}`, stage.revision, payload)) block(next, "non_converging_technical_review", `The same technical findings repeated for ${stage.id} without semantic progress.`, "planning", event.transition_id)
      } else if (status === "BLOCKED") block(next, text(payload.reason ?? "stage_review_blocked", "event.payload.reason"), text(payload.detail ?? "Technical reviewer reported a blocker.", "event.payload.detail"), "planning", event.transition_id)
      else throw new ProtocolError("event.payload.status", "unsupported stage review result", status)
    }
  } else if (event.type === "human_plan_result") {
    const status = uppercase(payload.status, "event.payload.status")
    const stage = next.stages.find((item) => item.id === pending.stage)!
    if (status === "REVIEW") stage.human_status = "review"
    else if (status === "BLOCKED") block(next, text(payload.reason ?? "human_plan_blocked", "event.payload.reason"), text(payload.detail ?? "Human-review planner reported a blocker.", "event.payload.detail"), "human_reviewing", event.transition_id)
    else throw new ProtocolError("event.payload.status", "human-review planner must return REVIEW or BLOCKED", status)
  } else if (event.type === "human_review_result") {
    const reopen = Array.isArray(payload.reopen_stages) ? strings(payload.reopen_stages, "event.payload.reopen_stages", false) : []
    if (reopen.length) {
      const requested = requestReopen(next, reopen, text(payload.reason ?? "Human reviewer found a stale passed-stage contract.", "event.payload.reason"), "reviewer")
      Object.assign(next, requested)
    } else {
      const status = uppercase(payload.status, "event.payload.status")
      const stage = next.stages.find((item) => item.id === pending.stage)!
      if (status === "PASS") {
        stage.human_status = "pass"
        clearCorrection(next, `HUMAN:${stage.id}`)
        next.current_stage = next.stages.find((item) => item.human_status !== "pass")?.id ?? null
        normalizeProgress(next)
      } else if (status === "REVISE") {
        stage.human_status = "planning"
        stage.human_revision += 1
        next.current_stage = stage.id
        if (recordCorrection(next, `HUMAN:${stage.id}`, stage.human_revision, payload)) block(next, "non_converging_human_review", `The same human-review findings repeated for ${stage.id} without semantic progress.`, "human_reviewing", event.transition_id)
      } else if (status === "BLOCKED") block(next, text(payload.reason ?? "human_review_blocked", "event.payload.reason"), text(payload.detail ?? "Human reviewer reported a blocker.", "event.payload.detail"), "human_reviewing", event.transition_id)
      else throw new ProtocolError("event.payload.status", "unsupported human review result", status)
    }
  } else if (event.type === "plan_decision") {
    const decision = uppercase(payload.decision, "event.payload.decision")
    if (decision === "APPROVE") next.status = "ready"
    else if (decision === "REVISE") {
      const stageId = typeof payload.stage === "string" ? payload.stage : next.stages[0]?.id
      const stage = next.stages.find((item) => item.id === stageId)
      if (!stage) throw new ProtocolError("event.payload.stage", "unknown stage", stageId)
      stage.human_status = "planning"
      stage.human_revision += 1
      next.status = "human_reviewing"
      next.current_stage = stage.id
    } else throw new ProtocolError("event.payload.decision", "must be APPROVE or REVISE", decision)
  } else if (event.type === "reopen_decision") applyReopenDecision(next, payload)
  else if (event.type === "blocker_resolution") {
    if (!next.blocker) throw new ProtocolError("state.blocker", "resolution requires blocker")
    const decision = uppercase(payload.decision ?? payload.resolution, "event.payload.decision")
    const resume = next.blocker.resume_status
    next.blocker = null
    if (decision === "RETRY" || decision === "RESUME") next.status = resume
    else if (decision === "REDISCOVER") {
      next.status = "discovery"
      next.analysis_status = "draft"
      resetStageProgress(next)
    } else throw new ProtocolError("event.payload.decision", "must be RETRY, RESUME, or REDISCOVER", decision)
  }

  next.state_revision += 1
  const result: JsonRecord = { transition_id: event.transition_id, event_type: event.type, status: next.status, state_revision: next.state_revision }
  next.applied[event.transition_id] = { event_digest: eventDigest, result: clone(result) }
  return { state: validateState(next, analysis && next.stages.length && !next.legacy_migrated ? analysis : undefined), result }
}
'''


STORE_TS = r'''
import { constants as fsConstants } from "node:fs"
import { access, lstat, mkdir, open, readFile, realpath, rename, rm, stat } from "node:fs/promises"
import path from "node:path"
import { setTimeout as delay } from "node:timers/promises"
import type { Analysis, EventInput, JsonRecord, State } from "./schema.js"
import { ProtocolError, clone, integer, parseJsonStrict, record } from "./schema.js"
import { semanticStageFingerprint, validateAnalysis } from "./analysis.js"
import { assertArtifact, assertCompleteArtifactGraph, assertInputSnapshotsCurrent, assertPendingOutputContracts, capturePendingSnapshots } from "./artifacts.js"
import { applyEvent } from "./events.js"
import { parseLegacyPlan, parseLegacySnapshot, renderPlan } from "./render.js"
import type { LegacySnapshot } from "./render.js"
import { reserveNext } from "./routing.js"
import { migrateState, newState, normalizeProgress, stableJson, validateState } from "./state.js"

async function exists(candidate: string): Promise<boolean> {
  try { await access(candidate, fsConstants.F_OK); return true } catch { return false }
}

function within(base: string, candidate: string): boolean {
  const relative = path.relative(path.resolve(base), path.resolve(candidate))
  return relative === "" || (relative !== ".." && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative))
}

async function atomicWrite(candidate: string, content: string): Promise<void> {
  await mkdir(path.dirname(candidate), { recursive: true })
  if (await exists(candidate) && (await lstat(candidate)).isSymbolicLink()) throw new ProtocolError(candidate, "refusing to replace a symlink")
  const temporary = path.join(path.dirname(candidate), `.${path.basename(candidate)}.${process.pid}.${Date.now()}.tmp`)
  const handle = await open(temporary, "wx", 0o600)
  try { await handle.writeFile(content, "utf8"); await handle.sync() } finally { await handle.close() }
  try { await rename(temporary, candidate) }
  catch (error) {
    const code = (error as { code?: string }).code
    if (!new Set(["EEXIST", "EPERM", "EACCES"]).has(code ?? "")) throw error
    await rm(candidate, { force: true })
    await rename(temporary, candidate)
  } finally { await rm(temporary, { force: true }) }
}

async function parseJsonFile(candidate: string): Promise<unknown> {
  let content: string
  try { content = await readFile(candidate, "utf8") } catch (error) { throw new ProtocolError(candidate, "cannot read JSON", String(error)) }
  return parseJsonStrict(content)
}

async function appendJournal(candidate: string, entry: JsonRecord): Promise<void> {
  const entries: JsonRecord[] = []
  if (await exists(candidate)) {
    for (const [index, line] of (await readFile(candidate, "utf8")).split(/\r?\n/).filter(Boolean).entries()) entries.push(record(parseJsonStrict(line), `journal[${index}]`))
  }
  const existing = entries.find((item) => item.entry_id === entry.entry_id)
  if (existing) {
    if (stableJson(existing) !== stableJson(entry)) throw new ProtocolError("journal.entry_id", "journal conflict: duplicate entry_id has different content", entry.entry_id)
    return
  }
  entries.push(entry)
  await atomicWrite(candidate, entries.map((item) => JSON.stringify(item)).join("\n") + "\n")
}

export class WorkflowStore {
  readonly base: string
  readonly root: string
  readonly internal: string
  readonly statePath: string
  readonly planPath: string
  readonly analysisPath: string
  readonly journalPath: string
  readonly transactionPath: string
  readonly lockPath: string
  readonly stateV1BackupPath: string
  readonly legacyBackupPath: string
  readonly legacySnapshotPath: string
  readonly request: string

  constructor(directory: string, request: string) {
    newState(request)
    this.base = path.resolve(directory)
    this.root = path.resolve(this.base, "1_orchestrator", request)
    if (path.dirname(this.root) !== path.resolve(this.base, "1_orchestrator")) throw new ProtocolError("workflow_root", "request path escapes workflow base", this.root)
    this.request = request
    this.internal = path.join(this.root, ".orchestrator")
    this.statePath = path.join(this.internal, "state.json")
    this.planPath = path.join(this.root, "plan.md")
    this.analysisPath = path.join(this.root, "analysis.json")
    this.journalPath = path.join(this.internal, "journal.jsonl")
    this.transactionPath = path.join(this.internal, "transaction.json")
    this.lockPath = path.join(this.internal, "lock")
    this.stateV1BackupPath = path.join(this.internal, "state-v1.json")
    this.legacyBackupPath = path.join(this.internal, "legacy-plan.md")
    this.legacySnapshotPath = path.join(this.internal, "legacy-state.json")
  }

  private async ensureRoot(): Promise<void> {
    const parent = path.resolve(this.base, "1_orchestrator")
    await mkdir(parent, { recursive: true })
    await mkdir(this.internal, { recursive: true })
    const resolvedParent = await realpath(parent)
    const resolvedRoot = await realpath(this.root)
    if (!within(resolvedParent, resolvedRoot) || resolvedRoot === resolvedParent) throw new ProtocolError("workflow_root", "resolved request root escapes 1_orchestrator", resolvedRoot)
  }

  private async withLock<T>(operation: () => Promise<T>, timeoutMs = 5000, staleMs = 300000): Promise<T> {
    await this.ensureRoot()
    const deadline = Date.now() + timeoutMs
    while (true) {
      try {
        const handle = await open(this.lockPath, "wx", 0o600)
        await handle.writeFile(JSON.stringify({ pid: process.pid, created_at: new Date().toISOString() }))
        await handle.close()
        break
      } catch (error) {
        if ((error as { code?: string }).code !== "EEXIST") throw error
        const info = await lstat(this.lockPath)
        if (info.isSymbolicLink()) throw new ProtocolError("workflow_lock", "lock path is a symlink")
        if (Date.now() - info.mtimeMs > staleMs) { await rm(this.lockPath, { force: true }); continue }
        if (Date.now() >= deadline) throw new ProtocolError("workflow_lock", "request is already being advanced")
        await delay(25)
      }
    }
    try { return await operation() } finally { await rm(this.lockPath, { force: true }) }
  }

  private async recover(): Promise<boolean> {
    if (!(await exists(this.transactionPath))) return false
    const transaction = record(await parseJsonFile(this.transactionPath), "transaction")
    if (transaction.schema_version !== 2) throw new ProtocolError("transaction.schema_version", "unsupported transaction", transaction.schema_version)
    const baseRevision = integer(transaction.base_state_revision, "transaction.base_state_revision")
    const target = validateState(transaction.state)
    if (typeof transaction.plan !== "string" || !transaction.plan.trim()) throw new ProtocolError("transaction.plan", "must be a non-empty string")
    const current = await exists(this.statePath) ? validateState(await parseJsonFile(this.statePath)) : null
    if (current) {
      if (current.state_revision === target.state_revision) {
        if (stableJson(current) !== stableJson(target)) throw new ProtocolError("transaction.state", "journal recovery conflict at target revision")
      } else if (current.state_revision === baseRevision) await atomicWrite(this.statePath, `${JSON.stringify(target, null, 2)}\n`)
      else throw new ProtocolError("transaction.base_state_revision", "journal recovery conflict", { base: baseRevision, current: current.state_revision, target: target.state_revision })
    } else {
      if (baseRevision !== 0) throw new ProtocolError("transaction.base_state_revision", "missing base state for recovery", baseRevision)
      await atomicWrite(this.statePath, `${JSON.stringify(target, null, 2)}\n`)
    }
    await atomicWrite(this.planPath, transaction.plan)
    await appendJournal(this.journalPath, record(transaction.journal, "transaction.journal"))
    await rm(this.transactionPath, { force: true })
    return true
  }

  private async loadState(): Promise<State> {
    await this.ensureRoot()
    await this.recover()
    if (await exists(this.statePath)) {
      const raw = await parseJsonFile(this.statePath)
      const migration = migrateState(raw)
      const state = validateState(migration.state)
      if (migration.migrated) {
        if (!(await exists(this.stateV1BackupPath))) await atomicWrite(this.stateV1BackupPath, `${JSON.stringify(raw, null, 2)}\n`)
        await atomicWrite(this.statePath, `${JSON.stringify(state, null, 2)}\n`)
        await appendJournal(this.journalPath, { entry_id: `state-schema:${migration.from_version}-${migration.to_version}:${state.state_revision}`, timestamp: new Date().toISOString(), action: "state_schema_migration", state_revision: state.state_revision, transition_id: migration.invalidated_transition, detail: clone(migration as unknown as JsonRecord) })
      }
      return state
    }
    if (await exists(this.planPath)) {
      const content = await readFile(this.planPath, "utf8")
      if (!(await exists(this.legacyBackupPath))) await atomicWrite(this.legacyBackupPath, content)
      const snapshot = parseLegacySnapshot(content, this.request)
      await atomicWrite(this.legacySnapshotPath, `${JSON.stringify(snapshot, null, 2)}\n`)
      return parseLegacyPlan(content, this.request)
    }
    return newState(this.request)
  }

  private async loadLegacySnapshot(): Promise<LegacySnapshot | undefined> {
    return await exists(this.legacySnapshotPath) ? parseJsonFile(this.legacySnapshotPath) as LegacySnapshot : undefined
  }

  private async restoreLegacyPasses(state: State, analysis: Analysis): Promise<void> {
    const snapshot = await this.loadLegacySnapshot()
    if (!snapshot) { state.legacy_migrated = false; return }
    for (const stage of state.stages) {
      const legacy = snapshot.stages.find((item) => item.id === stage.id)
      if (!legacy || legacy.status !== "pass" || !legacy.semantic_fingerprint || legacy.semantic_fingerprint !== semanticStageFingerprint(analysis, stage.id)) continue
      const revision = Math.max(1, legacy.revision)
      try {
        await assertArtifact(this.root, stage.details, { artifact: "technical-stage", stage: stage.id, revision, source_revision: state.analysis_revision, status: "REVIEW" })
        await assertArtifact(this.root, stage.review, { artifact: "technical-review", stage: stage.id, revision, source_revision: revision, status: "PASS" })
      } catch { continue }
      stage.status = "pass"
      stage.revision = revision
      if (legacy.human_status === "pass") {
        const humanRevision = Math.max(1, legacy.human_revision)
        try {
          await assertArtifact(this.root, stage.human_review, { artifact: "human-review", stage: stage.id, revision: humanRevision, source_revision: revision, status: "REVIEW" })
          await assertArtifact(this.root, stage.human_review_review, { artifact: "human-review-review", stage: stage.id, revision: humanRevision, source_revision: revision, status: "PASS" })
          stage.human_status = "pass"
          stage.human_revision = humanRevision
        } catch { stage.human_status = "pending"; stage.human_revision = 0 }
      }
    }
    state.legacy_migrated = false
    normalizeProgress(state)
    if (state.status === "planning") state.current_stage = state.stages.find((stage) => stage.status !== "pass")?.id ?? state.current_stage
    if (state.status === "human_reviewing") state.current_stage = state.stages.find((stage) => stage.human_status !== "pass")?.id ?? state.current_stage
  }

  private async loadAnalysis(): Promise<Analysis | undefined> {
    return await exists(this.analysisPath) ? validateAnalysis(await parseJsonFile(this.analysisPath)) : undefined
  }

  private journal(action: string, state: State, detail: JsonRecord): JsonRecord {
    const transition = typeof detail.transition_id === "string" ? detail.transition_id : "state"
    return { entry_id: `${transition}:${action}:${state.state_revision}`, timestamp: new Date().toISOString(), action, state_revision: state.state_revision, transition_id: detail.transition_id ?? null, detail: clone(detail) }
  }

  private async commit(baseStateRevision: number, state: State, analysis: Analysis | undefined, journal: JsonRecord): Promise<void> {
    const validated = validateState(state, analysis && state.stages.length && !state.legacy_migrated ? analysis : undefined)
    const plan = renderPlan(validated, analysis)
    const transaction = { schema_version: 2, base_state_revision: baseStateRevision, state: validated, plan, journal }
    await atomicWrite(this.transactionPath, `${JSON.stringify(transaction, null, 2)}\n`)
    await atomicWrite(this.statePath, `${JSON.stringify(validated, null, 2)}\n`)
    await atomicWrite(this.planPath, plan)
    await appendJournal(this.journalPath, journal)
    await rm(this.transactionPath, { force: true })
  }

  async reserve(expectedStateRevision?: number): Promise<{ state: State; action: JsonRecord }> {
    return this.withLock(async () => {
      const state = await this.loadState()
      const analysis = await this.loadAnalysis()
      if (state.status === "waiting_plan_approval" || state.status === "ready") await assertCompleteArtifactGraph(this.root, state, analysis)
      const result = reserveNext(state, analysis, expectedStateRevision)
      if (result.state.pending && !result.state.pending.snapshots_captured) {
        const projectedPlan = renderPlan(result.state, analysis)
        await capturePendingSnapshots(this.root, result.state.pending, { "plan.md": projectedPlan })
        result.action = clone(result.state.pending) as unknown as JsonRecord
      }
      if (stableJson(result.state) !== stableJson(state)) await this.commit(state.state_revision, result.state, analysis, this.journal("reserve", result.state, result.action))
      return result
    })
  }

  async apply(event: EventInput, expectedStateRevision?: number): Promise<{ state: State; result: JsonRecord }> {
    return this.withLock(async () => {
      const state = await this.loadState()
      const analysis = await this.loadAnalysis()
      if (!state.pending) {
        if (state.applied[event.transition_id]) return applyEvent(this.base, state, event, analysis, expectedStateRevision)
        throw new ProtocolError("state.pending", "event cannot be applied without a pending transition")
      }
      await assertInputSnapshotsCurrent(this.root, state.pending)
      await assertPendingOutputContracts(this.root, state, event, analysis)
      const payload = record(event.payload, "event.payload")
      if (state.pending.action === "APPROVE_PLAN" && String(payload.decision).toUpperCase() === "APPROVE") await assertCompleteArtifactGraph(this.root, state, analysis)
      const result = await applyEvent(this.base, state, event, analysis, expectedStateRevision)
      if (event.type === "map_decision" && String(payload.decision).toUpperCase() === "APPROVE" && result.state.legacy_migrated && analysis) await this.restoreLegacyPasses(result.state, analysis)
      if (result.state.status === "ready") await assertCompleteArtifactGraph(this.root, result.state, analysis)
      if (stableJson(result.state) !== stableJson(state)) await this.commit(state.state_revision, result.state, analysis, this.journal("apply", result.state, { transition_id: event.transition_id, event_type: event.type, result: result.result }))
      return result
    })
  }

  async validate(): Promise<JsonRecord> {
    return this.withLock(async () => {
      const state = await this.loadState()
      const analysis = await this.loadAnalysis()
      validateState(state, analysis && state.stages.length && !state.legacy_migrated ? analysis : undefined)
      if (state.legacy_migrated && !(await exists(this.statePath))) await this.commit(0, state, analysis, this.journal("migrate", state, { transition_id: null, source: "legacy-plan.md" }))
      const issues: string[] = []
      const expected = renderPlan(state, analysis)
      if (await exists(this.planPath) && await readFile(this.planPath, "utf8") !== expected) issues.push("plan.md differs from deterministic rendering")
      if (["review", "reviewed", "approved"].includes(state.analysis_status) && !analysis) issues.push("analysis.json is required by current state")
      if (state.status === "waiting_plan_approval" || state.status === "ready") {
        try { await assertCompleteArtifactGraph(this.root, state, analysis) } catch (error) { issues.push(error instanceof Error ? error.message : String(error)) }
      }
      return { valid: !issues.length, state_revision: state.state_revision, status: state.status, pending: state.pending, issues }
    })
  }
}
'''


TOOLS_TS = r'''
import { tool } from "@opencode-ai/plugin"
import { WorkflowStore, parseJsonStrict, record } from "../runtime/orchestrator.js"

const request = tool.schema.string().min(1).describe("Lower kebab-case workflow request id")
const expected = tool.schema.number().int().nonnegative().optional().describe("Optimistic state revision")

export const orchestrator_next = tool({
  description: "Reserve and return the next legal OpenCode orchestrator action.",
  args: { request, expected_state_revision: expected },
  async execute(args, context) {
    const store = new WorkflowStore(context.directory, args.request)
    return JSON.stringify(await store.reserve(args.expected_state_revision), null, 2)
  },
})

export const orchestrator_update = tool({
  description: "Apply the exact event for a previously reserved orchestrator transition.",
  args: {
    request,
    transition_id: tool.schema.string().min(1),
    event_type: tool.schema.string().min(1),
    payload_json: tool.schema.string().min(2).describe("Strict JSON object payload"),
    expected_state_revision: expected,
  },
  async execute(args, context) {
    const payload = record(parseJsonStrict(args.payload_json), "payload_json")
    const store = new WorkflowStore(context.directory, args.request)
    return JSON.stringify(await store.apply({ transition_id: args.transition_id, type: args.event_type, payload }, args.expected_state_revision), null, 2)
  },
})

export const orchestrator_status = tool({
  description: "Validate and report persisted orchestrator state and executable gates.",
  args: { request },
  async execute(args, context) {
    const store = new WorkflowStore(context.directory, args.request)
    return JSON.stringify(await store.validate(), null, 2)
  },
})
'''


HELPERS = r'''
import { mkdir, writeFile } from "node:fs/promises"
import path from "node:path"

export function analysisFixture() {
  return {
    schema_version: 1,
    request: { summary: "Ship a deterministic two-stage controller change", outcomes: ["Executable stage graph", "Verified release"] },
    change_surfaces: ["library"],
    requirements: [
      { id: "REQ-001", text: "Implement the controller contract", stage: "S01", acceptance: ["AC-001"], scenarios: ["SCN-001"] },
      { id: "REQ-002", text: "Integrate and release the contract", stage: "S02", acceptance: ["AC-003"], scenarios: ["SCN-002"] },
    ],
    nfrs: [
      { id: "NFR-001", text: "Preserve compatibility through explicit versioned contracts", category: "compatibility-migration", stage: "S01", acceptance: ["AC-002"], scenarios: ["SCN-001"] },
    ],
    decisions: [{ id: "DEC-001", text: "Use one TypeScript controller and immutable artifacts" }],
    contracts: [
      { id: "CTR-001", text: "S01 produces the controller contract consumed by S02", producer: "S01", consumers: ["S02"], external: false, terminal: false },
      { id: "CTR-002", text: "S02 produces the terminal release package", producer: "S02", consumers: [], external: false, terminal: true },
    ],
    acceptance: [
      { id: "AC-001", text: "Controller contract tests pass", stage: "S01", verification: "node test" },
      { id: "AC-002", text: "Compatibility migration test passes", stage: "S01", verification: "migration test" },
      { id: "AC-003", text: "Release journey reaches COMPLETE", stage: "S02", verification: "journey test" },
    ],
    scenarios: [
      { id: "SCN-001", text: "Validate and migrate controller state", stage: "S01", requirements: ["REQ-001"], expected: "State is valid and resumable" },
      { id: "SCN-002", text: "Execute a complete store journey", stage: "S02", requirements: ["REQ-002"], expected: "All artifacts pass and COMPLETE is returned" },
    ],
    nfr_applicability: [
      { category: "compatibility-migration", status: "required", evidence: "The state and runtime are versioned", owner: "S01", acceptance: ["AC-002"] },
    ],
    stages: [
      { id: "S01", title: "Controller contracts", slug: "controller-contracts", depends_on: [], requirements: ["REQ-001"], nfrs: ["NFR-001"], contracts_consumed: [], contracts_produced: ["CTR-001"], affected_area: "src and runtime", risks: ["stale artifact acceptance"] },
      { id: "S02", title: "Release integration", slug: "release-integration", depends_on: ["S01"], requirements: ["REQ-002"], nfrs: [], contracts_consumed: ["CTR-001"], contracts_produced: ["CTR-002"], affected_area: "tests installer CI", risks: ["cross-platform drift"] },
    ],
    assumptions: ["OpenCode invokes native tools from one repository root"],
    non_goals: ["Generic workflow framework"],
  }
}

export function event(action, type, payload) {
  return { transition_id: action.transition_id, type, payload }
}

export async function writeArtifact(root, relative, metadata, body = "# Verified artifact\n") {
  const destination = path.join(root, ...relative.split("/"))
  await mkdir(path.dirname(destination), { recursive: true })
  await writeFile(destination, [
    "---",
    "schema_version: 1",
    `artifact: ${metadata.artifact}`,
    `stage: ${metadata.stage ?? "none"}`,
    `revision: ${metadata.revision}`,
    `source_revision: ${metadata.source_revision}`,
    `status: ${metadata.status}`,
    "---",
    body.trimEnd(),
    "",
  ].join("\n"), "utf8")
}
'''


JOURNEY = r'''
import assert from "node:assert/strict"
import { mkdir, mkdtemp, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"

import { WorkflowStore } from "../runtime/orchestrator.js"
import { analysisFixture, event, writeArtifact } from "./helpers.mjs"

test("complete store journey creates and validates real artifacts", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-real-journey-"))
  const root = path.join(base, "1_orchestrator", "journey")
  await mkdir(root, { recursive: true })
  const store = new WorkflowStore(base, "journey")
  const analysis = analysisFixture()

  let step = await store.reserve()
  await writeFile(path.join(root, "analysis.json"), JSON.stringify(analysis, null, 2) + "\n")
  await writeArtifact(root, "discovery.md", { artifact: "discovery", revision: 1, source_revision: 0, status: "READY_FOR_REVIEW" })
  let applied = await store.apply(event(step.action, "discovery_result", { revision: 1, status: "READY_FOR_REVIEW" }), step.state.state_revision)
  assert.equal(applied.state.status, "discovery_review")

  step = await store.reserve(applied.state.state_revision)
  await writeArtifact(root, "reviews/discovery.md", { artifact: "discovery-review", revision: 1, source_revision: 1, status: "PASS" })
  applied = await store.apply(event(step.action, "discovery_review_result", { revision: 1, status: "PASS", findings: [], evidence: ["analysis schema", "discovery evidence"] }), step.state.state_revision)
  assert.equal(applied.state.status, "waiting_map_approval")

  step = await store.reserve(applied.state.state_revision)
  applied = await store.apply(event(step.action, "map_decision", { decision: "APPROVE" }), step.state.state_revision)
  assert.equal(applied.state.status, "planning")

  for (const expectedStage of ["S01", "S02"]) {
    step = await store.reserve(applied.state.state_revision)
    assert.equal(step.action.action, "PLAN_STAGE")
    assert.equal(step.action.stage, expectedStage)
    await writeArtifact(root, step.action.output, { artifact: "technical-stage", stage: expectedStage, revision: step.action.revision, source_revision: step.action.source_revision, status: "REVIEW" })
    applied = await store.apply(event(step.action, "stage_plan_result", { revision: step.action.revision, status: "REVIEW" }), step.state.state_revision)

    step = await store.reserve(applied.state.state_revision)
    assert.equal(step.action.action, "REVIEW_STAGE")
    await writeArtifact(root, step.action.output, { artifact: "technical-review", stage: expectedStage, revision: step.action.revision, source_revision: step.action.source_revision, status: "PASS" })
    applied = await store.apply(event(step.action, "stage_review_result", { revision: step.action.revision, status: "PASS", findings: [], evidence: ["technical artifact"] }), step.state.state_revision)
  }
  assert.equal(applied.state.status, "human_reviewing")

  for (const expectedStage of ["S01", "S02"]) {
    step = await store.reserve(applied.state.state_revision)
    assert.equal(step.action.action, "PLAN_HUMAN_REVIEW")
    await writeArtifact(root, step.action.output, { artifact: "human-review", stage: expectedStage, revision: step.action.revision, source_revision: step.action.source_revision, status: "REVIEW" })
    applied = await store.apply(event(step.action, "human_plan_result", { revision: step.action.revision, status: "REVIEW" }), step.state.state_revision)

    step = await store.reserve(applied.state.state_revision)
    assert.equal(step.action.action, "REVIEW_HUMAN_REVIEW")
    await writeArtifact(root, step.action.output, { artifact: "human-review-review", stage: expectedStage, revision: step.action.revision, source_revision: step.action.source_revision, status: "PASS" })
    applied = await store.apply(event(step.action, "human_review_result", { revision: step.action.revision, status: "PASS", findings: [], evidence: ["human artifact"] }), step.state.state_revision)
  }
  assert.equal(applied.state.status, "waiting_plan_approval")

  step = await store.reserve(applied.state.state_revision)
  assert.equal(step.action.action, "APPROVE_PLAN")
  assert.ok(step.action.inputs.includes("reviews/discovery.md"))
  assert.ok(step.action.inputs.includes("reviews/02-human-review.md"))
  applied = await store.apply(event(step.action, "plan_decision", { decision: "APPROVE" }), step.state.state_revision)
  assert.equal(applied.state.status, "ready")

  const complete = await store.reserve(applied.state.state_revision)
  assert.equal(complete.action.action, "COMPLETE")
  assert.equal((await store.validate()).valid, true)
})
'''


PROTOCOL_TEST = r'''
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
'''


REOPENING_TEST = r'''
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
'''


LEGACY_TEST = r'''
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
'''


RELEASE_GATES_TEST = r'''
import assert from "node:assert/strict"
import { mkdir, mkdtemp, readFile, symlink, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"

import { newState, renderPlan, reserveNext, WorkflowStore } from "../runtime/orchestrator.js"

async function toolContext(directory) {
  return { directory, worktree: directory, project: {}, client: {}, sessionID: "test", messageID: "test", agent: "test", abort: new AbortController().signal }
}

test("actual native OpenCode tools import and invoke controller APIs", async () => {
  const tools = await import("../dist-tools/tools/orchestrator.js")
  assert.deepEqual(Object.keys(tools).sort(), ["orchestrator_next", "orchestrator_status", "orchestrator_update"])
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-native-tool-"))
  const context = await toolContext(base)
  const status = JSON.parse(await tools.orchestrator_status.execute({ request: "native-tool" }, context))
  assert.equal(status.status, "discovery")
  const next = JSON.parse(await tools.orchestrator_next.execute({ request: "native-tool" }, context))
  assert.equal(next.action.action, "DISCOVER")
  const update = JSON.parse(await tools.orchestrator_update.execute({ request: "native-tool", transition_id: next.action.transition_id, event_type: "task_failure", payload_json: JSON.stringify({ reason: "test", detail: "intentional", retryable: true }), expected_state_revision: next.state.state_revision }, context))
  assert.equal(update.state.status, "blocked")
})

test("input symlink escaping request root is rejected", async (t) => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-symlink-"))
  const root = path.join(base, "1_orchestrator", "symlink")
  await mkdir(root, { recursive: true })
  const outside = path.join(base, "outside.md")
  await writeFile(outside, "outside\n")
  try { await symlink(outside, path.join(root, "feedback.md")) } catch (error) { t.skip(`symlink unavailable: ${error}`); return }
  await assert.rejects(() => new WorkflowStore(base, "symlink").reserve(), /symlink escapes/i)
})

test("transaction recovery succeeds only from exact base revision", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-recovery-"))
  const root = path.join(base, "1_orchestrator", "recovery")
  const internal = path.join(root, ".orchestrator")
  await mkdir(internal, { recursive: true })
  const initial = newState("recovery")
  await writeFile(path.join(internal, "state.json"), JSON.stringify(initial, null, 2) + "\n")
  await writeFile(path.join(root, "plan.md"), renderPlan(initial))
  const target = reserveNext(initial).state
  const journal = { entry_id: "recovery:reserve:1", timestamp: new Date(0).toISOString(), action: "reserve", state_revision: target.state_revision, transition_id: target.pending.transition_id, detail: {} }
  await writeFile(path.join(internal, "transaction.json"), JSON.stringify({ schema_version: 2, base_state_revision: 0, state: target, plan: renderPlan(target), journal }, null, 2) + "\n")
  const valid = await new WorkflowStore(base, "recovery").validate()
  assert.equal(valid.state_revision, 1)

  const conflictTarget = structuredClone(target)
  conflictTarget.state_revision = 3
  await writeFile(path.join(internal, "state.json"), JSON.stringify(conflictTarget, null, 2) + "\n")
  await writeFile(path.join(internal, "transaction.json"), JSON.stringify({ schema_version: 2, base_state_revision: 0, state: target, plan: renderPlan(target), journal }, null, 2) + "\n")
  await assert.rejects(() => new WorkflowStore(base, "recovery").validate(), /recovery conflict/i)
})

test("duplicate journal entry id with different content is a hard conflict", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-journal-conflict-"))
  const root = path.join(base, "1_orchestrator", "journal")
  const internal = path.join(root, ".orchestrator")
  await mkdir(internal, { recursive: true })
  const initial = newState("journal")
  const target = reserveNext(initial).state
  await writeFile(path.join(internal, "state.json"), JSON.stringify(initial, null, 2) + "\n")
  await writeFile(path.join(root, "plan.md"), renderPlan(initial))
  const journal = { entry_id: "same", timestamp: new Date(0).toISOString(), action: "reserve", state_revision: 1, transition_id: target.pending.transition_id, detail: { version: 1 } }
  await writeFile(path.join(internal, "journal.jsonl"), JSON.stringify({ ...journal, detail: { version: 2 } }) + "\n")
  await writeFile(path.join(internal, "transaction.json"), JSON.stringify({ schema_version: 2, base_state_revision: 0, state: target, plan: renderPlan(target), journal }, null, 2) + "\n")
  await assert.rejects(() => new WorkflowStore(base, "journal").validate(), /journal conflict/i)
})
'''


def patch_artifacts(source: str) -> str:
    marker = '  if (pending.action === "DISCOVER") {\n    if (status !== "READY_FOR_REVIEW") return\n    if (!analysis) throw new ProtocolError("analysis.json", "READY_FOR_REVIEW requires a valid analysis artifact")\n    await assertFreshPrimaryOutput(root, pending)'
    replacement = '''  if (pending.action === "DISCOVER") {
    if (status !== "READY_FOR_REVIEW") return
    if (!analysis) throw new ProtocolError("analysis.json", "READY_FOR_REVIEW requires a valid analysis artifact")
    await assertFreshPrimaryOutput(root, pending)
    const discoveryBaseline = pending.input_snapshot.find((snapshot) => snapshot.path === "discovery.md")
    const discoveryCurrent = await captureSnapshot(root, "discovery.md")
    if (!discoveryCurrent.exists || (discoveryBaseline && snapshotEqual(discoveryBaseline, discoveryCurrent))) throw new ProtocolError("discovery.md", "discovery artifact is missing or stale")'''
    if marker not in source:
        raise RuntimeError("cannot patch discovery side-output freshness")
    source = source.replace(marker, replacement, 1)
    graph_marker = '  for (const stage of state.stages) {\n    await assertArtifact(root, stage.details, {'
    graph_replacement = '''  for (const stage of state.stages) {
    if (stage.status !== "pass" || stage.human_status !== "pass") throw new ProtocolError("state.stages", "complete artifact graph requires technical and human PASS statuses", stage.id)
    await assertArtifact(root, stage.details, {'''
    if graph_marker not in source:
        raise RuntimeError("cannot patch complete graph status check")
    return source.replace(graph_marker, graph_replacement, 1)


def apply(root: Path, log: Path) -> list[str]:
    gate_test = "tests-ts/release-gates.test.mjs"
    changed = write_files(root, {gate_test: RELEASE_GATES_TEST})
    expect_failure(["node", "--test", gate_test], cwd=root, log=log)

    artifacts = patch_artifacts((root / "src/artifacts.ts").read_text(encoding="utf-8"))
    changed += write_files(root, {
        "src/analysis.ts": ANALYSIS_TS,
        "src/review.ts": REVIEW_TS,
        "src/events.ts": EVENTS_TS,
        "src/store.ts": STORE_TS,
        "src/artifacts.ts": artifacts,
        "tools/orchestrator.ts": TOOLS_TS,
        "tests-ts/helpers.mjs": HELPERS,
        "tests-ts/journey.test.mjs": JOURNEY,
        "tests-ts/protocol.test.mjs": PROTOCOL_TEST,
        "tests-ts/reopening.test.mjs": REOPENING_TEST,
        "tests-ts/legacy.test.mjs": LEGACY_TEST,
        gate_test: RELEASE_GATES_TEST,
    })
    return changed


if __name__ == "__main__":
    repository = Path(sys.argv[1]).resolve()
    log = Path(sys.argv[2]).resolve()
    print("\n".join(apply(repository, log)))
