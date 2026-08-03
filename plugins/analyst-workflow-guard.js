import { tool } from "@opencode-ai/plugin"

const VERSION = "3.0.0"
const ANALYSTS = new Set(["orchestrator-analyst", "orchestrator-analyst-single-model"])
const STATES = ["RUNNING", "WAITING_ANSWERS", "WAITING_APPROVAL", "BLOCKED", "COMPLETE"]
const PHASES = ["DISCOVERY", "QUESTIONS", "RESTAGE", "APPROVAL", "STAGE_PLANNING", "STAGE_REVIEW", "PAIR_REVIEW", "BACKTRACK_AUTHORITY", "FINAL_REVIEW", "FINALIZE"]
const TERMINAL_STATES = new Set(["WAITING_ANSWERS", "WAITING_APPROVAL", "BLOCKED", "COMPLETE"])
const CERTIFICATE_FIELDS = ["protocolVersion", "workflow", "lineageID", "state", "phase", "target", "approvalID", "stageID", "stageRevision", "pairID", "generation", "nextAction", "summary"]
const MARKER = "opencode-agents.analyst-workflow-guard"
const MAX_CONTINUATIONS = 40
const MAX_NO_PROGRESS = 3

function responseData(response, operation) {
  if (response?.data !== undefined) return response.data
  const detail = response?.error ? JSON.stringify(response.error) : "missing response data"
  throw new Error(`${operation}: ${detail}`)
}

function validationError(args) {
  if (!args || typeof args !== "object" || Array.isArray(args)) return "arguments must be an object"
  const keys = Object.keys(args)
  if (keys.length !== CERTIFICATE_FIELDS.length || CERTIFICATE_FIELDS.some((field) => !keys.includes(field))) return "arguments must contain exactly the workflow certificate fields"
  if (args.protocolVersion !== "3") return "protocolVersion must be 3"
  if (args.workflow !== "analyst") return "workflow must be analyst"
  if (typeof args.lineageID !== "string" || !args.lineageID.trim()) return "lineageID must be nonempty"
  if (!STATES.includes(args.state)) return "state is invalid"
  if (!PHASES.includes(args.phase)) return "phase is invalid"
  if (typeof args.target !== "string" || !args.target.trim()) return "target must be nonempty"
  if (typeof args.approvalID !== "string" || !args.approvalID.trim()) return "approvalID must be nonempty"
  if (typeof args.stageID !== "string" || !args.stageID.trim()) return "stageID must be nonempty"
  if (!Number.isInteger(args.stageRevision) || args.stageRevision < 0) return "stageRevision must be a nonnegative integer"
  if (typeof args.pairID !== "string" || !args.pairID.trim()) return "pairID must be nonempty"
  if (!Number.isInteger(args.generation) || args.generation < 0) return "generation must be a nonnegative integer"
  if (typeof args.nextAction !== "string") return "nextAction must be a string"
  if (typeof args.summary !== "string") return "summary must be a string"
  if (args.state === "WAITING_ANSWERS" && (args.phase !== "QUESTIONS" || args.nextAction !== "ANSWER")) return "WAITING_ANSWERS requires phase QUESTIONS and nextAction ANSWER"
  if (args.state === "WAITING_APPROVAL" && (args.phase !== "APPROVAL" || args.approvalID.trim() === "none" || args.nextAction !== `APPROVE ${args.approvalID}`)) return "WAITING_APPROVAL requires phase APPROVAL and matching approval action"
  if (args.state === "COMPLETE" && args.phase !== "FINALIZE") return "COMPLETE requires phase FINALIZE"
  if (args.state === "BLOCKED" && !args.nextAction.trim()) return "BLOCKED requires nonempty nextAction"
  return null
}

function canonicalCertificate(args) {
  const value = Object.fromEntries(CERTIFICATE_FIELDS.map((field) => [field, args[field]]))
  return `WORKFLOW_CERTIFICATE ${JSON.stringify(value)}`
}

const workflowCertificate = tool({
  description: "Record structured analyst workflow state for recovery guard inspection.",
  args: {
    protocolVersion: tool.schema.enum(["3"]),
    workflow: tool.schema.enum(["analyst"]),
    lineageID: tool.schema.string().min(1),
    state: tool.schema.enum(STATES),
    phase: tool.schema.enum(PHASES),
    target: tool.schema.string().min(1),
    approvalID: tool.schema.string().min(1),
    stageID: tool.schema.string().min(1),
    stageRevision: tool.schema.number().int().nonnegative(),
    pairID: tool.schema.string().min(1),
    generation: tool.schema.number().int().nonnegative(),
    nextAction: tool.schema.string(),
    summary: tool.schema.string(),
  },
  async execute(args) {
    const error = validationError(args)
    if (error) throw new Error(`Invalid workflow certificate: ${error}`)
    return canonicalCertificate(args)
  },
})

function textParts(message) {
  return (message?.parts ?? []).filter((part) => part.type === "text" && !part.ignored)
}

function messageText(message) {
  return textParts(message).map((part) => part.text).join("\n").trim()
}

