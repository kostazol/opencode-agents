import { AGENT_ACTIONS, EVENT_BY_ACTION, Analysis, EventInput, JsonRecord, PendingAction, ProtocolError, State, affectedStageClosure, boolean, clone, exactFields, record, strings, text, validateAnalysis } from "./orchestrator.js"
import { normalizeProgress, sha, stableJson, stageMap, stagesFromAnalysis, validateState } from "./state.js"
import { applyReopen, block, choice, feedbackText, proposeReopen, recordRevise, requireRevision } from "./review.js"

async function applyStage(base: string, state: State, pending: PendingAction, payload: JsonRecord, analysis?: Analysis): Promise<JsonRecord> {
  const stage = stageMap(state).get(pending.stage ?? "")
  if (!stage) throw new ProtocolError("state.pending.stage", "stage action requires known stage", pending.stage)
  requireRevision(payload, pending.revision!)
  if (pending.action === "PLAN_STAGE") {
    const status = choice(payload, "status", ["REVIEW", "BLOCKED"])
    if (status === "REVIEW") {
      stage.status = "review"
      return { status: "review", stage: stage.id, revision: stage.revision }
    }
    return block(state, pending, "stage_plan_blocked", text(payload.detail, "event.payload.detail"), payload.retryable !== false)
  }
  if (pending.action === "REVIEW_STAGE") {
    const status = choice(payload, "status", ["PASS", "REVISE", "REOPEN", "BLOCKED"])
    const key = `TECHNICAL:${stage.id}`
    if (status === "PASS") {
      delete state.convergence[key]
      stage.status = "pass"
      return { status: "pass", stage: stage.id, revision: stage.revision }
    }
    if (status === "REVISE") {
      const result = await recordRevise(base, state, key, stage.revision, payload)
      stage.status = "proposed"
      state.status = "planning"
      if (result.stalled) return block(state, pending, "no_semantic_progress", `Repeated unchanged findings: ${result.summary}`)
      return { status: state.status, stage: stage.id, next_revision: stage.revision + 1 }
    }
    if (status === "REOPEN") {
      if (!analysis) throw new ProtocolError("analysis", "reopening requires analysis.json")
      return proposeReopen(state, analysis, payload, "reviewer")
    }
    return block(state, pending, "stage_review_blocked", text(payload.detail, "event.payload.detail"), payload.retryable !== false)
  }
  if (pending.action === "PLAN_HUMAN_REVIEW") {
    const status = choice(payload, "status", ["REVIEW", "BLOCKED"])
    if (status === "REVIEW") {
      stage.human_status = "review"
      return { status: "review", stage: stage.id, revision: stage.human_revision }
    }
    return block(state, pending, "human_plan_blocked", text(payload.detail, "event.payload.detail"), payload.retryable !== false)
  }
  if (pending.action === "REVIEW_HUMAN_REVIEW") {
    const status = choice(payload, "status", ["PASS", "REVISE", "REOPEN", "BLOCKED"])
    const key = `HUMAN:${stage.id}`
    if (status === "PASS") {
      delete state.convergence[key]
      stage.human_status = "pass"
      return { status: "pass", stage: stage.id, revision: stage.human_revision }
    }
    if (status === "REVISE") {
      const result = await recordRevise(base, state, key, stage.human_revision, payload)
      stage.human_status = "pending"
      state.status = "human_reviewing"
      if (result.stalled) return block(state, pending, "no_semantic_progress", `Repeated unchanged findings: ${result.summary}`)
      return { status: state.status, stage: stage.id, next_revision: stage.human_revision + 1 }
    }
    if (status === "REOPEN") {
      if (!analysis) throw new ProtocolError("analysis", "reopening requires analysis.json")
      return proposeReopen(state, analysis, payload, "reviewer")
    }
    return block(state, pending, "human_review_blocked", text(payload.detail, "event.payload.detail"), payload.retryable !== false)
  }
  throw new ProtocolError("state.pending.action", "unsupported stage action", pending.action)
}

