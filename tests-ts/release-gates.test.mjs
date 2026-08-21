
import assert from "node:assert/strict"
import { mkdir, mkdtemp, symlink, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"

import { newState, renderPlan, reserveNext, WorkflowStore } from "../runtime/orchestrator.js"

async function toolContext(directory) {
  return { directory, worktree: directory, project: {}, client: {}, sessionID: "test", messageID: "test", agent: "test", abort: new AbortController().signal }
}

test("actual native OpenCode tools import and invoke controller APIs", async () => {
  const tools = await import("../dist-tools/tools/orchestrator.js")
  assert.deepEqual(Object.keys(tools).sort(), ["apply", "next", "validate"])
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-native-tool-"))
  const context = await toolContext(base)

  const status = JSON.parse(await tools.validate.execute({ request: "native-tool" }, context))
  assert.equal(status.ok, true)
  assert.equal(status.validation.status, "discovery")

  const next = JSON.parse(await tools.next.execute({ request: "native-tool" }, context))
  assert.equal(next.ok, true)
  assert.equal(next.action.action, "DISCOVER")

  const applied = JSON.parse(await tools.apply.execute({
    request: "native-tool",
    transition_id: next.action.transition_id,
    event_type: "task_failure",
    payload_json: JSON.stringify({ reason: "test", detail: "intentional", retryable: true }),
    expected_state_revision: next.state_revision,
  }, context))
  assert.equal(applied.ok, true)
  assert.equal(applied.status, "blocked")
})

test("input symlink escaping request root is rejected", async (t) => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-symlink-"))
  const root = path.join(base, "1_orchestrator", "symlink")
  await mkdir(root, { recursive: true })
  const outside = path.join(base, "outside.md")
  await writeFile(outside, "outside\n")
  try { await symlink(outside, path.join(root, "feedback.md")) } catch (error) { t.skip(`symlink unavailable: ${error}`); return }
  await assert.rejects(() => new WorkflowStore(base, "symlink").reserve(), /symlink escapes/i)
})

test("transaction recovery succeeds only from exact base revision", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-recovery-"))
  const root = path.join(base, "1_orchestrator", "recovery")
  const internal = path.join(root, ".orchestrator")
  await mkdir(internal, { recursive: true })
  const initial = newState("recovery")
  await writeFile(path.join(internal, "state.json"), JSON.stringify(initial, null, 2) + "\n")
  await writeFile(path.join(root, "plan.md"), renderPlan(initial))
  const target = reserveNext(initial).state
  const journal = { entry_id: "recovery:reserve:1", timestamp: new Date(0).toISOString(), action: "reserve", state_revision: target.state_revision, transition_id: target.pending.transition_id, detail: {} }
  await writeFile(path.join(internal, "transaction.json"), JSON.stringify({ schema_version: 2, base_state_revision: 0, state: target, plan: renderPlan(target), journal }, null, 2) + "\n")
  const valid = await new WorkflowStore(base, "recovery").validate()
  assert.equal(valid.state_revision, 1)

  const conflictTarget = structuredClone(target)
  conflictTarget.state_revision = 3
  conflictTarget.pending.issued_state_revision = 3
  conflictTarget.pending.issued_state_revision = 3
  await writeFile(path.join(internal, "state.json"), JSON.stringify(conflictTarget, null, 2) + "\n")
  await writeFile(path.join(internal, "transaction.json"), JSON.stringify({ schema_version: 2, base_state_revision: 0, state: target, plan: renderPlan(target), journal }, null, 2) + "\n")
  await assert.rejects(() => new WorkflowStore(base, "recovery").validate(), /recovery conflict/i)
})

test("duplicate journal entry id with different content is a hard conflict", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-journal-conflict-"))
  const root = path.join(base, "1_orchestrator", "journal")
  const internal = path.join(root, ".orchestrator")
  await mkdir(internal, { recursive: true })
  const initial = newState("journal")
  const target = reserveNext(initial).state
  await writeFile(path.join(internal, "state.json"), JSON.stringify(initial, null, 2) + "\n")
  await writeFile(path.join(root, "plan.md"), renderPlan(initial))
  const journal = { entry_id: "same", timestamp: new Date(0).toISOString(), action: "reserve", state_revision: 1, transition_id: target.pending.transition_id, detail: { version: 1 } }
  await writeFile(path.join(internal, "journal.jsonl"), JSON.stringify({ ...journal, detail: { version: 2 } }) + "\n")
  await writeFile(path.join(internal, "transaction.json"), JSON.stringify({ schema_version: 2, base_state_revision: 0, state: target, plan: renderPlan(target), journal }, null, 2) + "\n")
  await assert.rejects(() => new WorkflowStore(base, "journal").validate(), /journal conflict/i)
})
