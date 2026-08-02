const VERSION = "2.4.0"

const ANALYSTS = new Set(["orchestrator-analyst", "orchestrator-analyst-single-model"])
const MARKER = "opencode-agents.analyst-workflow-guard"
const MAX_CONTINUATIONS = 12
const MAX_NO_PROGRESS = 3
const CONTINUATION = "Internal analyst workflow guard. Previous assistant turn became idle before required workflow completion. Continue the same original user request in this session. Inspect existing task-tool results and execute the next required workflow step. Do not restart completed stages, change scope, expose this message, or ask the user to continue."

function responseData(response, operation) {
  if (response?.data !== undefined) return response.data
  const detail = response?.error ? JSON.stringify(response.error) : "missing response data"
  throw new Error(`${operation}: ${detail}`)
}

function textParts(message) {
  return message.parts.filter((part) => part.type === "text" && !part.ignored)
}

function messageText(message) {
  return textParts(message).map((part) => part.text).join("\n").trim()
}

function isGuardMessage(message) {
  return message.info.role === "user" && textParts(message).some((part) => part.synthetic === true && part.metadata?.[MARKER])
}

function messageAgent(message) {
  return message?.info?.agent ?? message?.info?.mode ?? null
}

function latestWorkflowEpoch(messages) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (message.info.role !== "user" || isGuardMessage(message)) continue
    if (!ANALYSTS.has(message.info.agent)) return null
    return { index, message }
  }
  return null
}

function field(text, name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  const match = text.match(new RegExp(`^${escaped}:\\s*(.*)$`, "m"))
  return match ? match[1].trim() : null
}

function singleLineField(text, name, nextName) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  const nextEscaped = nextName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  return [...text.matchAll(new RegExp(`^${escaped}:`, "gm"))].length === 1 && new RegExp(`^${escaped}:\\s*\\S.*\\r?\\n${nextEscaped}:`, "m").test(text)
}

