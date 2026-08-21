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

test("legacy plan migration preserves revisions and starts missing human review", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-legacy-"))
  const root = path.join(base, "1_orchestrator/sample")
  await mkdir(root, { recursive: true })
  await writeFile(path.join(root, "plan.md"), `---
status: ready
current_stage: none
---
# Legacy plan

## Stage map

### S01 — Первый этап
- Status: PASS
- Revision: 3
- Depends on: none
- Details: stages/01-first-stage.md
- Review: reviews/01.md
`)
  const store = new WorkflowStore(base, "sample")
  const validation = await store.validate()
  assert.equal(validation.valid, true)
  assert.equal(validation.status, "human_reviewing")
  const state = JSON.parse(await readFile(store.statePath, "utf8"))
  assert.equal(state.stages[0].revision, 3)
  assert.equal(state.stages[0].human_revision, 0)
  assert.equal(state.current_stage, "S01")
})

test("legacy migration rejects ambiguous blocked state", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-legacy-blocked-"))
  const root = path.join(base, "1_orchestrator/sample")
  await mkdir(root, { recursive: true })
  await writeFile(path.join(root, "plan.md"), `---
status: blocked
current_stage: none
---
# Legacy plan
`)
  await assert.rejects(() => new WorkflowStore(base, "sample").validate(), /cannot be migrated without structured blocker data/)
})

test("concurrent reserve serializes to one pending transition", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-concurrent-"))
  const firstStore = new WorkflowStore(base, "sample")
  const secondStore = new WorkflowStore(base, "sample")
  const [first, second] = await Promise.all([firstStore.reserve(), secondStore.reserve()])
  assert.equal(first.action.transition_id, second.action.transition_id)
  assert.equal(first.state.state_revision, 1)
  assert.equal(second.state.state_revision, 1)
  const persisted = JSON.parse(await readFile(firstStore.statePath, "utf8"))
  assert.equal(persisted.sequence, 1)
  assert.equal(persisted.pending.transition_id, first.action.transition_id)
})

