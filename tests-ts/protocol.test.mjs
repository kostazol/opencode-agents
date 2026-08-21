import assert from "node:assert/strict"
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"

import {
  ProtocolError,
  WorkflowStore,
  affectedStageClosure,
  applyEvent,
  newState,
  parseJsonStrict,
  reserveNext,
  validateAnalysis,
} from "../runtime/orchestrator.js"

import { analysisFixture, event, advanceToPlanning } from "./helpers.mjs"

test("analysis validates reciprocal traceability and contract order", () => {
  const analysis = validateAnalysis(analysisFixture())
  assert.deepEqual(affectedStageClosure(analysis, ["S01"]), ["S01", "S02"])
  const invalid = structuredClone(analysisFixture())
  invalid.stages[1].depends_on = []
  assert.throws(() => validateAnalysis(invalid), ProtocolError)
})

test("reservation is stable and event replay is idempotent", async () => {
  const state = newState("sample")
  const first = reserveNext(state)
  const second = reserveNext(first.state)
  assert.deepEqual(second.action, first.action)
  const input = event(first.action, "discovery_result", { revision: 1, status: "QUESTIONS" })
  const applied = await applyEvent(process.cwd(), first.state, input)
  const replay = await applyEvent(process.cwd(), applied.state, input)
  assert.deepEqual(replay.result, applied.result)
  await assert.rejects(
    () => applyEvent(process.cwd(), applied.state, event(first.action, "discovery_result", { revision: 1, status: "BLOCKED", detail: "x" })),
    ProtocolError,
  )
})

test("unchanged findings stop the revise loop", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-convergence-"))
  await mkdir(path.join(base, "src"), { recursive: true })
  await writeFile(path.join(base, "src/evidence.txt"), "same evidence\n")
  let { state, analysis } = await advanceToPlanning(base)

  let reserved = reserveNext(state, analysis)
  state = (await applyEvent(base, reserved.state, event(reserved.action, "stage_plan_result", { revision: 1, status: "REVIEW" }), analysis)).state
  reserved = reserveNext(state, analysis)
  const finding = { revision: 1, status: "REVISE", findings: [{ code: "missing-case", scope: "S01", message: "Добавить сценарий", evidence: ["src/evidence.txt"] }] }
  state = (await applyEvent(base, reserved.state, event(reserved.action, "stage_review_result", finding), analysis)).state

  reserved = reserveNext(state, analysis)
  state = (await applyEvent(base, reserved.state, event(reserved.action, "stage_plan_result", { revision: 2, status: "REVIEW" }), analysis)).state
  reserved = reserveNext(state, analysis)
  const second = await applyEvent(base, reserved.state, event(reserved.action, "stage_review_result", { ...finding, revision: 2 }), analysis)
  assert.equal(second.state.status, "blocked")
  assert.equal(second.state.blocker.reason, "no_semantic_progress")
})

test("store persists, validates, and renders plan", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-store-"))
  const requestRoot = path.join(base, "1_orchestrator/sample")
  await mkdir(requestRoot, { recursive: true })
  await writeFile(path.join(requestRoot, "analysis.json"), JSON.stringify(analysisFixture(), null, 2))
  const store = new WorkflowStore(base, "sample")
  const reserved = await store.reserve()
  assert.equal(reserved.action.action, "DISCOVER")
  const applied = await store.apply(event(reserved.action, "discovery_result", { revision: 1, status: "READY_FOR_REVIEW" }), reserved.state.state_revision)
  assert.equal(applied.state.status, "discovery_review")
  const validation = await store.validate()
  assert.equal(validation.valid, true)
  assert.match(await readFile(path.join(requestRoot, "plan.md"), "utf8"), /Stage map/)
  assert.match(await readFile(path.join(requestRoot, ".orchestrator/journal.jsonl"), "utf8"), /discovery_result/)
})


test("strict JSON rejects duplicate keys and trailing content", () => {
  assert.throws(() => parseJsonStrict('{"schema_version":1,"schema_version":2}'), /duplicate JSON key/)
  assert.throws(() => parseJsonStrict('{"ok":true} trailing'), /trailing content/)
  assert.deepEqual(parseJsonStrict('{"nested":{"value":1},"items":[true,null,"x"]}'), {
    nested: { value: 1 },
    items: [true, null, "x"],
  })
})

test("optimistic revision conflicts are rejected", () => {
  const reserved = reserveNext(newState("sample"))
  assert.throws(() => reserveNext(reserved.state, undefined, reserved.state.state_revision - 1), ProtocolError)
})

test("changed evidence permits another revision", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-progress-"))
  await mkdir(path.join(base, "src"), { recursive: true })
  const evidence = path.join(base, "src/evidence.txt")
  await writeFile(evidence, "first evidence\n")
  let { state, analysis } = await advanceToPlanning(base)

  let reserved = reserveNext(state, analysis)
  state = (await applyEvent(base, reserved.state, event(reserved.action, "stage_plan_result", { revision: 1, status: "REVIEW" }), analysis)).state
  reserved = reserveNext(state, analysis)
  const finding = { revision: 1, status: "REVISE", findings: [{ code: "missing-case", scope: "S01", message: "Добавить сценарий", evidence: ["src/evidence.txt"] }] }
  state = (await applyEvent(base, reserved.state, event(reserved.action, "stage_review_result", finding), analysis)).state

  await writeFile(evidence, "second evidence with material change\n")
  reserved = reserveNext(state, analysis)
  state = (await applyEvent(base, reserved.state, event(reserved.action, "stage_plan_result", { revision: 2, status: "REVIEW" }), analysis)).state
  reserved = reserveNext(state, analysis)
  const second = await applyEvent(base, reserved.state, event(reserved.action, "stage_review_result", { ...finding, revision: 2 }), analysis)
  assert.equal(second.state.status, "planning")
  assert.equal(second.state.blocker, null)
})