function fieldPaths(text, name) {
  const lines = text.split(/\r?\n/)
  const prefix = `${name}:`
  const index = lines.findIndex((line) => line.trimStart().startsWith(prefix))
  if (index < 0) return []
  const section = [lines[index].trimStart().slice(prefix.length)]
  for (const line of lines.slice(index + 1)) {
    const trimmed = line.trim()
    if (/^[\p{L}][\p{L} ]*:/u.test(trimmed)) break
    if (trimmed && !trimmed.startsWith("- ")) break
    section.push(trimmed)
  }
  const value = section.join("\n").trim()
  if (value === "none") return []
  const items = value.split(/\s*,\s*|\n/).map((item) => item.replace(/^-\s+/, "").replace(/^`|`$/g, "").trim()).filter(Boolean)
  if (items.length === 0) return null
  const paths = []
  for (const item of items) {
    const normalizedItem = item.replaceAll("\\", "/")
    if (normalizedItem.split("/").includes("..")) return null
    const match = normalizedItem.match(/^(1_orchestrator\/([^/\s`]+)\/tasks\/[0-9]{2}-[^\s/`,]+\.md)$/)
    if (!match || match[2] === "." || match[2] === "..") return null
    paths.push(match[1])
  }
  return paths
}

function samePaths(left, right) {
  return Array.isArray(left) && Array.isArray(right) && left.length > 0 && left.length === right.length && left.every((path, index) => path === right[index])
}

function samePathsAllowEmpty(left, right) {
  return Array.isArray(left) && Array.isArray(right) && left.length === right.length && left.every((path, index) => path === right[index])
}

function taskResult(part, sessionID) {
  if (part.type !== "tool" || part.tool !== "task" || part.state.status !== "completed") return null
  const input = part.state.input
  const metadata = part.state.metadata
  if (typeof input?.subagent_type !== "string") return null
  if (input.task_id !== undefined) return null
  if (metadata?.parentSessionId !== sessionID || typeof metadata.sessionId !== "string") return null
  if (!part.state.output.includes(`<task id="${metadata.sessionId}" state="completed">`)) return null
  const start = part.state.output.indexOf("<task_result>")
  const end = part.state.output.lastIndexOf("</task_result>")
  if (start < 0 || end <= start) return null
  return { id: part.id, role: input.subagent_type, text: part.state.output.slice(start + "<task_result>".length, end).trim() }
}

function workflowTasks(messages, start, sessionID) {
  const results = []
  for (const message of messages.slice(start)) {
    if (message.info.role !== "assistant") continue
    for (const part of message.parts) {
      const result = taskResult(part, sessionID)
      if (result) results.push(result)
    }
  }
  return results
}

function plannerResult(result) {
  if (!result || result.role !== "orchestrator-task-planner") return null
  return {
    text: result.text,
    status: field(result.text, "PLANNING"),
    mode: field(result.text, "MODE"),
    origin: field(result.text, "Origin"),
    target: field(result.text, "Target"),
    evidence: field(result.text, "Evidence"),
    outcome: field(result.text, "Proposed outcome"),
    clarificationGate: field(result.text, "Clarification gate"),
    clarificationID: field(result.text, "Clarification ID"),
    questionIDs: field(result.text, "Question IDs"),
    questions: field(result.text, "Questions"),
    questionsSingleLine: singleLineField(result.text, "Questions", "Planning attempt"),
    planningAttempt: field(result.text, "Planning attempt"),
    targetState: field(result.text, "Target state"),
    paths: fieldPaths(result.text, "Задачи"),
    checkedPaths: fieldPaths(result.text, "Checked tasks"),
    deferredPaths: fieldPaths(result.text, "Deferred tasks"),
    completePaths: fieldPaths(result.text, "Complete tasks"),
    supersededPaths: fieldPaths(result.text, "Superseded tasks"),
    deferredScope: field(result.text, "Deferred scope"),
    uncertaintyIDs: field(result.text, "Uncertainty IDs"),
    uncertainties: field(result.text, "Uncertainties"),
    uncertaintiesSingleLine: singleLineField(result.text, "Uncertainties", "Uncertainty IDs"),
    reassessAfter: fieldPaths(result.text, "Reassess after"),
    issueJournal: field(result.text, "Issue journal"),
    rejection: field(result.text, "Rejection"),
    changed: field(result.text, "Изменено"),
    changedPaths: fieldPaths(result.text, "Изменено"),
    blocker: field(result.text, "Блокер"),
  }
}

function reviewResult(result, role, label) {
  if (!result || result.role !== role) return null
  return {
    text: result.text,
    status: field(result.text, label),
    mode: field(result.text, "Review mode"),
    origin: field(result.text, "Origin"),
    target: field(result.text, "Target"),
    outcome: field(result.text, "Confirmed outcome"),
    clarificationGate: field(result.text, "Clarification gate"),
    clarificationID: field(result.text, "Clarification ID"),
    questionIDs: field(result.text, "Confirmed question IDs"),
    questions: field(result.text, "Questions"),
    questionsSingleLine: singleLineField(result.text, "Questions", "Clarification incorporation"),
    clarificationIncorporation: field(result.text, "Clarification incorporation"),
    checkedPaths: fieldPaths(result.text, "Checked tasks"),
    readyPaths: fieldPaths(result.text, "Ready for finalize"),
    deferredPaths: fieldPaths(result.text, "Deferred tasks"),
    completePaths: fieldPaths(result.text, "Complete tasks"),
    supersededPaths: fieldPaths(result.text, "Superseded tasks"),
    deferredScope: field(result.text, "Deferred scope"),
    uncertaintyConfirmation: field(result.text, "Uncertainty confirmation"),
    uncertaintyIDs: field(result.text, "Confirmed uncertainty IDs"),
    uncertainties: field(result.text, "Confirmed uncertainties"),
    uncertaintiesSingleLine: singleLineField(result.text, "Confirmed uncertainties", "Reassess after"),
    reassessAfter: fieldPaths(result.text, "Reassess after"),
    findings: field(result.text, "Findings"),
    blocker: field(result.text, "Блокер"),
  }
}

function validReview(review, planner) {
  if (review?.status !== "PASS" || review.mode !== "NORMAL" || review.findings !== "none" || review.blocker !== "none") return false
  if (!review.questionsSingleLine || !review.uncertaintiesSingleLine) return false
  if (review.origin !== planner.origin || review.target !== planner.target || review.outcome !== planner.outcome || review.clarificationGate !== planner.clarificationGate || normalized(review.clarificationID) !== normalized(planner.clarificationID) || normalized(review.questionIDs) !== normalized(planner.questionIDs) || normalized(review.questions) !== normalized(planner.questions) || normalized(review.deferredScope) !== normalized(planner.deferredScope) || normalized(review.uncertaintyIDs) !== normalized(planner.uncertaintyIDs) || normalized(review.uncertainties) !== normalized(planner.uncertainties)) return false
  if (!samePathsAllowEmpty(review.checkedPaths, planner.checkedPaths) || !samePathsAllowEmpty(review.readyPaths, planner.paths) || !samePathsAllowEmpty(review.deferredPaths, planner.deferredPaths) || !samePathsAllowEmpty(review.completePaths, planner.completePaths) || !samePathsAllowEmpty(review.supersededPaths, planner.supersededPaths) || !samePathsAllowEmpty(review.reassessAfter, planner.reassessAfter)) return false
  const incorporation = planner.clarificationGate === "CONSUMED" ? "CONFIRMED" : planner.clarificationGate === "CLOSED_UNUSED" ? "NOT_APPLICABLE" : null
  if (review.clarificationIncorporation !== incorporation) return false
  return planner.outcome === "PARTIAL_READY" ? review.uncertaintyConfirmation === "CONFIRMED" : review.uncertaintyConfirmation === "NOT_APPLICABLE"
}

function matchingReviewPlan(review, planner) {
  return review.origin === planner.origin && review.target === planner.target && review.outcome === planner.outcome && review.clarificationGate === planner.clarificationGate && normalized(review.clarificationID) === normalized(planner.clarificationID) && normalized(review.questionIDs) === normalized(planner.questionIDs) && normalized(review.questions) === normalized(planner.questions) && normalized(review.deferredScope) === normalized(planner.deferredScope) && normalized(review.uncertaintyIDs) === normalized(planner.uncertaintyIDs) && normalized(review.uncertainties) === normalized(planner.uncertainties) && samePathsAllowEmpty(review.checkedPaths, planner.checkedPaths) && samePathsAllowEmpty(review.readyPaths, planner.paths) && samePathsAllowEmpty(review.deferredPaths, planner.deferredPaths) && samePathsAllowEmpty(review.completePaths, planner.completePaths) && samePathsAllowEmpty(review.supersededPaths, planner.supersededPaths) && samePathsAllowEmpty(review.reassessAfter, planner.reassessAfter)
}

function validBlockReview(review, planner) {
  if (review?.status !== "BLOCKED" || review.mode !== "NORMAL" && review.mode !== "REJECTION_RECOVERY" || !review.questionsSingleLine || !review.uncertaintiesSingleLine || normalized(review.blocker) !== normalized(planner.blocker) || !validPartitions(planner) || !validUncertainties(planner) || !matchingReviewPlan(review, planner)) return false
  const immediate = review.findings === "none"
  const completeFinding = findingEntries(review.text).some((entry) => Number(field(entry, "Occurrence")) >= 4 && ["Signature", "Progress", "Affected tasks", "Finding", "Required correction"].every((name) => normalized(field(entry, name))))
  return immediate || completeFinding
}

function validPriorReviewForBlock(review, planner) {
  return validReview(review, planner)
}

function findingEntries(text) {
  const starts = [...text.matchAll(/^\s*\d+[.)]\s*$/gm)]
  return starts.map((match, index) => text.slice(match.index + match[0].length, starts[index + 1]?.index ?? text.length))
}