async function applyNonStage(base: string, state: State, pending: PendingAction, payload: JsonRecord, analysis?: Analysis): Promise<JsonRecord> {
  if (pending.action === "DISCOVER") {
    requireRevision(payload, pending.revision!)
    const status = choice(payload, "status", ["QUESTIONS", "READY_FOR_REVIEW", "BLOCKED"])
    if (status === "QUESTIONS") {
      state.question_revision += 1
      state.status = "waiting_answers"
      return { status: state.status, question_revision: state.question_revision }
    }
    if (status === "READY_FOR_REVIEW") {
      if (!analysis) throw new ProtocolError("analysis", "READY_FOR_REVIEW requires analysis.json")
      state.analysis_status = "review"
      state.status = "discovery_review"
      return { status: state.status, analysis_revision: state.analysis_revision }
    }
    return block(state, pending, "discovery_blocked", text(payload.detail, "event.payload.detail"), payload.retryable !== false)
  }
  if (pending.action === "REVIEW_DISCOVERY") {
    requireRevision(payload, pending.revision!)
    const status = choice(payload, "status", ["PASS", "REVISE", "BLOCKED"])
    if (status === "PASS") {
      delete state.convergence.DISCOVERY
      state.analysis_status = "reviewed"
      state.status = "waiting_map_approval"
      return { status: state.status }
    }
    if (status === "REVISE") {
      const result = await recordRevise(base, state, "DISCOVERY", pending.revision!, payload)
      state.analysis_status = "draft"
      state.status = "discovery"
      if (result.stalled) return block(state, pending, "no_semantic_progress", `Repeated unchanged findings: ${result.summary}`)
      return { status: state.status, reason: "discovery-review-revise" }
    }
    return block(state, pending, "discovery_review_blocked", text(payload.detail, "event.payload.detail"), payload.retryable !== false)
  }
  if (pending.action === "ASK_QUESTIONS") {
    const answers = strings(payload.answers, "event.payload.answers", false)
    state.status = "discovery"
    return { status: state.status, answers: answers.length }
  }
  if (pending.action === "APPROVE_MAP") {
    const decision = choice(payload, "decision", ["APPROVE", "FEEDBACK"])
    if (decision === "FEEDBACK") {
      feedbackText(payload)
      state.feedback_revision += 1
      state.analysis_status = "draft"
      state.status = "discovery"
      state.convergence = {}
      return { status: state.status, feedback_revision: state.feedback_revision }
    }
    if (!analysis) throw new ProtocolError("analysis", "map approval requires analysis.json")
    const stages = stagesFromAnalysis(analysis)
    if (state.legacy_migrated) {
      const previous = stageMap(state)
      for (const candidate of stages) {
        const old = previous.get(candidate.id)
        if (old && old.title === candidate.title && old.slug === candidate.slug && JSON.stringify(old.depends_on) === JSON.stringify(candidate.depends_on)) {
          candidate.status = old.status
          candidate.revision = old.revision
          candidate.human_status = old.human_status
          candidate.human_revision = old.human_revision
        }
      }
      state.legacy_migrated = false
    }
    state.stages = stages
    state.analysis_status = "approved"
    state.status = "planning"
    state.current_stage = stages[0].id
    return { status: state.status, current_stage: state.current_stage }
  }
  if (pending.action === "APPROVE_PLAN") {
    const decision = choice(payload, "decision", ["APPROVE", "FEEDBACK"])
    if (decision === "APPROVE") {
      state.status = "ready"
      state.current_stage = null
      return { status: state.status }
    }
    const remarks = feedbackText(payload)
    const scope = typeof payload.scope === "string" ? payload.scope : "DISCOVERY"
    if (scope === "STAGES") {
      if (!analysis) throw new ProtocolError("analysis", "stage feedback requires analysis.json")
      const seeds = strings(payload.affected_stages, "event.payload.affected_stages", false)
      const affected = affectedStageClosure(analysis, seeds)
      const stages = stageMap(state)
      for (const id of affected) {
        stages.get(id)!.status = "proposed"
        stages.get(id)!.human_status = "pending"
      }
      state.status = "planning"
      state.current_stage = affected[0]
      state.feedback_revision += 1
      state.convergence = {}
      return { status: state.status, reopened: affected, reason: remarks, feedback_revision: state.feedback_revision }
    }
    if (scope !== "DISCOVERY") throw new ProtocolError("event.payload.scope", "must be STAGES or DISCOVERY", scope)
    state.feedback_revision += 1
    state.analysis_status = "draft"
    state.status = "discovery"
    state.current_stage = null
    state.convergence = {}
    for (const stage of state.stages) {
      stage.status = "proposed"
      stage.human_status = "pending"
    }
    return { status: state.status, feedback_revision: state.feedback_revision }
  }
  if (pending.action === "APPROVE_REOPEN") {
    if (!analysis) throw new ProtocolError("analysis", "reopening requires analysis.json")
    return applyReopen(state, analysis, payload)
  }
  if (pending.action === "RESOLVE_BLOCKER") {
    if (!state.blocker) throw new ProtocolError("state.blocker", "no blocker to resolve")
    const decision = choice(payload, "decision", ["RETRY", "ABORT"])
    if (decision === "ABORT") {
      state.blocker.retryable = false
      return { status: "blocked", aborted: true }
    }
    if (!state.blocker.retryable) throw new ProtocolError("event.payload.decision", "blocker is not retryable")
    if (state.blocker.reason === "no_semantic_progress") {
      feedbackText(payload)
      state.feedback_revision += 1
      state.convergence = {}
    }
    state.status = state.blocker.resume_status
    state.blocker = null
    return { status: state.status, retried: true }
  }
  throw new ProtocolError("state.pending.action", "unsupported action", pending.action)
}

