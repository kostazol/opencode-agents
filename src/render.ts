import { Analysis, HUMAN_STATUSES, JsonRecord, ProtocolError, STAGE_STATUSES, StageState, State, WorkflowStatus, integer, record, stageId, text, validateAnalysis } from "./orchestrator.js"
import { newState, stageMap, validateState } from "./state.js"

function items(values: string[]): string {
  return values.length ? `[${values.join(", ")}]` : "none"
}

export function renderPlan(stateInput: unknown, analysisInput?: unknown): string {
  const state = validateState(stateInput, analysisInput !== undefined && (stateInput as State).stages?.length && !(stateInput as State).legacy_migrated ? analysisInput : undefined)
  const analysis = analysisInput === undefined ? undefined : validateAnalysis(analysisInput)
  const lines = [
    "---",
    "schema_version: 1",
    `state_revision: ${state.state_revision}`,
    `status: ${state.status}`,
    `current_stage: ${state.current_stage ?? "none"}`,
    `analysis_revision: ${state.analysis_revision}`,
    "---",
    "# План реализации",
    "",
    "> Индекс генерируется controller; смысловые детали находятся в discovery, stage и review artifacts.",
    "",
    "## Состояние",
    "",
    `- Запрос: \`${state.request_id}\``,
    `- Workflow: \`${state.status}\``,
    `- Analysis: \`${state.analysis_status}\` revision ${state.analysis_revision}`,
    `- Feedback revision: ${state.feedback_revision}`,
  ]
  if (state.pending) lines.push(`- Pending: \`${state.pending.transition_id}\` / \`${state.pending.action}\``, `- Pending reason: ${state.pending.reason}`)
  if (state.blocker) lines.push("", "## Blocker", "", `- Reason: ${state.blocker.reason}`, `- Detail: ${state.blocker.detail}`)
  if (state.reopen) lines.push("", "## Reopening proposal", "", `- Requested by: ${state.reopen.requested_by}`, `- Seeds: ${items(state.reopen.seeds)}`, `- Affected: ${items(state.reopen.affected)}`, `- Reason: ${state.reopen.reason}`)
  lines.push("", "## Stage map", "")
  const source = new Map(analysis?.stages.map((item) => [item.id, item]) ?? [])
  for (const stage of state.stages) {
    const metadata = source.get(stage.id)
    lines.push(
      `### ${stage.id} — ${stage.title}`,
      `- Status: ${stage.status.toUpperCase()}`,
      `- Revision: ${stage.revision}`,
      `- Depends on: ${items(stage.depends_on)}`,
      `- Affected area: ${metadata?.affected_area ?? "unknown"}`,
      `- Primary risks: ${items(metadata?.risks ?? [])}`,
      `- Consumes: ${items(metadata?.contracts_consumed ?? [])}`,
      `- Produces: ${items(metadata?.contracts_produced ?? [])}`,
      `- Details: ${stage.details}`,
      `- Review: ${stage.review}`,
      `- Human review: ${stage.human_review}`,
      `- Human review revision: ${stage.human_revision}`,
      `- Human review status: ${stage.human_status.toUpperCase()}`,
      `- Human review review: ${stage.human_review_review}`,
      "",
    )
  }
  if (analysis) {
    lines.push("## Traceability", "")
    for (const item of [...analysis.requirements, ...analysis.nfrs]) lines.push(`- \`${item.id}\` → \`${item.stage}\` → ${items(item.scenarios)} → ${items(item.acceptance)}: ${item.text}`)
    lines.push("")
  }
  return `${lines.join("\n").trimEnd()}\n`
}