function finalResponse(text) {
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
  let phase = null
  if (/^(?:Готово|Уточнение|Стоп)(?:\s*:.*)?$/.test(lines[0] ?? "")) phase = lines.shift().split(":", 1)[0]
  const value = lines.join("\n")
  const status = field(value, "Итог")
  const blocker = field(value, "Блокер")
  const result = {
    status,
    target: field(value, "Target"),
    clarificationGate: field(value, "Clarification gate"),
    clarificationID: field(value, "Clarification ID"),
    questionIDs: field(value, "Question IDs"),
    questions: field(value, "Вопросы"),
    questionsSingleLine: singleLineField(value, "Вопросы", "Задачи"),
    paths: fieldPaths(value, "Задачи"),
    deferredPaths: fieldPaths(value, "Отложенные задачи"),
    completePaths: fieldPaths(value, "Завершённые задачи"),
    supersededPaths: fieldPaths(value, "Исключённые задачи"),
    deferredScope: field(value, "Отложенный scope"),
    uncertaintyIDs: field(value, "Неопределённости"),
    uncertainties: field(value, "Uncertainties"),
    uncertaintiesSingleLine: singleLineField(value, "Uncertainties", "REASSESS после"),
    reassessAfter: fieldPaths(value, "REASSESS после"),
    risks: field(value, "Риски и ограничения"),
    blocker,
  }
  if (Object.values(result).some((item) => item === null) || ![result.paths, result.deferredPaths, result.completePaths, result.supersededPaths, result.reassessAfter].every(Array.isArray)) return null
  if (phase === "Готово" && !["READY", "PARTIAL_READY", "SATISFIED"].includes(status) || phase === "Уточнение" && status !== "CLARIFICATION_REQUIRED" || phase === "Стоп" && status !== "BLOCKED") return null
  return result
}

function normalized(value) {
  return value?.trim().replace(/\s+/g, " ") ?? ""
}

function subsetPaths(left, right) {
  return Array.isArray(left) && Array.isArray(right) && left.length > 0 && left.every((path) => right.includes(path))
}

function uniquePaths(paths) {
  return Array.isArray(paths) && new Set(paths).size === paths.length
}

