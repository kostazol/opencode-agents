const VERSION = "2.3.1"

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

function latestWorkflowEpoch(messages) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (message.info.role !== "user" || isGuardMessage(message)) continue
    if (!textParts(message).some((part) => part.synthetic !== true)) continue
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
    const match = normalizedItem.match(/^(?:[A-Za-z]:)?(?:[^\s`]*\/)?(1_orchestrator\/[^\s`]+\/tasks\/[0-9][0-9]-[^\s/`,]+\.md)$/)
    if (!match) return null
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
    status: field(result.text, "PLANNING"),
    mode: field(result.text, "MODE"),
    evidence: field(result.text, "Evidence"),
    paths: fieldPaths(result.text, "Задачи"),
    rejection: field(result.text, "Rejection"),
    blocker: field(result.text, "Блокер"),
  }
}

function reviewResult(result, role, label) {
  if (!result || result.role !== role) return null
  return {
    text: result.text,
    status: field(result.text, label),
    mode: field(result.text, "Review mode"),
    checkedPaths: fieldPaths(result.text, "Checked tasks"),
    readyPaths: fieldPaths(result.text, "Ready for finalize"),
    findings: field(result.text, "Findings"),
    blocker: field(result.text, "Блокер"),
  }
}

function validReview(review, paths) {
  return review?.status === "PASS" && review.mode === "NORMAL" && review.findings === "none" && review.blocker === "none" && samePaths(review.checkedPaths, paths) && samePaths(review.readyPaths, paths)
}

function validBlockReview(review, paths, blocker) {
  if (review?.status !== "BLOCKED" || review.mode !== "NORMAL" && review.mode !== "REJECTION_RECOVERY" || normalized(review.blocker) !== normalized(blocker) || !Array.isArray(paths) || paths.length > 0 && !samePaths(review.checkedPaths, paths)) return false
  const immediate = review.findings === "none" && Array.isArray(review.readyPaths) && review.readyPaths.length === 0
  const completeFinding = findingEntries(review.text).some((entry) => Number(field(entry, "Occurrence")) >= 4 && ["Signature", "Progress", "Affected tasks", "Finding", "Required correction"].every((name) => normalized(field(entry, name))))
  return immediate || completeFinding
}

function findingEntries(text) {
  const starts = [...text.matchAll(/^\s*\d+[.)]\s*$/gm)]
  return starts.map((match, index) => text.slice(match.index + match[0].length, starts[index + 1]?.index ?? text.length))
}

function finalResponse(text) {
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
  let phase = null
  if (/^(?:Готово|Стоп)(?:\s*:.*)?$/.test(lines[0] ?? "")) phase = lines.shift().split(":", 1)[0]
  if (lines.length < 4 || !lines[0].startsWith("Итог:") || !lines[1].startsWith("Задачи:") || !lines.at(-2).startsWith("Риски и ограничения:") || !lines.at(-1).startsWith("Блокер:")) return null
  if (lines.slice(2, -2).some((line) => !line.startsWith("- "))) return null
  const status = lines[0].slice("Итог:".length).trim()
  const blocker = lines.at(-1).slice("Блокер:".length).trim()
  if (!status || !blocker || phase === "Готово" && status !== "READY" || phase === "Стоп" && status !== "BLOCKED") return null
  return { status, paths: fieldPaths(lines.join("\n"), "Задачи"), blocker }
}

function normalized(value) {
  return value?.trim().replace(/\s+/g, " ") ?? ""
}

function terminalState(messages, epochIndex, sessionID, agent) {
  const latest = messages.at(-1)
  if (!latest || latest.info.role !== "assistant" || latest.info.error || !latest.info.time?.completed) return { terminal: false, frontier: "no-completed-assistant" }
  if (latest.parts.some((part) => part.type === "tool" && (part.state.status === "pending" || part.state.status === "running"))) return { terminal: false, frontier: "tool-active" }
  const tasks = workflowTasks(messages, epochIndex, sessionID)
  const last = tasks.at(-1)
  const planner = plannerResult(last)
  const response = finalResponse(messageText(latest))
  const frontier = tasks.length === 0 ? "no-workflow-task" : tasks.slice(-3).map(resultFrontier).join(">>")
  if (!planner || !response) return { terminal: false, frontier }
  if (!Array.isArray(planner.paths) || !Array.isArray(response.paths)) return { terminal: false, frontier }
  if (response.status === "BLOCKED" && response.blocker !== "none" && planner.rejection === "none" && normalized(response.blocker) === normalized(planner.blocker) && samePathsAllowEmpty(response.paths, planner.paths)) {
    const direct = planner.status === "BLOCKED" && planner.mode === "CREATE" && planner.evidence === "BLOCKED" && planner.paths.length === 0
    if (direct) return { terminal: true, frontier: `${frontier}:blocked` }
    if (planner.status === "PASS" && planner.mode === "BLOCK" && planner.evidence === "NOT_APPLICABLE") {
      const planBlock = reviewResult(tasks.at(-2), "orchestrator-plan-reviewer", "PLAN_REVIEW")
      const ultraBlock = reviewResult(tasks.at(-2), "orchestrator-plan-ultra-reviewer", "ULTRA_PLAN_REVIEW")
      const priorTerra = reviewResult(tasks.at(-3), "orchestrator-plan-reviewer", "PLAN_REVIEW")
      const acceptedPlanBlock = validBlockReview(planBlock, planner.paths, planner.blocker)
      const acceptedUltraBlock = agent === "orchestrator-analyst" && validBlockReview(ultraBlock, planner.paths, planner.blocker) && validReview(priorTerra, planner.paths)
      if (acceptedPlanBlock || acceptedUltraBlock) return { terminal: true, frontier: `${frontier}:blocked` }
    }
  }
  if (response.status !== "READY" || response.blocker !== "none" || planner.status !== "PASS" || planner.mode !== "FINALIZE" || planner.evidence !== "NOT_APPLICABLE" || planner.rejection !== "none" || planner.blocker !== "none" || !samePaths(response.paths, planner.paths)) return { terminal: false, frontier }
  const reviewer = reviewResult(tasks.at(-2), "orchestrator-plan-reviewer", "PLAN_REVIEW")
  if (agent === "orchestrator-analyst-single-model") return { terminal: validReview(reviewer, planner.paths), frontier: `${frontier}:single-ready` }
  const ultra = reviewResult(tasks.at(-2), "orchestrator-plan-ultra-reviewer", "ULTRA_PLAN_REVIEW")
  const terra = reviewResult(tasks.at(-3), "orchestrator-plan-reviewer", "PLAN_REVIEW")
  return { terminal: validReview(terra, planner.paths) && validReview(ultra, planner.paths), frontier: `${frontier}:standard-ready` }
}

function resultFrontier(result) {
  if (!result) return "no-workflow-task"
  const planner = plannerResult(result)
  if (planner) return [result.role, planner.status, planner.mode, planner.evidence, planner.paths?.join("|"), planner.rejection, planner.blocker].map(normalized).join(":")
  const label = result.role === "orchestrator-plan-ultra-reviewer" ? "ULTRA_PLAN_REVIEW" : "PLAN_REVIEW"
  const review = reviewResult(result, result.role, label)
  if (review) return [result.role, review.status, review.mode, review.checkedPaths?.join("|"), review.readyPaths?.join("|"), review.findings, review.blocker, findingFrontier(result.text)].map(normalized).join(":")
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
  const state = terminalState(messages, epoch.index, sessionID, epoch.message.info.agent)
  if (state.terminal) return { resume: false, reason: "terminal" }
  const latest = messages.at(-1)
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
