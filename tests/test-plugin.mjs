import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"

const rawSource = await readFile(new URL("../plugins/analyst-workflow-guard.js", import.meta.url), "utf8")
const stub = `
const chain = { int() { return this }, nonnegative() { return this }, min() { return this } }
const tool = Object.assign((definition) => definition, { schema: { number: () => Object.create(chain), string: () => Object.create(chain), enum: (values) => ({ values }) } })
`
const source = rawSource.replace('import { tool } from "@opencode-ai/plugin"', stub)
const { default: AnalystWorkflowGuard } = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`)

const SESSION = "session-parent"
const AGENT = "orchestrator-analyst"
const MARKER = "opencode-agents.analyst-workflow-guard"
const messageIDs = new Map()
let messageSequence = 1n

function messageID(value) {
  if (value.startsWith("msg_")) return value
  if (!messageIDs.has(value)) {
    const encoded = messageSequence.toString(16).padStart(12, "0")
    messageSequence += 1n
    messageIDs.set(value, `msg_${encoded}${"a".repeat(14)}`)
  }
  return messageIDs.get(value)
}

function text(id, value, options = {}) {
  return { id, sessionID: SESSION, messageID: options.messageID ?? id, type: "text", text: value, ...options }
}

function user(id, options = {}) {
  const agent = options.agent ?? AGENT
  const actualID = messageID(id)
  return {
    info: { id: actualID, sessionID: SESSION, role: "user", time: { created: 1 }, agent, model: options.model ?? { providerID: "openai", modelID: "gpt-5.6-terra", variant: options.variant } },
    parts: options.fileOnly ? [{ id: `${id}-file`, type: "file", filename: "request.txt" }] : [text(`${id}-text`, options.value ?? "Create plan", { messageID: actualID, synthetic: options.synthetic, metadata: options.metadata })],
  }
}

function assistant(id, parts = [], options = {}) {
  const info = { id: messageID(id), sessionID: SESSION, role: "assistant", mode: options.agent ?? AGENT, time: { created: 2, completed: 3 } }
  if (options.error) info.error = options.error
  if (options.incomplete) delete info.time.completed
  return { info, parts: [text(`${id}-text`, options.value ?? "prose is irrelevant", { messageID: id }), ...parts] }
}

function certificate(overrides = {}) {
  return {
    protocolVersion: "3",
    workflow: "analyst",
    lineageID: "lineage-1",
    state: "RUNNING",
    phase: "STAGE_PLANNING",
    target: "1_orchestrator/request/",
    approvalID: "none",
    stageID: "planner",
    stageRevision: 0,
    pairID: "pair-1",
    generation: 0,
    nextAction: "dispatch planner",
    summary: "planner needed",
    ...overrides,
  }
}

function certPart(id, args, options = {}) {
  const output = options.output ?? AnalystWorkflowGuard.testing.canonicalCertificate(args)
  return { id, sessionID: SESSION, messageID: "assistant", type: "tool", tool: "workflow_certificate", state: { status: options.status ?? "completed", input: args, output } }
}

function questionPart(id, status = "running") {
  return { id, sessionID: SESSION, messageID: "assistant", type: "tool", tool: "question", state: { status, input: { questions: [] }, output: "" } }
}

function markerUser(id, triggerAssistantID, frontier, extra = {}) {
  const marker = { [MARKER]: { triggerAssistantID: messageID(triggerAssistantID), frontier, messageID: messageID(`marker-${id}`), ...extra } }
  return user(id, { value: "continue", synthetic: true, metadata: marker })
}

function decisionWith(args, options = {}) {
  return AnalystWorkflowGuard.testing.continuationDecision([user("user", options.user), assistant("assistant", args ? [certPart("cert", args)] : [], options.assistant)], SESSION)
}

test("plugin imports tool and exposes exact certificate args", async () => {
  assert.match(rawSource, /^import \{ tool \} from "@opencode-ai\/plugin"/)
  const hooks = await AnalystWorkflowGuard({ client: minimalClient([]), directory: "/repo" })
  assert.deepEqual(Object.keys(hooks.tool), ["workflow_certificate"])
  assert.deepEqual(Object.keys(hooks.tool.workflow_certificate.args), ["protocolVersion", "workflow", "lineageID", "state", "phase", "target", "approvalID", "stageID", "stageRevision", "pairID", "generation", "nextAction", "summary"])
})

test("certificate execute returns canonical prefixed JSON", async () => {
  const hooks = await AnalystWorkflowGuard({ client: minimalClient([]), directory: "/repo" })
  const args = certificate()
  assert.equal(await hooks.tool.workflow_certificate.execute(args), AnalystWorkflowGuard.testing.canonicalCertificate(args))
})

test("certificate cross-field validation rejects invalid combinations", async () => {
  const hooks = await AnalystWorkflowGuard({ client: minimalClient([]), directory: "/repo" })
  const execute = hooks.tool.workflow_certificate.execute
  await assert.rejects(execute(certificate({ protocolVersion: "2" })), /protocolVersion must be 3/)
  await assert.rejects(execute(certificate({ workflow: "executor" })), /workflow must be analyst/)
  await assert.rejects(execute(certificate({ state: "WAITING_ANSWERS", phase: "QUESTIONS", nextAction: "WAIT" })), /nextAction ANSWER/)
  await assert.rejects(execute(certificate({ state: "WAITING_APPROVAL", phase: "APPROVAL", approvalID: "A7", nextAction: "APPROVE A8" })), /matching approval action/)
  await assert.rejects(execute(certificate({ state: "COMPLETE", phase: "DISCOVERY" })), /phase FINALIZE/)
  await assert.rejects(execute(certificate({ state: "BLOCKED", nextAction: "" })), /nonempty nextAction/)
  assert.equal(await execute(certificate({ state: "RUNNING", phase: "FINALIZE" })), AnalystWorkflowGuard.testing.canonicalCertificate(certificate({ state: "RUNNING", phase: "FINALIZE" })))
  await assert.rejects(execute(certificate({ generation: -1 })), /nonnegative integer/)
  await assert.rejects(execute({ ...certificate(), extra: true }), /exactly the workflow certificate fields/)
})

test("terminal waiting states stop recovery", () => {
  const answers = certificate({ state: "WAITING_ANSWERS", phase: "QUESTIONS", nextAction: "ANSWER" })
  const approval = certificate({ state: "WAITING_APPROVAL", phase: "APPROVAL", approvalID: "approval-4", nextAction: "APPROVE approval-4" })
  assert.deepEqual(decisionWith(answers), { resume: false, reason: "terminal" })
  assert.deepEqual(decisionWith(approval), { resume: false, reason: "terminal" })
})

test("COMPLETE and BLOCKED stop recovery", () => {
  assert.deepEqual(decisionWith(certificate({ state: "COMPLETE", phase: "FINALIZE", nextAction: "none" })), { resume: false, reason: "terminal" })
  assert.deepEqual(decisionWith(certificate({ state: "BLOCKED", nextAction: "grant repository access" })), { resume: false, reason: "terminal" })
})

test("certificate from prior user turn cannot terminate or resume current uncertified turn", () => {
  for (const stale of [certificate({ state: "WAITING_ANSWERS", phase: "QUESTIONS", nextAction: "ANSWER" }), certificate({ state: "BLOCKED", nextAction: "grant access" })]) {
    const messages = [user("request"), assistant("waiting", [certPart("wait", stale)]), user("answer", { value: "explain option B" }), assistant("reply")]
    assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "uncertified" })
  }
})

test("new certificate after user answer can stop recovery", () => {
  const waiting = certificate({ state: "WAITING_ANSWERS", phase: "QUESTIONS", nextAction: "ANSWER" })
  const blocked = certificate({ state: "BLOCKED", nextAction: "grant access" })
  const messages = [user("request"), assistant("waiting", [certPart("wait", waiting)]), user("answer", { value: "Q1: permanent" }), assistant("reply", [certPart("blocked", blocked)])]
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "terminal" })
})

test("new-turn terminal certificate from wrong lineage is ignored", () => {
  const waiting = certificate({ state: "WAITING_ANSWERS", phase: "QUESTIONS", nextAction: "ANSWER" })
  const forged = certificate({ lineageID: "lineage-2", state: "COMPLETE", phase: "FINALIZE" })
  const messages = [user("request"), assistant("waiting", [certPart("wait", waiting)]), user("answer", { value: "Q1: permanent" }), assistant("reply", [certPart("forged", forged)])]
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "uncertified" })
})

test("new discovery certificate starts a new lineage", () => {
  const waiting = certificate({ state: "WAITING_APPROVAL", phase: "APPROVAL", approvalID: "old", nextAction: "APPROVE old" })
  const discovery = certificate({ lineageID: "lineage-2", state: "RUNNING", phase: "DISCOVERY", generation: 0, nextAction: "review questions" })
  const messages = [user("request"), assistant("waiting", [certPart("wait", waiting)]), user("new-request", { value: "Plan another feature" }), assistant("reply", [certPart("discovery", discovery)])]
  const decision = AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION)
  assert.equal(decision.resume, true)
  assert.equal(decision.certificate.lineageID, "lineage-2")
})

test("stale generation terminal certificate cannot stop recovery", () => {
  const current = certificate({ generation: 2, phase: "PAIR_REVIEW", nextAction: "review next pair" })
  const stale = certificate({ generation: 1, state: "COMPLETE", phase: "FINALIZE", nextAction: "none" })
  const decision = AnalystWorkflowGuard.testing.continuationDecision([user("user"), assistant("assistant", [certPart("current", current), certPart("stale", stale)])], SESSION)
  assert.equal(decision.resume, true)
  assert.equal(decision.certificate.generation, 2)
})

test("future generation jump cannot forge terminal state", () => {
  const current = certificate({ generation: 2, phase: "PAIR_REVIEW", nextAction: "review next pair" })
  const future = certificate({ generation: 999, state: "COMPLETE", phase: "FINALIZE", nextAction: "none" })
  const decision = AnalystWorkflowGuard.testing.continuationDecision([user("future-user"), assistant("future-assistant", [certPart("current", current), certPart("future", future)])], SESSION)
  assert.equal(decision.resume, true)
  assert.equal(decision.certificate.generation, 2)
})

test("current turn may remain waiting while user asks for question explanation", () => {
  const waiting = certificate({ state: "WAITING_ANSWERS", phase: "QUESTIONS", nextAction: "ANSWER" })
  const messages = [user("question-request"), assistant("question-wait", [certPart("wait", waiting)]), user("question-explain", { value: "Explain option B" }), assistant("question-repeat", [certPart("repeat", waiting)])]
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "terminal" })
})

test("unsupported trigger ID does not create maximal fallback ID", () => {
  const decision = { epochID: "msg_000000000001aaaaaaaaaaaaaa", triggerAssistantID: "legacy-id", frontier: "state" }
  assert.equal(AnalystWorkflowGuard.testing.continuationMessageID(SESSION, decision), null)
})

test("terminal certificate cannot be reopened in same turn", () => {
  const complete = certificate({ state: "COMPLETE", phase: "FINALIZE", nextAction: "none" })
  const running = certificate({ phase: "DISCOVERY", nextAction: "restart" })
  const messages = [user("user"), assistant("assistant", [certPart("complete", complete), certPart("running", running)])]
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "terminal" })
})

test("only RUNNING certificate resumes", () => {
  assert.deepEqual(decisionWith(null), { resume: false, reason: "uncertified" })
  const decision = decisionWith(certificate())
  assert.equal(decision.resume, true)
  assert.equal(decision.certificate.nextAction, "dispatch planner")
})

test("malformed output and mismatched lineage do not forge terminal state", () => {
  const running = certificate()
  const forged = certificate({ lineageID: "lineage-2", state: "COMPLETE", phase: "FINALIZE" })
  const parts = [certPart("run", running), certPart("forged", forged), certPart("bad", certificate({ state: "COMPLETE", phase: "FINALIZE" }), { output: "WORKFLOW_CERTIFICATE {}" })]
  const decision = AnalystWorkflowGuard.testing.continuationDecision([user("user"), assistant("assistant", parts)], SESSION)
  assert.equal(decision.resume, true)
  assert.equal(decision.certificate.state, "RUNNING")
})

test("certificate from child message or child part is ignored", () => {
  const complete = certificate({ state: "COMPLETE", phase: "FINALIZE" })
  const childMessage = assistant("child-message", [certPart("root-part", complete)])
  childMessage.info.sessionID = "child"
  const childPart = certPart("child-part", complete)
  childPart.sessionID = "child"
  const messages = [user("user"), childMessage, assistant("assistant", [childPart])]
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "uncertified" })
})

test("child, nonanalyst, error, active tool, and cancellation are ignored", async () => {
  assert.deepEqual(decisionWith(null, { user: { agent: "build" }, assistant: { agent: "build" } }), { resume: false, reason: "not-analyst-workflow" })
  assert.deepEqual(decisionWith(null, { assistant: { error: { name: "AbortError" } } }), { resume: false, reason: "not-completed" })
  const active = certPart("active", certificate(), { status: "running", output: "" })
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision([user("user"), assistant("assistant", [active])], SESSION), { resume: false, reason: "tool-active" })
  for (const value of ["Please stop", "Не продолжай", "I changed my mind, stop planning"]) assert.deepEqual(decisionWith(null, { user: { value } }), { resume: false, reason: "not-analyst-workflow" })
  let readMessages = false
  const client = minimalClient([], { session: { parentID: "parent" }, onMessages: () => { readMessages = true } })
  const hooks = await AnalystWorkflowGuard({ client, directory: "/repo" })
  await hooks.event({ event: { type: "session.idle", properties: { sessionID: SESSION } } })
  assert.equal(readMessages, false)
})

test("pending native question prevents recovery", () => {
  const messages = [user("question-user"), assistant("question-assistant", [certPart("question-running", certificate({ phase: "QUESTIONS", nextAction: "ASK_REVIEWED_QUESTIONS" })), questionPart("question-tool")])]
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "tool-active" })
})

test("declared nonanalyst root is rejected before messages", async () => {
  let readMessages = false
  const client = minimalClient([], { session: { agent: "build" }, onMessages: () => { readMessages = true } })
  const hooks = await AnalystWorkflowGuard({ client, directory: "/repo" })
  await hooks.event({ event: { type: "session.idle", properties: { sessionID: SESSION } } })
  assert.equal(readMessages, false)
})

test("latest user and completed assistant must use same analyst", () => {
  const messages = [user("user"), assistant("assistant", [], { agent: "orchestrator-analyst-single-model" })]
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "not-analyst-workflow" })
  assert.deepEqual(decisionWith(null, { assistant: { incomplete: true } }), { resume: false, reason: "not-completed" })
})

test("same-frontier no-progress cap is two", () => {
  const running = certificate()
  const frontier = AnalystWorkflowGuard.testing.certificateFrontier(running)
  const messages = [user("user"), assistant("initial", [certPart("cert-0", running)])]
  for (let index = 1; index <= 2; index += 1) {
    messages.push(markerUser(`guard-${index}`, `assistant-${index - 1}`, frontier))
    messages.push(assistant(`assistant-${index}`, [certPart(`cert-${index}`, running)]))
  }
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "no-progress-cap" })
})

test("stage, phase, revision, pair, and generation alter frontier", () => {
  const base = certificate()
  for (const change of [{ stageID: "review" }, { phase: "STAGE_REVIEW" }, { stageRevision: 1 }, { pairID: "pair-2" }, { generation: 1 }]) {
    assert.notEqual(AnalystWorkflowGuard.testing.certificateFrontier(base), AnalystWorkflowGuard.testing.certificateFrontier(certificate(change)))
  }
  const priorFrontier = AnalystWorkflowGuard.testing.certificateFrontier(base)
  const advanced = certificate({ stageRevision: 1 })
  const messages = [user("user"), assistant("first", [certPart("first-cert", base)]), markerUser("guard", "first", priorFrontier), assistant("second", [certPart("second-cert", advanced)])]
  assert.equal(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION).resume, true)
})

test("total continuation cap is two", () => {
  const messages = [user("user")]
  for (let index = 0; index < 2; index += 1) {
    messages.push(markerUser(`guard-${index}`, `assistant-${index}`, `frontier-${index}`))
    messages.push(assistant(`assistant-${index + 1}`, [certPart(`cert-${index}`, certificate({ stageRevision: index + 1 }))]))
  }
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "continuation-cap" })
})

test("continuation cap resets after next explicit user turn", () => {
  const running = certificate()
  const frontier = AnalystWorkflowGuard.testing.certificateFrontier(running)
  const messages = [user("cap-request"), assistant("cap-start", [certPart("cap-start-cert", running)])]
  for (let index = 0; index < 2; index += 1) {
    messages.push(markerUser(`cap-guard-${index}`, `cap-assistant-${index}`, `cap-frontier-${index}`))
    messages.push(assistant(`cap-assistant-${index + 1}`, [certPart(`cap-cert-${index}`, certificate({ stageRevision: index + 1 }))]))
  }
  assert.equal(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION).resume, false)
  messages.push(user("cap-new-user", { value: "Continue approved workflow" }))
  messages.push(assistant("cap-new-assistant", [certPart("cap-new-cert", certificate({ stageRevision: 3, nextAction: "review S02" }))]))
  const decision = AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION)
  assert.equal(decision.resume, true)
  assert.notEqual(decision.frontier, frontier)
})

test("variant, model, deterministic messageID, and RUNNING action are preserved", async () => {
  const running = certificate({ nextAction: "dispatch fresh Sol review" })
  const messages = [user("msg_000000000001aaaaaaaaaaaaaa", { variant: "ultra" }), assistant("msg_000000000002aaaaaaaaaaaaaa", [certPart("cert", running)])]
  const prompts = []
  const client = minimalClient(messages, { onPrompt: (prompt) => prompts.push(prompt) })
  const hooks = await AnalystWorkflowGuard({ client, directory: "/repo" })
  await hooks.event({ event: { type: "session.idle", properties: { sessionID: SESSION } } })
  const body = prompts[0].body
  assert.equal(body.agent, AGENT)
  assert.deepEqual(body.model, { providerID: "openai", modelID: "gpt-5.6-terra" })
  assert.equal(body.variant, "ultra")
  assert.match(body.messageID, /^msg_/)
  assert.match(body.parts[0].text, /Execute exactly this next action: dispatch fresh Sol review/)
  assert.match(body.parts[0].text, /Do not parse prior prose/)
  assert.equal(body.parts[0].metadata[MARKER].messageID, body.messageID)
  const decision = AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION)
  assert.equal(body.messageID, AnalystWorkflowGuard.testing.continuationMessageID(SESSION, decision))
  assert.equal(body.messageID, AnalystWorkflowGuard.testing.continuationMessageID(SESSION, decision))
})

test("dual idle events deduplicate before marker persistence", async () => {
  const messages = [user("user"), assistant("assistant", [certPart("running", certificate())])]
  let prompts = 0
  const client = minimalClient(messages, { onPrompt: () => { prompts += 1 } })
  const hooks = await AnalystWorkflowGuard({ client, directory: "/repo" })
  await Promise.all([
    hooks.event({ event: { type: "session.idle", properties: { sessionID: SESSION } } }),
    hooks.event({ event: { type: "session.status", properties: { sessionID: SESSION, status: { type: "idle" } } } }),
  ])
  assert.equal(prompts, 1)
})

test("non-idle session.status event is ignored", async () => {
  let prompts = 0
  const client = minimalClient([user("user"), assistant("assistant")], { onPrompt: () => { prompts += 1 } })
  const hooks = await AnalystWorkflowGuard({ client, directory: "/repo" })
  await hooks.event({ event: { type: "session.status", properties: { sessionID: SESSION, status: { type: "busy" } } } })
  assert.equal(prompts, 0)
})

test("absent status means idle; busy status suppresses continuation", async () => {
  const messages = [user("user"), assistant("assistant", [certPart("running", certificate())])]
  let idlePrompts = 0
  const idleHooks = await AnalystWorkflowGuard({ client: minimalClient(messages, { status: {}, onPrompt: () => { idlePrompts += 1 } }), directory: "/repo" })
  await idleHooks.event({ event: { type: "session.idle", properties: { sessionID: SESSION } } })
  assert.equal(idlePrompts, 1)
  let busyPrompts = 0
  const busyHooks = await AnalystWorkflowGuard({ client: minimalClient(messages, { status: { [SESSION]: { type: "busy" } }, onPrompt: () => { busyPrompts += 1 } }), directory: "/repo" })
  await busyHooks.event({ event: { type: "session.idle", properties: { sessionID: SESSION } } })
  assert.equal(busyPrompts, 0)
})

test("second status recheck catches newly busy session", async () => {
  const messages = [user("user"), assistant("assistant", [certPart("running", certificate())])]
  let statusCalls = 0
  let prompts = 0
  const client = minimalClient(messages, { onPrompt: () => { prompts += 1 } })
  client.session.status = async () => {
    statusCalls += 1
    return { data: statusCalls === 1 ? {} : { [SESSION]: { type: "busy" } } }
  }
  const hooks = await AnalystWorkflowGuard({ client, directory: "/repo" })
  await hooks.event({ event: { type: "session.idle", properties: { sessionID: SESSION } } })
  assert.equal(statusCalls, 2)
  assert.equal(prompts, 0)
})

function minimalClient(messages, options = {}) {
  return {
    app: { log: async () => ({ data: true }) },
    session: {
      get: async () => ({ data: { id: SESSION, directory: "/repo", ...(options.session ?? {}) } }),
      messages: async () => {
        options.onMessages?.()
        return { data: messages }
      },
      status: async () => ({ data: options.status ?? {} }),
      promptAsync: async (prompt) => {
        options.onPrompt?.(prompt)
        return { data: undefined }
      },
    },
  }
}