function targetOf(path) {
  return path?.match(/^(1_orchestrator\/[^/]+)\/tasks\//)?.[1] ?? null
}

function normalizedTarget(value) {
  const target = typeof value === "string" ? value.trim() : ""
  return /^1_orchestrator\/(?!\.{1,2}\/)[^/\s]+\/$/.test(target) ? target : null
}

function validPartitions(plan) {
  const partitions = [plan.paths, plan.deferredPaths, plan.completePaths, plan.supersededPaths]
  if (![plan.checkedPaths, ...partitions].every(uniquePaths)) return false
  const union = partitions.flat()
  if (new Set(union).size !== union.length || plan.checkedPaths.length !== union.length || !plan.checkedPaths.every((path) => union.includes(path))) return false
  const target = normalizedTarget(plan.target)
  const targets = new Set(plan.checkedPaths.map(targetOf))
  return target !== null && !targets.has(null) && targets.size <= 1 && [...targets].every((item) => `${item}/` === target)
}

function matchingPartitions(response, planner) {
  return samePathsAllowEmpty(response.paths, planner.paths) && samePathsAllowEmpty(response.deferredPaths, planner.deferredPaths) && samePathsAllowEmpty(response.completePaths, planner.completePaths) && samePathsAllowEmpty(response.supersededPaths, planner.supersededPaths) && samePathsAllowEmpty(response.reassessAfter, planner.reassessAfter)
}

function matchingLineage(response, planner) {
  return normalizedTarget(response.target) !== null && response.target === planner.target && response.clarificationGate === planner.clarificationGate && normalized(response.clarificationID) === normalized(planner.clarificationID) && normalized(response.questionIDs) === normalized(planner.questionIDs) && normalized(response.questions) === normalized(planner.questions)
}

function validGateLineage(plan) {
  const id = normalized(plan.clarificationID)
  const questionIDs = normalized(plan.questionIDs)
  const questions = normalized(plan.questions)
  if (plan.clarificationGate === "OPEN" || plan.clarificationGate === "CLOSED_UNUSED") return id === "none" && questionIDs === "none" && questions === "none"
  if (plan.clarificationGate === "WAITING" || plan.clarificationGate === "CONSUMED") return id && id !== "none" && questionIDs && questionIDs !== "none" && questions && questions !== "none"
  return false
}

function validUncertainties(plan) {
  const idsValue = normalized(plan.uncertaintyIDs)
  const entriesValue = normalized(plan.uncertainties)
  if (idsValue === "none" || entriesValue === "none") return idsValue === "none" && entriesValue === "none"
  const ids = idsValue.split(/\s*,\s*/)
  const entries = entriesValue.split(/\s*\|\|\s*/)
  if (new Set(ids).size !== ids.length || entries.length !== ids.length) return false
  const entryIDs = []
  for (const entry of entries) {
    const match = entry.match(/^([^{};]+)\{(.+)\}$/)
    if (!match) return false
    const fields = match[2].split(";")
    const expected = ["question", "static", "implementation", "unlock", "durable", "affected", "condition"]
    if (fields.length !== expected.length || fields.some((item, index) => !item.startsWith(`${expected[index]}=`) || !item.slice(expected[index].length + 1).trim())) return false
    entryIDs.push(match[1].trim())
  }
  return ids.every((id, index) => id === entryIDs[index])
}

function validIssueJournal(plan) {
  const target = normalizedTarget(plan.target)
  return target !== null && plan.issueJournal === `${target}planning-issues.md` && plan.changed === plan.issueJournal
}

function validOutcomeShape(plan) {
  if (plan.outcome === "READY") return plan.paths.length > 0 && plan.deferredPaths.length === 0 && plan.deferredScope === "none" && plan.uncertaintyIDs === "none" && plan.uncertainties === "none" && plan.reassessAfter.length === 0
  if (plan.outcome === "PARTIAL_READY") return plan.paths.length > 0 && plan.deferredScope !== "none" && plan.uncertaintyIDs !== "none" && plan.uncertaintiesSingleLine && plan.uncertainties !== "none" && validUncertainties(plan) && subsetPaths(plan.reassessAfter, plan.paths)
  if (plan.outcome === "SATISFIED") return plan.origin === "REASSESS" && plan.paths.length === 0 && plan.deferredPaths.length === 0 && plan.completePaths.length > 0 && plan.deferredScope === "none" && plan.uncertaintyIDs === "none" && plan.uncertainties === "none" && plan.reassessAfter.length === 0
  return false
}

function matchingOutcome(response, planner) {
  if (response.status !== planner.outcome || !response.questionsSingleLine || !response.uncertaintiesSingleLine || !validPartitions(planner) || !validUncertainties(planner) || !matchingPartitions(response, planner)) return false
  if (!matchingLineage(response, planner) || !validGateLineage(planner) || !["CONSUMED", "CLOSED_UNUSED"].includes(planner.clarificationGate)) return false
  if (normalized(response.deferredScope) !== normalized(planner.deferredScope) || normalized(response.uncertaintyIDs) !== normalized(planner.uncertaintyIDs) || normalized(response.uncertainties) !== normalized(planner.uncertainties)) return false
  return validOutcomeShape(planner)
}

function priorPlannerHistory(messages, epochIndex, sessionID, target) {
  const history = []
  for (const message of messages.slice(0, epochIndex)) {
    if (message.info.role !== "assistant") continue
    for (const part of message.parts) {
      const planner = plannerResult(taskResult(part, sessionID))
      if (planner && normalizedTarget(planner.target) !== null && planner.target === target) history.push({ planner, response: finalResponse(messageText(message)) })
    }
  }
  return history
}

function validWaitingPlanner(planner, response) {
  if (!planner || !response || planner.status !== "CLARIFICATION_REQUIRED" || !["CREATE", "REASSESS"].includes(planner.mode) || planner.origin !== planner.mode || planner.evidence !== "COMPLETE" || planner.outcome !== "NOT_APPLICABLE" || planner.clarificationGate !== "WAITING" || !validGateLineage(planner) || !planner.questionsSingleLine || !planner.uncertaintiesSingleLine || !validUncertainties(planner) || planner.planningAttempt !== "COMPLETE" || planner.changed !== "none" || planner.rejection !== "none" || planner.blocker !== "none" || !validPartitions(planner)) return false
  const validTargetState = planner.mode === "CREATE" ? planner.targetState === "ABSENT" && planner.checkedPaths.length === 0 : planner.targetState === "UNCHANGED"
  return validTargetState && response.status === "CLARIFICATION_REQUIRED" && response.blocker === "none" && response.questionsSingleLine && response.uncertaintiesSingleLine && matchingLineage(response, planner) && matchingPartitions(response, planner) && normalized(response.deferredScope) === normalized(planner.deferredScope) && normalized(response.uncertaintyIDs) === normalized(planner.uncertaintyIDs) && normalized(response.uncertainties) === normalized(planner.uncertainties)
}

function activePriorClarification(messages, epochIndex, sessionID, target) {
  const latest = priorPlannerHistory(messages, epochIndex, sessionID, target).at(-1)
  return validWaitingPlanner(latest?.planner, latest?.response) ? latest.planner : null
}

function validConsumedHistory(messages, epochIndex, sessionID, planner) {
  if (planner.clarificationGate !== "CONSUMED") return true
  const prior = activePriorClarification(messages, epochIndex, sessionID, planner.target)
  if (!prior || normalized(prior.clarificationID) !== normalized(planner.clarificationID) || normalized(prior.questionIDs) !== normalized(planner.questionIDs) || normalized(prior.questions) !== normalized(planner.questions)) return false
  return messages[epochIndex]?.info.role === "user" && !isGuardMessage(messages[epochIndex])
}

function validDirectBlock(planner, response) {
  if (planner.status !== "BLOCKED" || !["CREATE", "REASSESS"].includes(planner.mode) || planner.origin !== planner.mode || normalizedTarget(planner.target) === null || planner.evidence !== "BLOCKED" || planner.outcome !== "NOT_APPLICABLE" || !validGateLineage(planner) || planner.changed !== "none" || planner.rejection !== "none" || planner.blocker === "none") return false
  if (!response.questionsSingleLine || !response.uncertaintiesSingleLine || !validUncertainties(planner) || !matchingPartitions(response, planner) || !matchingLineage(response, planner) || normalized(response.deferredScope) !== normalized(planner.deferredScope) || normalized(response.uncertaintyIDs) !== normalized(planner.uncertaintyIDs) || normalized(response.uncertainties) !== normalized(planner.uncertainties) || normalized(response.blocker) !== normalized(planner.blocker)) return false
  if (planner.mode === "CREATE") return planner.targetState === "ABSENT" && planner.checkedPaths.length === 0 && planner.paths.length === 0 && planner.deferredPaths.length === 0 && planner.completePaths.length === 0 && planner.supersededPaths.length === 0
  return planner.targetState === "UNCHANGED" && validPartitions(planner)
}

function validBlockPlanner(planner) {
  return planner.status === "PASS" && planner.mode === "BLOCK" && ["CREATE", "REASSESS"].includes(planner.origin) && planner.evidence === "NOT_APPLICABLE" && ["CONSUMED", "CLOSED_UNUSED"].includes(planner.clarificationGate) && validGateLineage(planner) && planner.planningAttempt === "NOT_APPLICABLE" && planner.targetState === "PRESENT" && validPartitions(planner) && validUncertainties(planner) && validOutcomeShape(planner) && validIssueJournal(planner) && planner.rejection === "none" && planner.blocker !== "none"
}

function terminalState(messages, epochIndex, sessionID, agent) {
  const latest = messages.at(-1)
  if (!latest || latest.info.role !== "assistant" || messageAgent(latest) !== agent || latest.info.error || !latest.info.time?.completed) return { terminal: false, frontier: "no-completed-analyst-assistant" }
  if (latest.parts.some((part) => part.type === "tool" && (part.state.status === "pending" || part.state.status === "running"))) return { terminal: false, frontier: "tool-active" }
  const tasks = workflowTasks(messages, epochIndex, sessionID)
  const last = tasks.at(-1)
  const planner = plannerResult(last)
  const response = finalResponse(messageText(latest))
  const frontier = tasks.length === 0 ? "no-workflow-task" : tasks.slice(-3).map(resultFrontier).join(">>")
  if (!planner || !response) return { terminal: false, frontier }
  const plannerPathSets = [planner.paths, planner.checkedPaths, planner.deferredPaths, planner.completePaths, planner.supersededPaths, planner.reassessAfter]
  const responsePathSets = [response.paths, response.deferredPaths, response.completePaths, response.supersededPaths, response.reassessAfter]
  if (![...plannerPathSets, ...responsePathSets].every(Array.isArray)) return { terminal: false, frontier }
  if (response.status === "CLARIFICATION_REQUIRED") {
    const matchingClarification = response.clarificationGate === "WAITING" && planner.clarificationGate === "WAITING" && matchingLineage(response, planner)
    const validQuestions = planner.questionsSingleLine && response.questionsSingleLine && normalized(planner.clarificationID) && planner.clarificationID !== "none" && normalized(planner.questionIDs) && planner.questionIDs !== "none" && normalized(planner.questions) && planner.questions !== "none"
    const validPlanner = planner.status === "CLARIFICATION_REQUIRED" && ["CREATE", "REASSESS"].includes(planner.mode) && planner.origin === planner.mode && planner.evidence === "COMPLETE" && planner.outcome === "NOT_APPLICABLE" && planner.planningAttempt === "COMPLETE" && planner.uncertaintiesSingleLine && validUncertainties(planner) && planner.changed === "none" && planner.rejection === "none" && planner.blocker === "none"
    const validTarget = planner.mode === "CREATE" ? planner.targetState === "ABSENT" && validPartitions(planner) && planner.checkedPaths.length === 0 : planner.targetState === "UNCHANGED" && validPartitions(planner)
    const matchingMetadata = normalized(response.deferredScope) === normalized(planner.deferredScope) && normalized(response.uncertaintyIDs) === normalized(planner.uncertaintyIDs) && normalized(response.uncertainties) === normalized(planner.uncertainties)
    if (!activePriorClarification(messages, epochIndex, sessionID, planner.target) && matchingPartitions(response, planner) && matchingClarification && matchingMetadata && response.uncertaintiesSingleLine && validQuestions && validPlanner && validTarget && response.blocker === "none") return { terminal: true, frontier: `${frontier}:clarification` }
    return { terminal: false, frontier }
  }
  if (response.status === "BLOCKED" && response.blocker !== "none" && planner.rejection === "none" && normalized(response.blocker) === normalized(planner.blocker) && samePathsAllowEmpty(response.paths, planner.paths) && samePathsAllowEmpty(response.deferredPaths, planner.deferredPaths) && samePathsAllowEmpty(response.completePaths, planner.completePaths) && samePathsAllowEmpty(response.supersededPaths, planner.supersededPaths)) {
    const consumedHistory = validConsumedHistory(messages, epochIndex, sessionID, planner)
    const direct = consumedHistory && validDirectBlock(planner, response)
    if (direct) return { terminal: true, frontier: `${frontier}:blocked` }
    if (consumedHistory && validBlockPlanner(planner)) {
      const planBlock = reviewResult(tasks.at(-2), "orchestrator-plan-reviewer", "PLAN_REVIEW")
      const ultraBlock = reviewResult(tasks.at(-2), "orchestrator-plan-ultra-reviewer", "ULTRA_PLAN_REVIEW")
      const priorTerra = reviewResult(tasks.at(-3), "orchestrator-plan-reviewer", "PLAN_REVIEW")
      const acceptedPlanBlock = validBlockReview(planBlock, planner)
      const acceptedUltraBlock = agent === "orchestrator-analyst" && validBlockReview(ultraBlock, planner) && validPriorReviewForBlock(priorTerra, planner)
      if (acceptedPlanBlock || acceptedUltraBlock) return { terminal: true, frontier: `${frontier}:blocked` }
    }
  }
  const validFinalizeState = planner.targetState === "PRESENT" && planner.planningAttempt === "NOT_APPLICABLE" && samePathsAllowEmpty(planner.changedPaths, planner.outcome === "SATISFIED" ? [] : planner.paths)
  if (response.blocker !== "none" || planner.status !== "PASS" || planner.mode !== "FINALIZE" || !["CREATE", "REASSESS"].includes(planner.origin) || planner.evidence !== "NOT_APPLICABLE" || planner.rejection !== "none" || planner.blocker !== "none" || !validFinalizeState || !validConsumedHistory(messages, epochIndex, sessionID, planner) || !matchingOutcome(response, planner)) return { terminal: false, frontier }
  const reviewer = reviewResult(tasks.at(-2), "orchestrator-plan-reviewer", "PLAN_REVIEW")
  if (agent === "orchestrator-analyst-single-model") return { terminal: validReview(reviewer, planner), frontier: `${frontier}:single-${planner.outcome.toLowerCase()}` }
  const ultra = reviewResult(tasks.at(-2), "orchestrator-plan-ultra-reviewer", "ULTRA_PLAN_REVIEW")
  const terra = reviewResult(tasks.at(-3), "orchestrator-plan-reviewer", "PLAN_REVIEW")
  return { terminal: validReview(terra, planner) && validReview(ultra, planner), frontier: `${frontier}:standard-${planner.outcome.toLowerCase()}` }
}

function resultFrontier(result) {
  if (!result) return "no-workflow-task"
  const planner = plannerResult(result)
  if (planner) return [result.role, planner.status, planner.mode, planner.origin, planner.target, planner.evidence, planner.outcome, planner.clarificationGate, planner.clarificationID, planner.questionIDs, planner.questions, planner.planningAttempt, planner.targetState, planner.paths?.join("|"), planner.checkedPaths?.join("|"), planner.deferredPaths?.join("|"), planner.completePaths?.join("|"), planner.supersededPaths?.join("|"), planner.deferredScope, planner.uncertaintyIDs, planner.uncertainties, planner.reassessAfter?.join("|"), planner.rejection, planner.blocker].map(normalized).join(":")
  const label = result.role === "orchestrator-plan-ultra-reviewer" ? "ULTRA_PLAN_REVIEW" : "PLAN_REVIEW"
  const review = reviewResult(result, result.role, label)
  if (review) return [result.role, review.status, review.mode, review.origin, review.target, review.outcome, review.clarificationGate, review.clarificationID, review.questionIDs, review.questions, review.clarificationIncorporation, review.checkedPaths?.join("|"), review.readyPaths?.join("|"), review.deferredPaths?.join("|"), review.completePaths?.join("|"), review.supersededPaths?.join("|"), review.deferredScope, review.uncertaintyConfirmation, review.uncertaintyIDs, review.uncertainties, review.reassessAfter?.join("|"), review.findings, review.blocker, findingFrontier(result.text)].map(normalized).join(":")
  return result.role
}

function findingFrontier(text) {
  return [...text.matchAll(/^\s*(Signature|Occurrence|Progress|Affected tasks|Finding|Required correction):\s*(.*)$/gm)].map((match) => `${match[1]}=${match[2].trim()}`).join("|")
}

function guardMarkers(messages, start) {
  const markers = []
  for (const message of messages.slice(start)) {
    if (message.info.role !== "user") continue
    for (const part of textParts(message)) {
      const marker = part.metadata?.[MARKER]
      if (part.synthetic === true && marker) markers.push(marker)
    }
  }
  return markers
}

function isCancellation(text) {
  return /^\s*(?:(?:actually|i\s+changed\s+my\s+mind|я\s+передумал)[,;:]?\s*|(?:could|can)\s+you\s+|мож(?:ешь|ете)\s+)?(?:(?:please|пожалуйста)[,!]?\s+)?(?:stop|cancel|do\s+not\s+(?:continue|proceed|resume)|don['’]?t\s+(?:continue|proceed|resume)|отмен\S*|останов\S*|прекрат\S*|не\s+(?:продолжай\S*|возобновляй\S*)|хватит)(?:[\s.!?]|$)/i.test(text)
}

function continuationDecision(messages, sessionID) {
  const epoch = latestWorkflowEpoch(messages)
  if (!epoch || isCancellation(messageText(epoch.message))) return { resume: false, reason: "not-analyst-workflow" }
  const latest = messages.at(-1)
  if (!latest || latest.info.role !== "assistant" || messageAgent(latest) !== epoch.message.info.agent) return { resume: false, reason: "not-analyst-workflow" }
  const state = terminalState(messages, epoch.index, sessionID, epoch.message.info.agent)
  if (state.terminal) return { resume: false, reason: "terminal" }
  if (!latest || latest.info.role !== "assistant" || latest.info.error || !latest.info.time?.completed) return { resume: false, reason: "not-completed" }
  const markers = guardMarkers(messages, epoch.index)
  if (markers.some((marker) => marker.triggerAssistantID === latest.info.id)) return { resume: false, reason: "duplicate" }
  if (markers.length >= MAX_CONTINUATIONS) return { resume: false, reason: "continuation-cap" }
  let unchanged = 0
  for (let index = markers.length - 1; index >= 0 && markers[index].frontier === state.frontier; index -= 1) unchanged += 1
  if (unchanged >= MAX_NO_PROGRESS) return { resume: false, reason: "no-progress-cap" }
  return { resume: true, agent: epoch.message.info.agent, model: epoch.message.info.model, epochID: epoch.message.info.id, triggerAssistantID: latest.info.id, attempt: markers.length + 1, frontier: state.frontier }
}

async function AnalystWorkflowGuard({ client, directory }) {
  const locks = new Map()
  const handled = new Set()
  const pending = new Map()

  async function log(level, message, extra = {}) {
    try {
      await client.app.log({ body: { service: "analyst-workflow-guard", level, message, extra }, query: { directory } })
    } catch {}
  }

  async function inspect(sessionID) {
    if (handled.has(sessionID)) return
    handled.add(sessionID)
    try {
      const session = responseData(await client.session.get({ path: { id: sessionID }, query: { directory } }), "get session")
      if (session.parentID) return
      if (session.agent && !ANALYSTS.has(session.agent)) return
      const messages = responseData(await client.session.messages({ path: { id: sessionID }, query: { directory: session.directory } }), "get messages")
      const pendingTrigger = pending.get(sessionID)
      if (pendingTrigger) {
        const latestAssistant = [...messages].reverse().find((message) => message.info.role === "assistant")
        const persisted = guardMarkers(messages, 0).some((marker) => marker.triggerAssistantID === pendingTrigger.triggerAssistantID)
        if (persisted || latestAssistant?.info.id !== pendingTrigger.triggerAssistantID || Date.now() - pendingTrigger.created > 30000) pending.delete(sessionID)
        else return
      }
      const decision = continuationDecision(messages, sessionID)
      if (!decision.resume) {
        if (decision.reason.endsWith("cap")) await log("warn", `Stopped automatic continuation: ${decision.reason}`, { sessionID })
        return
      }
      const current = responseData(await client.session.messages({ path: { id: sessionID }, query: { directory: session.directory } }), "recheck messages")
      const currentDecision = continuationDecision(current, sessionID)
      if (!currentDecision.resume || currentDecision.triggerAssistantID !== decision.triggerAssistantID || currentDecision.frontier !== decision.frontier) return
      const status = responseData(await client.session.status({ query: { directory: session.directory } }), "get session status")
      if (status[sessionID] && status[sessionID].type !== "idle") return
      const finalMessages = responseData(await client.session.messages({ path: { id: sessionID }, query: { directory: session.directory } }), "final message recheck")
      const finalDecision = continuationDecision(finalMessages, sessionID)
      if (!finalDecision.resume || finalDecision.triggerAssistantID !== decision.triggerAssistantID || finalDecision.frontier !== decision.frontier) return
      pending.set(sessionID, { triggerAssistantID: decision.triggerAssistantID, created: Date.now() })
      const continuation = await client.session.promptAsync({
        path: { id: sessionID },
        query: { directory: session.directory },
        body: {
          agent: decision.agent,
          model: decision.model,
          parts: [{ type: "text", text: CONTINUATION, synthetic: true, metadata: { [MARKER]: { version: 1, epochID: decision.epochID, triggerAssistantID: decision.triggerAssistantID, attempt: decision.attempt, frontier: decision.frontier } } }],
        },
      })
      if (continuation?.error) {
        pending.delete(sessionID)
        throw new Error(`continue session: ${JSON.stringify(continuation.error)}`)
      }
      await log("info", "Continued incomplete analyst workflow", { sessionID, attempt: decision.attempt })
    } catch (error) {
      await log("error", "Analyst workflow inspection failed", { sessionID, error: error instanceof Error ? error.message : String(error) })
    } finally {
      handled.delete(sessionID)
    }
  }

  return {
    event: async ({ event }) => {
      if (event.type !== "session.idle") return
      const sessionID = event.properties.sessionID
      const previous = locks.get(sessionID) ?? Promise.resolve()
      const current = previous.then(() => inspect(sessionID))
      locks.set(sessionID, current)
      await current
      if (locks.get(sessionID) === current) locks.delete(sessionID)
    },
  }
}

AnalystWorkflowGuard.testing = Object.freeze({ VERSION, continuationDecision, terminalState })

export default AnalystWorkflowGuard