export async function applyEvent(base: string, input: unknown, eventInput: unknown, analysisInput?: unknown, expectedStateRevision?: number): Promise<{ state: State; result: JsonRecord }> {
  const cross = analysisInput !== undefined && (input as State).stages?.length && !(input as State).legacy_migrated ? analysisInput : undefined
  const state = validateState(input, cross)
  const event = record(eventInput, "event") as unknown as EventInput
  exactFields(event as unknown as JsonRecord, ["transition_id", "type", "payload"], "event")
  const eventDigest = sha(event)
  const applied = state.applied[event.transition_id]
  if (applied) {
    if (applied.event_digest !== eventDigest) throw new ProtocolError("event", "transition was already applied with different payload", event.transition_id)
    return { state, result: clone(applied.result) }
  }
  if (expectedStateRevision !== undefined && state.state_revision !== expectedStateRevision) throw new ProtocolError("expected_state_revision", "state revision conflict", { expected: expectedStateRevision, actual: state.state_revision })
  if (!state.pending || state.pending.transition_id !== event.transition_id) throw new ProtocolError("event.transition_id", "does not match pending transition", event.transition_id)
  const payload = record(event.payload, "event.payload")
  const next = clone(state)
  const pending = next.pending!
  let result: JsonRecord
  if (event.type === "task_failure") {
    if (!AGENT_ACTIONS.has(pending.action)) throw new ProtocolError("event.type", "task_failure is valid only for agent actions")
    const reason = choice(payload, "reason", ["timeout", "cancelled", "permission_denied", "malformed_result", "tool_error"])
    const detail = text(payload.detail, "event.payload.detail")
    result = block(next, pending, reason, detail, payload.retryable !== false)
  } else {
    const expected = EVENT_BY_ACTION[pending.action]
    if (event.type !== expected) throw new ProtocolError("event.type", `expected ${expected}`, event.type)
    const analysis = analysisInput === undefined ? undefined : validateAnalysis(analysisInput)
    result = AGENT_ACTIONS.has(pending.action) && !new Set(["DISCOVER", "REVIEW_DISCOVERY"]).has(pending.action)
      ? await applyStage(base, next, pending, payload, analysis)
      : await applyNonStage(base, next, pending, payload, analysis)
  }
  next.pending = null
  next.state_revision += 1
  next.applied[event.transition_id] = { event_digest: eventDigest, result: clone(result) }
  normalizeProgress(next)
  return { state: validateState(next, analysisInput !== undefined && next.stages.length && !next.legacy_migrated ? analysisInput : undefined), result: clone(result) }
}

