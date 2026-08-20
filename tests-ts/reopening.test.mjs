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

test("controlled reopening affects only the dependency closure", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-reopen-"))
  let { state, analysis } = await advanceToPlanning(base)

  let reserved = reserveNext(state, analysis)
  state = (await applyEvent(base, reserved.state, event(reserved.action, "stage_plan_result", { revision: 1, status: "REVIEW" }), analysis)).state
  reserved = reserveNext(state, analysis)
  state = (await applyEvent(base, reserved.state, event(reserved.action, "stage_review_result", { revision: 1, status: "PASS" }), analysis)).state

  reserved = reserveNext(state, analysis)
  assert.equal(reserved.action.stage, "S02")
  state = (await applyEvent(base, reserved.state, event(reserved.action, "stage_plan_result", { revision: 1, status: "REVIEW" }), analysis)).state
  reserved = reserveNext(state, analysis)
  state = (await applyEvent(base, reserved.state, event(reserved.action, "stage_review_result", {
    revision: 1,
    status: "REOPEN",
    affected_stages: ["S01"],
    reason: "upstream contract is incomplete",
  }), analysis)).state

  assert.equal(state.status, "waiting_reopen_approval")
  assert.deepEqual(state.reopen.affected, ["S01", "S02"])
  reserved = reserveNext(state, analysis)
  assert.equal(reserved.action.action, "APPROVE_REOPEN")
  state = (await applyEvent(base, reserved.state, event(reserved.action, "reopen_decision", { decision: "APPROVE" }), analysis)).state
  assert.equal(state.status, "planning")
  assert.equal(state.current_stage, "S01")
  assert.deepEqual(state.stages.map((stage) => stage.status), ["proposed", "proposed"])
})

test("an interrupted transaction is recovered idempotently", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-recovery-"))
  const store = new WorkflowStore(base, "sample")
  const reserved = await store.reserve()
  const plan = await readFile(store.planPath, "utf8")
  const transaction = {
    schema_version: 1,
    state: reserved.state,
    plan,
    journal: {
      entry_id: `manual:recover:${reserved.state.state_revision}`,
      timestamp: new Date().toISOString(),
      action: "recovery-test",
      state_revision: reserved.state.state_revision,
      transition_id: null,
      detail: {},
    },
  }
  await writeFile(store.transactionPath, JSON.stringify(transaction, null, 2))
  await rm(store.statePath, { force: true })
  await rm(store.planPath, { force: true })

  const validation = await store.validate()
  assert.equal(validation.valid, true)
  assert.match(await readFile(store.journalPath, "utf8"), /manual:recover/)
  await store.validate()
  const journal = await readFile(store.journalPath, "utf8")
  assert.equal(journal.match(/manual:recover/g)?.length, 1)
})


test("analysis rejects non-contiguous IDs and orphan acceptance", () => {
  const nonContiguous = structuredClone(analysisFixture())
  nonContiguous.requirements[1].id = "REQ-003"
  nonContiguous.stages[1].requirements = ["REQ-003"]
  nonContiguous.scenarios[1].requirements = ["REQ-003"]
  assert.throws(() => validateAnalysis(nonContiguous), /contiguous and ordered/)

  const orphan = structuredClone(analysisFixture())
  orphan.acceptance.push({ id: "AC-004", text: "Лишний критерий", stage: "S01", verification: "none" })
  assert.throws(() => validateAnalysis(orphan), /not linked from any requirement/)
})

test("corrupt durable state is rejected before routing", () => {
  const reserved = reserveNext(newState("sample"))
  const corrupt = structuredClone(reserved.state)
  corrupt.pending.action = "UNKNOWN"
  assert.throws(() => reserveNext(corrupt), /unsupported action/)

  const badDigest = structuredClone(reserved.state)
  badDigest.pending = null
  badDigest.applied.fake = { event_digest: "x", result: {} }
  assert.throws(() => reserveNext(badDigest), /SHA-256 digest/)
})