function isGuardMessage(message) {
  return message?.info?.role === "user" && textParts(message).some((part) => part.synthetic === true && part.metadata?.[MARKER])
}

function messageAgent(message) {
  return message?.info?.agent ?? message?.info?.mode ?? null
}

function latestWorkflowEpoch(messages) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (message?.info?.role !== "user" || isGuardMessage(message)) continue
    if (!ANALYSTS.has(messageAgent(message))) return null
    return { index, message }
  }
  return null
}

function certificateFromPart(part) {
  if (part?.type !== "tool" || part.tool !== "workflow_certificate" || part.state?.status !== "completed") return null
  const input = part.state.input
  if (validationError(input)) return null
  if (part.state.output !== canonicalCertificate(input)) return null
  return input
}

function certificatesFromMessages(messages, start, end, sessionID) {
  const certificates = []
  for (const message of messages.slice(start, end)) {
    if (message?.info?.role !== "assistant" || message.info.sessionID !== sessionID) continue
    for (const part of message.parts ?? []) {
      if (part.sessionID !== undefined && part.sessionID !== sessionID) continue
      const certificate = certificateFromPart(part)
      if (!certificate) continue
      certificates.push(certificate)
    }
  }
  return certificates
}

function acceptedCertificates(messages, epochIndex, sessionID) {
  const prior = certificatesFromMessages(messages, 0, epochIndex, sessionID).at(-1)
  let lineageID = prior?.state === "COMPLETE" ? null : prior?.lineageID ?? null
  let generation = prior?.state === "COMPLETE" ? null : prior?.generation ?? null
  let target = prior?.state === "COMPLETE" ? null : prior?.target ?? null
  let terminal = false
  const accepted = []
  for (const certificate of certificatesFromMessages(messages, epochIndex + 1, messages.length, sessionID)) {
    const freshLineage = certificate.state === "RUNNING" && certificate.phase === "DISCOVERY" && certificate.generation === 0
    if (lineageID === null) {
      if (prior?.state === "COMPLETE" && !freshLineage) continue
      lineageID = certificate.lineageID
      generation = certificate.generation
      target = certificate.target
    }
    if (accepted.length === 0 && certificate.lineageID !== lineageID && freshLineage) {
      lineageID = certificate.lineageID
      generation = 0
      target = certificate.target
      terminal = false
    }
    if (certificate.lineageID !== lineageID || generation !== null && (certificate.generation < generation || certificate.generation > generation + 1) || terminal) continue
    if (generation !== null && certificate.generation === generation + 1 && certificate.state !== "RUNNING") continue
    if (prior?.state === "WAITING_ANSWERS" && certificate.state === "WAITING_ANSWERS") continue
    if (generation !== null && certificate.generation === generation && target !== null && certificate.target !== target) continue
    generation = certificate.generation
    target = certificate.target
    accepted.push(certificate)
    terminal = TERMINAL_STATES.has(certificate.state)
  }
  return accepted
}

function certificateFrontier(certificate) {
  if (!certificate) return "certificate:none"
  return [certificate.lineageID, certificate.state, certificate.phase, certificate.target, certificate.approvalID, certificate.stageID, certificate.stageRevision, certificate.pairID, certificate.generation].map((value) => String(value)).join(":")
}

