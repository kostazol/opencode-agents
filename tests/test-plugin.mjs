import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import test from "node:test"

const source = await readFile(new URL("../plugins/analyst-workflow-guard.js", import.meta.url), "utf8")
const { default: AnalystWorkflowGuard } = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`)

const SESSION = "session-parent"
const PATH = "1_orchestrator/request/tasks/01-work.md"
const FULL_PATH = PATH
const TARGET = "1_orchestrator/request/"

function text(id, value, options = {}) {
  return { id, sessionID: SESSION, messageID: options.messageID ?? id, type: "text", text: value, ...options }
}

function user(id, agent = "orchestrator-analyst", value = "Create plan", options = {}) {
  return { info: { id, sessionID: SESSION, role: "user", time: { created: 1 }, agent, model: { providerID: "openai", modelID: "gpt-5.6-terra" } }, parts: [text(`${id}-text`, value, { messageID: id, ...options })] }
}

function assistant(id, value, parts = [], agent = "orchestrator-analyst") {
  return { info: { id, sessionID: SESSION, role: "assistant", parentID: "user", mode: agent, time: { created: 2, completed: 3 }, modelID: "gpt-5.6-terra", providerID: "openai" }, parts: [text(`${id}-text`, value, { messageID: id }), ...parts] }
}

function task(id, role, result) {
  const child = `${id}-child`
  return { id, sessionID: SESSION, messageID: "assistant", type: "tool", callID: `${id}-call`, tool: "task", state: { status: "completed", input: { description: "work", prompt: "work", subagent_type: role }, output: `<task id="${child}" state="completed">\n<task_result>\n${result}\n</task_result>\n</task>`, title: "work", metadata: { parentSessionId: SESSION, sessionId: child }, time: { start: 1, end: 2 } } }
}

function review(label, options = {}) {
  const origin = options.origin ?? "CREATE"
  const target = options.target ?? TARGET
  const gate = options.gate ?? "CLOSED_UNUSED"
  const clarificationID = options.clarificationID ?? "none"
  const questionIDs = options.questionIDs ?? "none"
  const questions = options.questions ?? "none"
  const incorporation = options.incorporation ?? (gate === "CONSUMED" ? "CONFIRMED" : "NOT_APPLICABLE")
  const outcome = options.outcome ?? "READY"
  const readyPaths = options.readyPaths ?? FULL_PATH
  const checkedPaths = options.checkedPaths ?? FULL_PATH
  const deferredPaths = options.deferredPaths ?? "none"
  const completePaths = options.completePaths ?? "none"
  const supersededPaths = options.supersededPaths ?? "none"
  const deferredScope = options.deferredScope ?? "none"
  const confirmation = options.confirmation ?? (outcome === "PARTIAL_READY" ? "CONFIRMED" : "NOT_APPLICABLE")
  const uncertaintyIDs = options.uncertaintyIDs ?? "none"
  const uncertainties = options.uncertainties ?? "none"
  const reassessAfter = options.reassessAfter ?? "none"
  return `${label}: PASS\nReview mode: NORMAL\nOrigin: ${origin}\nTarget: ${target}\nClarification gate: ${gate}\nClarification ID: ${clarificationID}\nConfirmed question IDs: ${questionIDs}\nQuestions: ${questions}\nClarification incorporation: ${incorporation}\nConfirmed outcome: ${outcome}\nChecked tasks: ${checkedPaths}\nReady for finalize: ${readyPaths}\nDeferred tasks: ${deferredPaths}\nComplete tasks: ${completePaths}\nSuperseded tasks: ${supersededPaths}\nDeferred scope: ${deferredScope}\nUncertainty confirmation: ${confirmation}\nConfirmed uncertainty IDs: ${uncertaintyIDs}\nConfirmed uncertainties: ${uncertainties}\nReassess after: ${reassessAfter}\nFindings: none\nБлокер: none`
}

function finalize(options = {}) {
  const origin = options.origin ?? "CREATE"
  const target = options.target ?? TARGET
  const gate = options.gate ?? "CLOSED_UNUSED"
  const clarificationID = options.clarificationID ?? "none"
  const questionIDs = options.questionIDs ?? "none"
  const questions = options.questions ?? "none"
  const outcome = options.outcome ?? "READY"
  const readyPaths = options.readyPaths ?? FULL_PATH
  const checkedPaths = options.checkedPaths ?? FULL_PATH
  const deferredPaths = options.deferredPaths ?? "none"
  const completePaths = options.completePaths ?? "none"
  const supersededPaths = options.supersededPaths ?? "none"
  const deferredScope = options.deferredScope ?? "none"
  const uncertaintyIDs = options.uncertaintyIDs ?? "none"
  const uncertainties = options.uncertainties ?? "none"
  const reassessAfter = options.reassessAfter ?? "none"
  return `PLANNING: PASS\nMODE: FINALIZE\nOrigin: ${origin}\nTarget: ${target}\nEvidence: NOT_APPLICABLE\nProposed outcome: ${outcome}\nClarification gate: ${gate}\nClarification ID: ${clarificationID}\nQuestion IDs: ${questionIDs}\nQuestions: ${questions}\nPlanning attempt: NOT_APPLICABLE\nTarget state: PRESENT\nЗадачи: ${readyPaths}\nChecked tasks: ${checkedPaths}\nDeferred tasks: ${deferredPaths}\nComplete tasks: ${completePaths}\nSuperseded tasks: ${supersededPaths}\nDeferred scope: ${deferredScope}\nUncertainties: ${uncertainties}\nUncertainty IDs: ${uncertaintyIDs}\nReassess after: ${reassessAfter}\nIssue journal: none\nFindings applied: NOT_APPLICABLE\nИзменено: ${readyPaths}\nПредположения: none\nRejection: none\nБлокер: none`
}

function ready(options = {}) {
  const outcome = options.outcome ?? "READY"
  const target = options.target ?? TARGET
  const gate = options.gate ?? "CLOSED_UNUSED"
  const clarificationID = options.clarificationID ?? "none"
  const questionIDs = options.questionIDs ?? "none"
  const questions = options.questions ?? "none"
  const readyPaths = options.readyPaths ?? FULL_PATH
  const deferredPaths = options.deferredPaths ?? "none"
  const completePaths = options.completePaths ?? "none"
  const supersededPaths = options.supersededPaths ?? "none"
  const deferredScope = options.deferredScope ?? "none"
  const uncertaintyIDs = options.uncertaintyIDs ?? "none"
  const uncertainties = options.uncertainties ?? "none"
  const reassessAfter = options.reassessAfter ?? "none"
  return `Готово\n\nИтог: ${outcome}\nTarget: ${target}\nClarification gate: ${gate}\nClarification ID: ${clarificationID}\nQuestion IDs: ${questionIDs}\nВопросы: ${questions}\nЗадачи: ${readyPaths}\nОтложенные задачи: ${deferredPaths}\nЗавершённые задачи: ${completePaths}\nИсключённые задачи: ${supersededPaths}\nОтложенный scope: ${deferredScope}\nНеопределённости: ${uncertaintyIDs}\nUncertainties: ${uncertainties}\nREASSESS после: ${reassessAfter}\nРиски и ограничения: none\nБлокер: none`
}

function clarificationPlanner() {
  return `PLANNING: CLARIFICATION_REQUIRED\nMODE: CREATE\nOrigin: CREATE\nTarget: ${TARGET}\nEvidence: COMPLETE\nProposed outcome: NOT_APPLICABLE\nClarification gate: WAITING\nClarification ID: avatar-contract\nQuestion IDs: Q1\nQuestions: Q1 choose public URL lifetime: permanent or expiring\nPlanning attempt: COMPLETE\nTarget state: ABSENT\nЗадачи: none\nChecked tasks: none\nDeferred tasks: none\nComplete tasks: none\nSuperseded tasks: none\nDeferred scope: none\nUncertainties: none\nUncertainty IDs: none\nReassess after: none\nIssue journal: none\nFindings applied: NOT_APPLICABLE\nИзменено: none\nПредположения: none\nRejection: none\nБлокер: none`
}

function clarificationResponse() {
  return `Уточнение\n\nИтог: CLARIFICATION_REQUIRED\nTarget: ${TARGET}\nClarification gate: WAITING\nClarification ID: avatar-contract\nQuestion IDs: Q1\nВопросы: Q1 choose public URL lifetime: permanent or expiring\nЗадачи: none\nОтложенные задачи: none\nЗавершённые задачи: none\nИсключённые задачи: none\nОтложенный scope: none\nНеопределённости: none\nUncertainties: none\nREASSESS после: none\nРиски и ограничения: none\nБлокер: none`
}

test("incomplete analyst turn resumes", () => {
  const decision = AnalystWorkflowGuard.testing.continuationDecision([user("user"), assistant("assistant", "Стоп\n\nИтог: BLOCKED\nЗадачи: none\nОтложенные задачи: none\nЗавершённые задачи: none\nИсключённые задачи: none\nОтложенный scope: none\nНеопределённости: none\nREASSESS после: none\nРиски и ограничения: none\nБлокер: repeat request")], SESSION)
  assert.equal(decision.resume, true)
  assert.equal(decision.agent, "orchestrator-analyst")
})

test("non-analyst workflow never resumes", () => {
  const messages = [user("user", "build", "Implement feature"), assistant("assistant", "done", [], "build")]
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "not-analyst-workflow" })
})

test("analyst history cannot resume latest non-analyst assistant", () => {
  const messages = [user("user", "orchestrator-analyst", "Create plan"), assistant("assistant", "stopped", [], "build")]
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "not-analyst-workflow" })
})

test("file-only non-analyst user supersedes analyst history", () => {
  const fileUser = { info: { id: "file-user", sessionID: SESSION, role: "user", time: { created: 2 }, agent: "build", model: { providerID: "openai", modelID: "gpt-5.6-terra" } }, parts: [{ id: "file", sessionID: SESSION, messageID: "file-user", type: "file", mime: "text/plain", filename: "request.txt", url: "data:text/plain,work" }] }
  const messages = [user("user", "orchestrator-analyst", "Create plan"), fileUser, assistant("assistant", "stopped")]
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "not-analyst-workflow" })
})

test("standard reviewed finalize is terminal", () => {
  const messages = [user("user"), assistant("assistant", ready(), [task("terra", "orchestrator-plan-reviewer", review("PLAN_REVIEW")), task("ultra", "orchestrator-plan-ultra-reviewer", review("ULTRA_PLAN_REVIEW")), task("final", "orchestrator-task-planner", finalize())])]
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "terminal" })
})

test("single-model reviewed finalize is terminal", () => {
  const messages = [user("user", "orchestrator-analyst-single-model"), assistant("assistant", ready(), [task("review", "orchestrator-plan-reviewer", review("PLAN_REVIEW")), task("final", "orchestrator-task-planner", finalize())], "orchestrator-analyst-single-model")]
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "terminal" })
})

test("answered clarification can finalize once", () => {
  const options = { gate: "CONSUMED", clarificationID: "avatar-contract", questionIDs: "Q1", questions: "Q1 choose public URL lifetime: permanent or expiring" }
  const messages = [user("user", "orchestrator-analyst-single-model"), assistant("clarification", clarificationResponse(), [task("clarify", "orchestrator-task-planner", clarificationPlanner())], "orchestrator-analyst-single-model"), user("answer", "orchestrator-analyst-single-model", "permanent"), assistant("assistant", ready(options), [task("review", "orchestrator-plan-reviewer", review("PLAN_REVIEW", options)), task("final", "orchestrator-task-planner", finalize(options))], "orchestrator-analyst-single-model")]
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "terminal" })
})

test("consumed clarification without prior certificate resumes", () => {
  const options = { gate: "CONSUMED", clarificationID: "avatar-contract", questionIDs: "Q1", questions: "Q1 choose public URL lifetime: permanent or expiring" }
  const messages = [user("answer", "orchestrator-analyst-single-model", "Clarification ID: avatar-contract\nQ1: permanent"), assistant("assistant", ready(options), [task("review", "orchestrator-plan-reviewer", review("PLAN_REVIEW", options)), task("final", "orchestrator-task-planner", finalize(options))], "orchestrator-analyst-single-model")]
  assert.equal(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION).resume, true)
})

test("standard confirmed partial ready is terminal", () => {
  const options = { outcome: "PARTIAL_READY", deferredScope: "storage rollback behavior", uncertaintyIDs: "storage-rollback", uncertainties: "storage-rollback{question=rollback;static=searched storage;implementation=required;unlock=01;durable=integration test;affected=cleanup;condition=COMPLETE}", reassessAfter: FULL_PATH }
  const messages = [user("user"), assistant("assistant", ready(options), [task("terra", "orchestrator-plan-reviewer", review("PLAN_REVIEW", options)), task("ultra", "orchestrator-plan-ultra-reviewer", review("ULTRA_PLAN_REVIEW", options)), task("final", "orchestrator-task-planner", finalize(options))])]
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "terminal" })
})

test("partial ready without reviewer uncertainty confirmation resumes", () => {
  const options = { outcome: "PARTIAL_READY", deferredScope: "storage rollback behavior", uncertaintyIDs: "storage-rollback", uncertainties: "storage-rollback{question=rollback;static=searched storage;implementation=required;unlock=01;durable=integration test;affected=cleanup;condition=COMPLETE}", reassessAfter: FULL_PATH }
  const unconfirmed = { ...options, confirmation: "REJECTED" }
  const messages = [user("user"), assistant("assistant", ready(options), [task("terra", "orchestrator-plan-reviewer", review("PLAN_REVIEW", unconfirmed)), task("ultra", "orchestrator-plan-ultra-reviewer", review("ULTRA_PLAN_REVIEW", options)), task("final", "orchestrator-task-planner", finalize(options))])]
  assert.equal(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION).resume, true)
})

test("partial ready without complete uncertainty entries resumes", () => {
  const options = { outcome: "PARTIAL_READY", deferredScope: "storage rollback behavior", uncertaintyIDs: "storage-rollback", uncertainties: "none", reassessAfter: FULL_PATH }
  const messages = [user("user"), assistant("assistant", ready(options), [task("terra", "orchestrator-plan-reviewer", review("PLAN_REVIEW", options)), task("ultra", "orchestrator-plan-ultra-reviewer", review("ULTRA_PLAN_REVIEW", options)), task("final", "orchestrator-task-planner", finalize(options))])]
  assert.equal(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION).resume, true)
})

test("reassessed satisfied plan is terminal", () => {
  const options = { origin: "REASSESS", outcome: "SATISFIED", readyPaths: "none", checkedPaths: FULL_PATH, completePaths: FULL_PATH }
  const messages = [user("user"), assistant("assistant", ready(options), [task("terra", "orchestrator-plan-reviewer", review("PLAN_REVIEW", options)), task("ultra", "orchestrator-plan-ultra-reviewer", review("ULTRA_PLAN_REVIEW", options)), task("final", "orchestrator-task-planner", finalize(options))])]
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "terminal" })
})

test("certified first-pass clarification waits for user", () => {
  const messages = [user("user"), assistant("assistant", clarificationResponse(), [task("clarify", "orchestrator-task-planner", clarificationPlanner())])]
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "terminal" })
})

test("second clarification after answer resumes instead of waiting", () => {
  const messages = [user("user"), assistant("assistant-1", clarificationResponse(), [task("clarify-1", "orchestrator-task-planner", clarificationPlanner())]), user("answer", "orchestrator-analyst", "Clarification ID: avatar-contract\nQ1: permanent"), assistant("assistant-2", clarificationResponse(), [task("clarify-2", "orchestrator-task-planner", clarificationPlanner())])]
  assert.equal(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION).resume, true)
})

test("prior clarification does not block different target", () => {
  const otherTarget = "1_orchestrator/other/"
  const otherPlanner = clarificationPlanner().replaceAll(TARGET, otherTarget).replaceAll("avatar-contract", "other-contract")
  const otherResponse = clarificationResponse().replaceAll(TARGET, otherTarget).replaceAll("avatar-contract", "other-contract")
  const messages = [user("user"), assistant("assistant-1", clarificationResponse(), [task("clarify-1", "orchestrator-task-planner", clarificationPlanner())]), user("new-request", "orchestrator-analyst", "Create another plan"), assistant("assistant-2", otherResponse, [task("clarify-2", "orchestrator-task-planner", otherPlanner)])]
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "terminal" })
})

test("multiline clarification batch cannot certify waiting", () => {
  const planner = clarificationPlanner().replace("Questions: Q1 choose public URL lifetime: permanent or expiring", "Questions: Q1 choose public URL lifetime\nextra planner detail")
  const response = clarificationResponse().replace("Вопросы: Q1 choose public URL lifetime: permanent or expiring", "Вопросы: Q1 choose public URL lifetime\nextra response detail")
  const messages = [user("user"), assistant("assistant", response, [task("clarify", "orchestrator-task-planner", planner)])]
  assert.equal(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION).resume, true)
})

test("uncertified clarification resumes", () => {
  const response = "Уточнение\n\nИтог: CLARIFICATION_REQUIRED\nClarification gate: WAITING\nClarification ID: avatar-contract\nQuestion IDs: Q1\nВопросы: choose URL lifetime\nЗадачи: none\nОтложенные задачи: none\nЗавершённые задачи: none\nИсключённые задачи: none\nОтложенный scope: none\nНеопределённости: none\nREASSESS после: none\nРиски и ограничения: none\nБлокер: none"
  assert.equal(AnalystWorkflowGuard.testing.continuationDecision([user("user"), assistant("assistant", response)], SESSION).resume, true)
})

test("finalize without required reviews resumes", () => {
  const messages = [user("user"), assistant("assistant", ready(), [task("final", "orchestrator-task-planner", finalize())])]
  assert.equal(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION).resume, true)
})

test("finalize with absent target state resumes", () => {
  const invalid = finalize().replace("Target state: PRESENT", "Target state: ABSENT")
  const messages = [user("user"), assistant("assistant", ready(), [task("terra", "orchestrator-plan-reviewer", review("PLAN_REVIEW")), task("ultra", "orchestrator-plan-ultra-reviewer", review("ULTRA_PLAN_REVIEW")), task("final", "orchestrator-task-planner", invalid)])]
  assert.equal(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION).resume, true)
})

test("finalize with missing changed ready path resumes", () => {
  const invalid = finalize().replace(`Изменено: ${FULL_PATH}`, "Изменено: none")
  const messages = [user("user"), assistant("assistant", ready(), [task("terra", "orchestrator-plan-reviewer", review("PLAN_REVIEW")), task("ultra", "orchestrator-plan-ultra-reviewer", review("ULTRA_PLAN_REVIEW")), task("final", "orchestrator-task-planner", invalid)])]
  assert.equal(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION).resume, true)
})

test("task path outside final tasks field cannot certify ready", () => {
  const response = `Итог: READY\nЗадачи: none\nОтложенные задачи: none\nЗавершённые задачи: none\nИсключённые задачи: none\nОтложенный scope: none\nНеопределённости: none\nREASSESS после: none\nРиски и ограничения: generated ${FULL_PATH}\nБлокер: none`
  const messages = [user("user"), assistant("assistant", response, [task("terra", "orchestrator-plan-reviewer", review("PLAN_REVIEW")), task("ultra", "orchestrator-plan-ultra-reviewer", review("ULTRA_PLAN_REVIEW")), task("final", "orchestrator-task-planner", finalize())])]
  assert.equal(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION).resume, true)
})

test("overlapping task partitions cannot certify ready", () => {
  const options = { completePaths: FULL_PATH }
  const messages = [user("user"), assistant("assistant", ready(options), [task("terra", "orchestrator-plan-reviewer", review("PLAN_REVIEW", options)), task("ultra", "orchestrator-plan-ultra-reviewer", review("ULTRA_PLAN_REVIEW", options)), task("final", "orchestrator-task-planner", finalize(options))])]
  assert.equal(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION).resume, true)
})

test("traversal task path cannot certify ready", () => {
  const traversal = "/repo/1_orchestrator/a/../b/tasks/01-work.md"
  const options = { readyPaths: traversal, checkedPaths: traversal }
  const messages = [user("user"), assistant("assistant", ready(options), [task("terra", "orchestrator-plan-reviewer", review("PLAN_REVIEW", options)), task("ultra", "orchestrator-plan-ultra-reviewer", review("ULTRA_PLAN_REVIEW", options)), task("final", "orchestrator-task-planner", finalize(options))])]
  assert.equal(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION).resume, true)
})

test("task paths outside declared target cannot certify ready", () => {
  const options = { target: "1_orchestrator/other/" }
  const messages = [user("user"), assistant("assistant", ready(options), [task("terra", "orchestrator-plan-reviewer", review("PLAN_REVIEW", options)), task("ultra", "orchestrator-plan-ultra-reviewer", review("ULTRA_PLAN_REVIEW", options)), task("final", "orchestrator-task-planner", finalize(options))])]
  assert.equal(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION).resume, true)
})

test("noncanonical target cannot certify ready", () => {
  const options = { target: "1_orchestrator/request" }
  const messages = [user("user"), assistant("assistant", ready(options), [task("terra", "orchestrator-plan-reviewer", review("PLAN_REVIEW", options)), task("ultra", "orchestrator-plan-ultra-reviewer", review("ULTRA_PLAN_REVIEW", options)), task("final", "orchestrator-task-planner", finalize(options))])]
  assert.equal(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION).resume, true)
})

test("certified create blocker is terminal", () => {
  const blocked = `PLANNING: BLOCKED\nMODE: CREATE\nOrigin: CREATE\nTarget: ${TARGET}\nEvidence: BLOCKED\nProposed outcome: NOT_APPLICABLE\nClarification gate: OPEN\nClarification ID: none\nQuestion IDs: none\nQuestions: none\nPlanning attempt: NOT_APPLICABLE\nTarget state: ABSENT\nЗадачи: none\nChecked tasks: none\nDeferred tasks: none\nComplete tasks: none\nSuperseded tasks: none\nDeferred scope: none\nUncertainties: none\nUncertainty IDs: none\nReassess after: none\nIssue journal: none\nFindings applied: NOT_APPLICABLE\nИзменено: none\nПредположения: none\nRejection: none\nБлокер: grant repository access`
  const response = `Итог: BLOCKED\nTarget: ${TARGET}\nClarification gate: OPEN\nClarification ID: none\nQuestion IDs: none\nВопросы: none\nЗадачи: none\nОтложенные задачи: none\nЗавершённые задачи: none\nИсключённые задачи: none\nОтложенный scope: none\nНеопределённости: none\nUncertainties: none\nREASSESS после: none\nРиски и ограничения: none\nБлокер: grant repository access`
  const messages = [user("user"), assistant("assistant", response, [task("blocked", "orchestrator-task-planner", blocked)])]
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(messages, SESSION), { resume: false, reason: "terminal" })
  const changed = [user("user"), assistant("assistant", response, [task("blocked", "orchestrator-task-planner", blocked.replace("Изменено: none", `Изменено: ${FULL_PATH}`))])]
  assert.equal(AnalystWorkflowGuard.testing.continuationDecision(changed, SESSION).resume, true)
  const consumedPlanner = blocked.replace("Clarification gate: OPEN\nClarification ID: none\nQuestion IDs: none\nQuestions: none", "Clarification gate: CONSUMED\nClarification ID: forged\nQuestion IDs: Q1\nQuestions: Q1 forged")
  const consumedResponse = response.replace("Clarification gate: OPEN\nClarification ID: none\nQuestion IDs: none\nВопросы: none", "Clarification gate: CONSUMED\nClarification ID: forged\nQuestion IDs: Q1\nВопросы: Q1 forged")
  const forged = [user("user"), assistant("assistant", consumedResponse, [task("blocked", "orchestrator-task-planner", consumedPlanner)])]
  assert.equal(AnalystWorkflowGuard.testing.continuationDecision(forged, SESSION).resume, true)
})

test("planner block requires originating blocked review", () => {
  const blockedReview = `PLAN_REVIEW: BLOCKED\nReview mode: NORMAL\nOrigin: CREATE\nTarget: ${TARGET}\nClarification gate: CLOSED_UNUSED\nClarification ID: none\nConfirmed question IDs: none\nQuestions: none\nClarification incorporation: NOT_APPLICABLE\nConfirmed outcome: READY\nChecked tasks: ${FULL_PATH}\nReady for finalize: ${FULL_PATH}\nDeferred tasks: none\nComplete tasks: none\nSuperseded tasks: none\nDeferred scope: none\nUncertainty confirmation: NOT_APPLICABLE\nConfirmed uncertainty IDs: none\nConfirmed uncertainties: none\nReassess after: none\nFindings: none\nБлокер: choose public API behavior`
  const blockedPlan = `PLANNING: PASS\nMODE: BLOCK\nOrigin: CREATE\nTarget: ${TARGET}\nEvidence: NOT_APPLICABLE\nProposed outcome: READY\nClarification gate: CLOSED_UNUSED\nClarification ID: none\nQuestion IDs: none\nQuestions: none\nPlanning attempt: NOT_APPLICABLE\nTarget state: PRESENT\nЗадачи: ${FULL_PATH}\nChecked tasks: ${FULL_PATH}\nDeferred tasks: none\nComplete tasks: none\nSuperseded tasks: none\nDeferred scope: none\nUncertainties: none\nUncertainty IDs: none\nReassess after: none\nIssue journal: ${TARGET}planning-issues.md\nFindings applied: NOT_APPLICABLE\nИзменено: ${TARGET}planning-issues.md\nПредположения: none\nRejection: none\nБлокер: choose public API behavior`
  const response = `Стоп\n\nИтог: BLOCKED\nTarget: ${TARGET}\nClarification gate: CLOSED_UNUSED\nClarification ID: none\nQuestion IDs: none\nВопросы: none\nЗадачи: ${FULL_PATH}\nОтложенные задачи: none\nЗавершённые задачи: none\nИсключённые задачи: none\nОтложенный scope: none\nНеопределённости: none\nUncertainties: none\nREASSESS после: none\nРиски и ограничения: none\nБлокер: choose public API behavior`
  const certified = [user("user"), assistant("assistant", response, [task("review", "orchestrator-plan-reviewer", blockedReview), task("blocked", "orchestrator-task-planner", blockedPlan)])]
  assert.deepEqual(AnalystWorkflowGuard.testing.continuationDecision(certified, SESSION), { resume: false, reason: "terminal" })
  const uncertified = [user("user"), assistant("assistant", response, [task("blocked", "orchestrator-task-planner", blockedPlan)])]
  assert.equal(AnalystWorkflowGuard.testing.continuationDecision(uncertified, SESSION).resume, true)
  const malformed = [user("user"), assistant("assistant", response, [task("review", "orchestrator-plan-reviewer", blockedReview), task("blocked", "orchestrator-task-planner", blockedPlan.replace("Target state: PRESENT", "Target state: ABSENT"))])]
  assert.equal(AnalystWorkflowGuard.testing.continuationDecision(malformed, SESSION).resume, true)
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

test("plugin ignores declared non-analyst root sessions before reading messages", async () => {
  let messagesCalled = false
  const client = {
    app: { log: async () => ({ data: true }) },
    session: {
      get: async () => ({ data: { id: SESSION, directory: "/repo", agent: "build" } }),
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