export function parseLegacyPlan(content: string, requestId: string): State {
  const lines = content.split(/\r?\n/)
  if (lines[0] !== "---") throw new ProtocolError("legacy.frontmatter", "start delimiter missing")
  const frontmatterEnd = lines.indexOf("---", 1)
  if (frontmatterEnd < 0) throw new ProtocolError("legacy.frontmatter", "end delimiter missing")
  const frontmatter = new Map<string, string>()
  for (const [offset, line] of lines.slice(1, frontmatterEnd).entries()) {
    const separator = line.indexOf(":")
    if (separator < 1) throw new ProtocolError(`legacy.frontmatter[${offset}]`, "expected key: value", line)
    const key = line.slice(0, separator).trim()
    if (frontmatter.has(key)) throw new ProtocolError(`legacy.frontmatter.${key}`, "duplicate field")
    frontmatter.set(key, line.slice(separator + 1).trim())
  }

  const statusAliases: Record<string, WorkflowStatus> = {
    discovery: "discovery",
    "discovery-review": "discovery_review",
    discovery_review: "discovery_review",
    "waiting-answers": "waiting_answers",
    waiting_answers: "waiting_answers",
    "waiting-approval": "waiting_map_approval",
    "waiting-map-approval": "waiting_map_approval",
    waiting_map_approval: "waiting_map_approval",
    planning: "planning",
    "human-reviewing": "human_reviewing",
    human_reviewing: "human_reviewing",
    "waiting-plan-approval": "waiting_plan_approval",
    waiting_plan_approval: "waiting_plan_approval",
    ready: "ready",
  }
  const rawStatus = frontmatter.get("status") ?? "discovery"
  if (rawStatus === "blocked") throw new ProtocolError("legacy.status", "blocked legacy plan cannot be migrated without structured blocker data")
  const mappedStatus = statusAliases[rawStatus]
  if (!mappedStatus) throw new ProtocolError("legacy.status", "unsupported legacy workflow status", rawStatus)
  const currentStage = frontmatter.get("current_stage") ?? "none"
  if (currentStage !== "none") stageId(currentStage, "legacy.current_stage")

  const state = newState(requestId)
  state.legacy_migrated = true
  state.analysis_status = "draft"
  state.status = mappedStatus
  state.current_stage = currentStage === "none" ? null : currentStage

  const headings = lines.map((line, index) => line === "## Stage map" ? index : -1).filter((index) => index >= 0)
  if (headings.length > 1) throw new ProtocolError("legacy.Stage map", "expected at most one section")
  if (!headings.length) {
    if (state.current_stage !== null) throw new ProtocolError("legacy.current_stage", "cannot reference a stage when stage map is absent", state.current_stage)
    return validateState(state)
  }

  const stageHeading = /^### (S[0-9]{2}) — (.+)$/
  const fieldLine = /^- ([^:]+): (.*)$/
  let index = headings[0] + 1
  const end = lines.findIndex((line, lineIndex) => lineIndex > headings[0] && line.startsWith("## "))
  const stageEnd = end < 0 ? lines.length : end
  while (index < stageEnd) {
    if (!lines[index]) {
      index += 1
      continue
    }
    const heading = stageHeading.exec(lines[index])
    if (!heading) throw new ProtocolError("legacy.Stage map", "expected stage heading", lines[index])
    index += 1
    const fields = new Map<string, string>()
    while (index < stageEnd && !lines[index].startsWith("### ")) {
      const line = lines[index]
      index += 1
      if (!line) continue
      const match = fieldLine.exec(line)
      if (!match) throw new ProtocolError(`legacy.${heading[1]}`, "expected '- Field: value'", line)
      if (fields.has(match[1])) throw new ProtocolError(`legacy.${heading[1]}.${match[1]}`, "duplicate field")
      fields.set(match[1], match[2])
    }
    for (const required of ["Status", "Revision", "Depends on", "Details", "Review"]) {
      if (!fields.has(required)) throw new ProtocolError(`legacy.${heading[1]}`, "missing required field", required)
    }

    const id = heading[1]
    const number = Number(id.slice(1))
    const details = fields.get("Details")!
    const slugMatch = new RegExp(`^stages/${String(number).padStart(2, "0")}-([a-z0-9]+(?:-[a-z0-9]+)*)\\.md$`).exec(details)
    if (!slugMatch) throw new ProtocolError(`legacy.${id}.Details`, "non-canonical path", details)
    const status = fields.get("Status")!.toLowerCase()
    if (!STAGE_STATUSES.has(status)) throw new ProtocolError(`legacy.${id}.Status`, "unsupported stage status", status)
    const humanStatus = (fields.get("Human review status") ?? "PENDING").toLowerCase()
    if (!HUMAN_STATUSES.has(humanStatus)) throw new ProtocolError(`legacy.${id}.Human review status`, "unsupported human-review status", humanStatus)
    const revision = integer(Number(fields.get("Revision")), `legacy.${id}.Revision`)
    const humanRevision = integer(Number(fields.get("Human review revision") ?? 0), `legacy.${id}.Human review revision`)
    const dependencyText = fields.get("Depends on")!
    const dependencies = dependencyText === "none" || dependencyText === "[]" || !dependencyText
      ? []
      : dependencyText.replace(/^\[|\]$/g, "").split(",").map((item) => stageId(item.trim(), `legacy.${id}.Depends on`))

    state.stages.push({
      id,
      title: text(heading[2], `legacy.${id}.title`),
      slug: slugMatch[1],
      depends_on: dependencies,
      status: status as StageState["status"],
      revision,
      human_status: humanStatus as StageState["human_status"],
      human_revision: humanRevision,
      details,
      review: fields.get("Review")!,
      human_review: fields.get("Human review") ?? `stages/${String(number).padStart(2, "0")}-${slugMatch[1]}.human-review.md`,
      human_review_review: fields.get("Human review review") ?? `reviews/${String(number).padStart(2, "0")}-human-review.md`,
    })
  }

  if (state.status === "ready" && state.stages.some((stage) => stage.human_status !== "pass")) {
    state.status = "human_reviewing"
    state.current_stage = state.stages.find((stage) => stage.human_status !== "pass")!.id
  }
  if ((state.status === "planning" || state.status === "human_reviewing") && state.current_stage === null) {
    const field = state.status === "planning" ? "status" : "human_status"
    state.current_stage = state.stages.find((stage) => stage[field] !== "pass")?.id ?? null
  }
  if (state.current_stage !== null && !state.stages.some((stage) => stage.id === state.current_stage)) {
    throw new ProtocolError("legacy.current_stage", "unknown stage", state.current_stage)
  }
  return validateState(state)
}