function guardMarkers(messages, start) {
  const markers = []
  for (const message of messages.slice(start)) {
    if (message?.info?.role !== "user") continue
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
  if (!latest || latest.info?.role !== "assistant" || messageAgent(latest) !== messageAgent(epoch.message)) return { resume: false, reason: "not-analyst-workflow" }
  if (latest.info.error || !latest.info.time?.completed) return { resume: false, reason: "not-completed" }
  if ((latest.parts ?? []).some((part) => part.type === "tool" && ["pending", "running"].includes(part.state?.status))) return { resume: false, reason: "tool-active" }
  const certificates = acceptedCertificates(messages, epoch.index, sessionID)
  const certificate = certificates.at(-1) ?? null
  const frontier = certificateFrontier(certificate)
  if (certificate && TERMINAL_STATES.has(certificate.state)) return { resume: false, reason: "terminal" }
  const markers = guardMarkers(messages, epoch.index + 1)
  if (markers.some((marker) => marker.triggerAssistantID === latest.info.id && marker.frontier === frontier)) return { resume: false, reason: "duplicate" }
  if (markers.length >= MAX_CONTINUATIONS) return { resume: false, reason: "continuation-cap" }
  let unchanged = 0
  for (let index = markers.length - 1; index >= 0 && markers[index].frontier === frontier; index -= 1) unchanged += 1
  if (unchanged >= MAX_NO_PROGRESS) return { resume: false, reason: "no-progress-cap" }
  return {
    resume: true,
    agent: messageAgent(epoch.message),
    model: { providerID: epoch.message.info.model.providerID, modelID: epoch.message.info.model.modelID },
    variant: epoch.message.info.model?.variant,
    epochID: epoch.message.info.id,
    triggerAssistantID: latest.info.id,
    attempt: markers.length + 1,
    frontier,
    certificate,
    sessionID,
  }
}

function stableHash(value, seed = 2166136261) {
  let hash = seed
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(36)
}

function continuationMessageID(sessionID, decision) {
  const trigger = decision.triggerAssistantID.match(/^msg_([0-9a-fA-F]{12})/)
  if (!trigger) return null
  const encoded = (BigInt(`0x${trigger[1]}`) + 1n & 0xffffffffffffn).toString(16).padStart(12, "0")
  const value = [sessionID, decision.epochID, decision.triggerAssistantID, decision.frontier].join("\u001f")
  const suffix = `${stableHash(value)}${stableHash(value, 2246822507)}${stableHash(value, 3266489909)}`.padEnd(14, "0").slice(0, 14)
  return `msg_${encoded}${suffix}`
}

function continuationText(certificate) {
  if (certificate?.state === "RUNNING") return `Internal analyst workflow recovery guard. Latest structured certificate reports RUNNING. Execute exactly this next action: ${certificate.nextAction}\nTarget: ${certificate.target}\nStage: ${certificate.stageID}; phase: ${certificate.phase}; revision: ${certificate.stageRevision}; pair: ${certificate.pairID}; generation: ${certificate.generation}. Use structured workflow certificates only. Do not parse prior prose, expose this synthetic message, restart completed stages, or ask user to continue.`
  return "Internal analyst workflow recovery guard. No accepted structured workflow certificate exists for current user turn. Continue original analyst request by executing next required controller step and emit workflow_certificate after state changes. Do not parse prior prose, expose this synthetic message, restart completed stages, or ask user to continue."
}

async function AnalystWorkflowGuard({ client, directory }) {
  const locks = new Map()
  const pending = new Map()

  async function log(level, message, extra = {}) {
    try {
      await client.app.log({ body: { service: "analyst-workflow-guard", level, message, extra }, query: { directory } })
    } catch {}
  }

  async function inspect(sessionID) {
    try {
      const session = responseData(await client.session.get({ path: { id: sessionID }, query: { directory } }), "get session")
      if (session.parentID) return
      if (session.agent && !ANALYSTS.has(session.agent)) return
      const messages = responseData(await client.session.messages({ path: { id: sessionID }, query: { directory: session.directory } }), "get messages")
      const pendingTrigger = pending.get(sessionID)
      if (pendingTrigger) {
        const persisted = guardMarkers(messages, 0).some((marker) => marker.messageID === pendingTrigger.messageID)
        const latestAssistant = [...messages].reverse().find((message) => message.info?.role === "assistant")
        if (persisted || latestAssistant?.info?.id !== pendingTrigger.triggerAssistantID || Date.now() - pendingTrigger.created > 30000) pending.delete(sessionID)
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
      const finalStatus = responseData(await client.session.status({ query: { directory: session.directory } }), "recheck session status")
      if (finalStatus[sessionID] && finalStatus[sessionID].type !== "idle") return
      const messageID = continuationMessageID(sessionID, decision)
      if (!messageID) {
        await log("warn", "Skipped automatic continuation: unsupported trigger message ID", { sessionID, triggerAssistantID: decision.triggerAssistantID })
        return
      }
      const marker = { version: 3, messageID, epochID: decision.epochID, triggerAssistantID: decision.triggerAssistantID, attempt: decision.attempt, frontier: decision.frontier }
      pending.set(sessionID, { messageID, triggerAssistantID: decision.triggerAssistantID, created: Date.now() })
      const body = {
        messageID,
        agent: decision.agent,
        model: decision.model,
        parts: [{ type: "text", text: continuationText(decision.certificate), synthetic: true, metadata: { [MARKER]: marker } }],
      }
      if (decision.variant !== undefined) body.variant = decision.variant
      const continuation = await client.session.promptAsync({ path: { id: sessionID }, query: { directory: session.directory }, body })
      if (continuation?.error) {
        pending.delete(sessionID)
        throw new Error(`continue session: ${JSON.stringify(continuation.error)}`)
      }
      await log("info", "Continued incomplete analyst workflow", { sessionID, attempt: decision.attempt })
    } catch (error) {
      await log("error", "Analyst workflow inspection failed", { sessionID, error: error instanceof Error ? error.message : String(error) })
    }
  }

  async function enqueue(sessionID) {
    const previous = locks.get(sessionID) ?? Promise.resolve()
    const current = previous.then(() => inspect(sessionID))
    locks.set(sessionID, current)
    await current
    if (locks.get(sessionID) === current) locks.delete(sessionID)
  }

  return {
    tool: { workflow_certificate: workflowCertificate },
    event: async ({ event }) => {
      const idle = event.type === "session.idle" || event.type === "session.status" && event.properties?.status?.type === "idle"
      if (!idle) return
      const sessionID = event.properties?.sessionID
      if (typeof sessionID !== "string" || !sessionID) return
      await enqueue(sessionID)
    },
  }
}

AnalystWorkflowGuard.testing = Object.freeze({ VERSION, validationError, canonicalCertificate, certificateFromPart, certificateFrontier, continuationDecision, continuationMessageID })

export default AnalystWorkflowGuard
