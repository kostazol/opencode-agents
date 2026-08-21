
import assert from "node:assert/strict"
import { mkdir, mkdtemp, readFile, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"

import {
  ProtocolError,
  WorkflowStore,
  migrateState,
  newState,
  reserveNext,
  validateState,
} from "../runtime/orchestrator.js"
import { analysisFixture, event } from "./helpers.mjs"

async function writeArtifact(root, relative, metadata, body = "# Artifact\n") {
  const destination = path.join(root, ...relative.split("/"))
  await mkdir(path.dirname(destination), { recursive: true })
  await writeFile(destination, [
    "---",
    "schema_version: 1",
    `artifact: ${metadata.artifact}`,
    `stage: ${metadata.stage ?? "none"}`,
    `revision: ${metadata.revision}`,
    `source_revision: ${metadata.source_revision}`,
    `status: ${metadata.status}`,
    "---",
    body.trimEnd(),
    "",
  ].join("\n"), "utf8")
}

test("state schema v1 migration is explicit and invalidates an unsnapshotted transition", () => {
  const reserved = reserveNext(newState("schema-migration")).state
  const legacy = structuredClone(reserved)
  legacy.schema_version = 1
  delete legacy.pending.input_snapshot
  delete legacy.pending.output_snapshot
  delete legacy.pending.snapshots_captured
  const migrated = migrateState(legacy)
  assert.equal(migrated.migrated, true)
  assert.equal(migrated.from_version, 1)
  assert.equal(migrated.to_version, 2)
  const state = validateState(migrated.state)
  assert.equal(state.status, "blocked")
  assert.equal(state.pending, null)
  assert.match(state.blocker.detail, /immutable input snapshot/i)
})

test("persisted pending transition contains path, existence, digest, and revision metadata snapshots", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-snapshot-shape-"))
  const root = path.join(base, "1_orchestrator", "sample")
  await mkdir(root, { recursive: true })
  await writeFile(path.join(root, "feedback.md"), "input\n", "utf8")
  const reserved = await new WorkflowStore(base, "sample").reserve()
  assert.equal(reserved.state.schema_version, 2)
  assert.equal(reserved.state.pending.snapshots_captured, true)
  assert.equal(reserved.state.pending.input_snapshot.length, reserved.state.pending.inputs.length)
  for (const snapshot of reserved.state.pending.input_snapshot) {
    assert.equal(typeof snapshot.path, "string")
    assert.equal(typeof snapshot.exists, "boolean")
    if (snapshot.exists) assert.match(snapshot.digest, /^[0-9a-f]{64}$/)
    else assert.equal(snapshot.digest, null)
    assert.ok(snapshot.metadata === null || typeof snapshot.metadata === "object")
  }
  const persisted = JSON.parse(await readFile(path.join(root, ".orchestrator", "state.json"), "utf8"))
  assert.deepEqual(persisted.pending.input_snapshot, reserved.state.pending.input_snapshot)
})

test("a pre-existing output must be regenerated after reserve", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-stale-output-"))
  const root = path.join(base, "1_orchestrator", "sample")
  await mkdir(root, { recursive: true })
  await writeFile(path.join(root, "analysis.json"), JSON.stringify(analysisFixture(), null, 2) + "\n", "utf8")
  await writeArtifact(root, "discovery.md", { artifact: "discovery", revision: 1, source_revision: 0, status: "READY_FOR_REVIEW" })
  const store = new WorkflowStore(base, "sample")
  const reserved = await store.reserve()
  await assert.rejects(
    () => store.apply(event(reserved.action, "discovery_result", { revision: 1, status: "READY_FOR_REVIEW" }), reserved.state.state_revision),
    /stale|regenerated/i,
  )
})

test("artifact revision metadata is part of the transition contract", async () => {
  const base = await mkdtemp(path.join(os.tmpdir(), "orchestrator-artifact-metadata-"))
  const root = path.join(base, "1_orchestrator", "sample")
  await mkdir(root, { recursive: true })
  const store = new WorkflowStore(base, "sample")
  const reserved = await store.reserve()
  await writeFile(path.join(root, "analysis.json"), JSON.stringify(analysisFixture(), null, 2) + "\n", "utf8")
  await writeArtifact(root, "discovery.md", { artifact: "discovery", revision: 1, source_revision: 99, status: "READY_FOR_REVIEW" })
  await assert.rejects(
    () => store.apply(event(reserved.action, "discovery_result", { revision: 1, status: "READY_FOR_REVIEW" }), reserved.state.state_revision),
    ProtocolError,
  )
})
