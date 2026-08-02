import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"

const source = await readFile(new URL("../plugins/analyst-workflow-guard.js", import.meta.url), "utf8")
const { default: AnalystWorkflowGuard } = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`)

const SESSION = "session-parent"
const PATH = "1_orchestrator/request/tasks/01-work.md"
const FULL_PATH = `/repo/${PATH}`

function text(id, value, options = {}) {
  return { id, sessionID: SESSION, messageID: options.messageID ?? id, type: "text", text: value, ...options }
}

function user(id, agent = "orchestrator-analyst", value = "Create plan", options = {}) {
  return { info: { id, sessionID: SESSION, role: "user", time: { created: 1 }, agent, model: { providerID: "openai", modelID: "gpt-5.6-terra" } }, parts: [text(`${id}-text`, value, { messageID: id, ...options })] }
}

function assistant(id, value, parts = []) {
  return { info: { id, sessionID: SESSION, role: "assistant", parentID: "user", mode: "orchestrator-analyst", time: { created: 2, completed: 3 }, modelID: "gpt-5.6-terra", providerID: "openai" }, parts: [text(`${id}-text`, value, { messageID: id }), ...parts] }
}

function task(id, role, result) {
  const child = `${id}-child`
  return { id, sessionID: SESSION, messageID: "assistant", type: "tool", callID: `${id}-call`, tool: "task", state: { status: "completed", input: { description: "work", prompt: "work", subagent_type: role }, output: `<task id="${child}" state="completed">\n<task_result>\n${result}\n</task_result>\n</task>`, title: "work", metadata: { parentSessionId: SESSION, sessionId: child }, time: { start: 1, end: 2 } } }
}

function review(label) {
  return `${label}: PASS\nReview mode: NORMAL\nChecked tasks: ${FULL_PATH}\nReady for finalize: ${FULL_PATH}\nFindings: none\nБлокер: none`
}

function finalize() {
  return `PLANNING: PASS\nMODE: FINALIZE\nEvidence: NOT_APPLICABLE\nЗадачи: ${FULL_PATH}\nIssue journal: none\nFindings applied: NOT_APPLICABLE\nИзменено: ${FULL_PATH}\nПредположения: none\nRejection: none\nБлокер: none`
}

function ready() {
  return `Готово\n\nИтог: READY\nЗадачи: ${FULL_PATH}\nРиски и ограничения: none\nБлокер: none`
}

test("incomplete analyst turn resumes", () => {
  const decision = AnalystWorkflowGuard.testing.continuationDecision([user("user"), assistant("assistant", "Стоп\n\nИтог: BLOCKED\nЗадачи: none\nРиски и ограничения: none\nБлокер: repeat request")], SESSION)
  assert.equal(decision.resume, true)
  assert.equal(decision.agent, "orchestrator-analyst")
})

test("standard reviewed finalize is terminal", () => {
  const messages = [user("user"), assistant("assistant", ready(), [task("terra", "orchestrator-plan-reviewer", review("PLAN_REVIEW")), task("ultra", "orchestrator-plan-ultra-reviewer", review("ULTRA_PLAN_REVIEW")), task("final", "orchestrator-task-planner", finalize())])]
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "terminal" })
})

test("single-model reviewed finalize is terminal", () => {
  const messages = [user("user", "orchestrator-analyst-single-model"), assistant("assistant", ready(), [task("review", "orchestrator-plan-reviewer", review("PLAN_REVIEW")), task("final", "orchestrator-task-planner", finalize())])]
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "terminal" })
})

test("finalize without required reviews resumes", () => {
  const messages = [user("user"), assistant("assistant", ready(), [task("final", "orchestrator-task-planner", finalize())])]
  assert.equal(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION).resume, true)
})

test("task path outside final tasks field cannot certify ready", () => {
  const response = `Итог: READY\nЗадачи: none\nРиски и ограничения: generated ${FULL_PATH}\nБлокер: none`
  const messages = [user("user"), assistant("assistant", response, [task("terra", "orchestrator-plan-reviewer", review("PLAN_REVIEW")), task("ultra", "orchestrator-plan-ultra-reviewer", review("ULTRA_PLAN_REVIEW")), task("final", "orchestrator-task-planner", finalize())])]
  assert.equal(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION).resume, true)
})

test("certified create blocker is terminal", () => {
  const blocked = "PLANNING: BLOCKED\nMODE: CREATE\nEvidence: BLOCKED\nЗадачи: none\nIssue journal: none\nFindings applied: NOT_APPLICABLE\nИзменено: none\nПредположения: none\nRejection: none\nБлокер: grant repository access"
  const response = "Итог: BLOCKED\nЗадачи: none\nРиски и ограничения: none\nБлокер: grant repository access"
  const messages = [user("user"), assistant("assistant", response, [task("blocked", "orchestrator-task-planner", blocked)])]
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "terminal" })
})

test("planner block requires originating blocked review", () => {
  const blockedReview = `PLAN_REVIEW: BLOCKED\nReview mode: NORMAL\nChecked tasks: ${FULL_PATH}\nReady for finalize: none\nFindings: none\nБлокер: choose public API behavior`
  const blockedPlan = `PLANNING: PASS\nMODE: BLOCK\nEvidence: NOT_APPLICABLE\nЗадачи: ${FULL_PATH}\nIssue journal: none\nFindings applied: NOT_APPLICABLE\nИзменено: none\nПредположения: none\nRejection: none\nБлокер: choose public API behavior`
  const response = `Стоп\n\nИтог: BLOCKED\nЗадачи: ${FULL_PATH}\nРиски и ограничения: none\nБлокер: choose public API behavior`
  const certified = [user("user"), assistant("assistant", response, [task("review", "orchestrator-plan-reviewer", blockedReview), task("blocked", "orchestrator-task-planner", blockedPlan)])]
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(certified, SESSION), { resume: false, reason: "terminal" })
  const uncertified = [user("user"), assistant("assistant", response, [task("blocked", "orchestrator-task-planner", blockedPlan)])]
  assert.equal(AnalystWorkflowGuard.testing.continuationDecision(uncertified, SESSION).resume, true)
})

test("synthetic marker deduplicates idle event", () => {
  const marker = { "opencode-agents.analyst-workflow-guard": { triggerAssistantID: "assistant", frontier: "no-workflow-task" } }
  const messages = [user("user"), user("guard", "orchestrator-analyst", "continue", { synthetic: true, metadata: marker }), assistant("assistant", "stopped")]
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "duplicate" })
})

test("bounded no-progress markers stop continuation loop", () => {
  const messages = [user("user")]
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const marker = { "opencode-agents.analyst-workflow-guard": { triggerAssistantID: `prior-${attempt}`, frontier: "no-workflow-task" } }
    messages.push(user(`guard-${attempt}`, "orchestrator-analyst", "continue", { synthetic: true, metadata: marker }))
    messages.push(assistant(`assistant-${attempt}`, "stopped"))
  }
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "no-progress-cap" })
})

test("explicit cancellation is not resumed", () => {
  for (const value of ["Остановить планирование", "Пожалуйста, не продолжай", "Please stop", "Don't continue", "Хватит", "I changed my mind, stop planning", "Could you stop?", "Can you stop?", "Actually, don't continue"]) {
    const messages = [user("user", "orchestrator-analyst", value), assistant("assistant", "stopped")]
    assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "not-analyst-workflow" })
  }
})

test("new task IDs do not bypass semantic no-progress cap", () => {
  const repeated = "PLANNING: REJECTED\nMODE: REVISE\nEvidence: NOT_APPLICABLE\nЗадачи: none\nIssue journal: none\nFindings applied: NOT_APPLICABLE\nИзменено: none\nПредположения: none\nRejection: malformed\nБлокер: none"
  const messages = [user("user"), assistant("initial", "stopped", [task("task-0", "orchestrator-task-planner", repeated)])]
  for (let attempt = 1; attempt <= 5; attempt += 1) {
    const current = AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION)
    const marker = { "opencode-agents.analyst-workflow-guard": { triggerAssistantID: current.triggerAssistantID, frontier: current.frontier } }
    messages.push(user(`guard-${attempt}`, "orchestrator-analyst", "continue", { synthetic: true, metadata: marker }))
    messages.push(assistant(`assistant-${attempt}`, "stopped", [task(`task-${attempt}`, "orchestrator-task-planner", repeated)]))
  }
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "no-progress-cap" })
})

test("distinct reviewer findings count as semantic progress", () => {
  const finding = (signature) => `PLAN_REVIEW: REVISE\nReview mode: NORMAL\nChecked tasks: ${FULL_PATH}\nReady for finalize: none\nFindings:\n1.\n  Signature: ${signature}\n  Occurrence: 1\n  Progress: NOT_APPLICABLE\n  Affected tasks: ${FULL_PATH}\n  Finding: defect ${signature}\n  Required correction: fix ${signature}\nБлокер: none`
  const initial = [user("user"), assistant("assistant-1", "stopped", [task("review-1", "orchestrator-plan-reviewer", finding("first"))])]
  const first = AnalystWorkflowGuard.testing.continuationDecision(initial, SESSION)
  const marker = { "opencode-agents.analyst-workflow-guard": { triggerAssistantID: "assistant-1", frontier: first.frontier } }
  const messages = [...initial, user("guard", "orchestrator-analyst", "continue", { synthetic: true, metadata: marker }), assistant("assistant-2", "stopped", [task("review-2", "orchestrator-plan-reviewer", finding("second"))])]
  const decision = AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION)
  assert.equal(decision.resume, true)
  assert.notEqual(decision.frontier, first.frontier)
})

test("plugin ignores child sessions", async () => {
  let messagesCalled = false
  const client = {
    app: { log: async () => ({ data: true }) },
    session: {
      get: async () => ({ data: { id: SESSION, directory: "/repo", parentID: "parent" } }),
      messages: async () => { messagesCalled = true; return { data: [] } },
    },
  }
  const hooks = await AnalystWorkflowGuard({ client, directory: "/repo" })
  await hooks.event({ event: { type: "session.idle", properties: { sessionID: SESSION } } })
  assert.equal(messagesCalled, false)
})

test("plugin treats absent status entry as idle and continues", async () => {
  const messages = [user("user"), assistant("assistant", "stopped")]
  let prompt
  const client = {
    app: { log: async () => ({ data: true }) },
    session: {
      get: async () => ({ data: { id: SESSION, directory: "/repo" } }),
      messages: async () => ({ data: messages }),
      status: async () => ({ data: {} }),
      promptAsync: async (value) => { prompt = value; return { data: undefined } },
    },
  }
  const hooks = await AnalystWorkflowGuard({ client, directory: "/repo" })
  await hooks.event({ event: { type: "session.idle", properties: { sessionID: SESSION } } })
  assert.equal(prompt.path.id, SESSION)
  assert.equal(prompt.body.agent, "orchestrator-analyst")
  assert.deepEqual(prompt.body.model, { providerID: "openai", modelID: "gpt-5.6-terra" })
  assert.equal(prompt.body.parts[0].synthetic, true)
  assert.equal(prompt.body.parts[0].metadata["opencode-agents.analyst-workflow-guard"].triggerAssistantID, "assistant")
})

test("plugin does not continue busy session", async () => {
  const messages = [user("user"), assistant("assistant", "stopped")]
  let prompts = 0
  const client = {
    app: { log: async () => ({ data: true }) },
    session: {
      get: async () => ({ data: { id: SESSION, directory: "/repo" } }),
      messages: async () => ({ data: messages }),
      status: async () => ({ data: { [SESSION]: { type: "busy" } } }),
      promptAsync: async () => { prompts += 1; return { data: undefined } },
    },
  }
  const hooks = await AnalystWorkflowGuard({ client, directory: "/repo" })
  await hooks.event({ event: { type: "session.idle", properties: { sessionID: SESSION } } })
  assert.equal(prompts, 0)
})

test("pending continuation suppresses duplicate idle before marker persistence", async () => {
  const messages = [user("user"), assistant("assistant", "stopped")]
  let prompts = 0
  const client = {
    app: { log: async () => ({ data: true }) },
    session: {
      get: async () => ({ data: { id: SESSION, directory: "/repo" } }),
      messages: async () => ({ data: messages }),
      status: async () => ({ data: { [SESSION]: { type: "idle" } } }),
      promptAsync: async () => { prompts += 1; return { data: undefined } },
    },
  }
  const hooks = await AnalystWorkflowGuard({ client, directory: "/repo" })
  await hooks.event({ event: { type: "session.idle", properties: { sessionID: SESSION } } })
  await hooks.event({ event: { type: "session.idle", properties: { sessionID: SESSION } } })
  assert.equal(prompts, 1)
})
