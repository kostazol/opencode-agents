from __future__ import annotations

from final_common import prepare


prepare.step7_runtime.TOOLS_TS = r'''
import { tool } from "@opencode-ai/plugin"
import { ProtocolError, WorkflowStore, parseJsonStrict, type EventInput } from "../runtime/orchestrator.js"

const requestSchema = tool.schema.string().min(1).max(80).regex(/^[a-z0-9][a-z0-9-]{0,79}$/)
const revisionSchema = tool.schema.number().int().nonnegative().optional()

function response(value: unknown): string {
  return JSON.stringify(value, null, 2)
}

function failure(error: unknown): string {
  if (error instanceof ProtocolError) {
    return response({ ok: false, error: { type: "protocol", field: error.field, message: error.message, value: error.value } })
  }
  return response({ ok: false, error: { type: "runtime", message: error instanceof Error ? error.message : String(error) } })
}

async function withStore<T>(request: string, context: { directory: string }, operation: (store: WorkflowStore) => Promise<T>): Promise<string> {
  try {
    return response({ ok: true, ...(await operation(new WorkflowStore(context.directory, request)) as object) })
  } catch (error) {
    return failure(error)
  }
}

// OpenCode prefixes exported names with the file name, producing
// orchestrator_next, orchestrator_apply, and orchestrator_validate.
export const next = tool({
  description: "Reserve and return the single deterministic next technical-analysis action.",
  args: { request: requestSchema, expected_state_revision: revisionSchema },
  execute: (args, context) => withStore(args.request, context, async (store) => {
    const { state, action } = await store.reserve(args.expected_state_revision)
    return { state_revision: state.state_revision, status: state.status, action }
  }),
})

export const apply = tool({
  description: "Apply one typed agent result or user decision to the pending technical-analysis transition.",
  args: {
    request: requestSchema,
    transition_id: tool.schema.string().min(1),
    event_type: tool.schema.string().min(1),
    payload_json: tool.schema.string().min(2),
    expected_state_revision: revisionSchema,
  },
  execute: (args, context) => withStore(args.request, context, async (store) => {
    let payload: unknown
    try {
      payload = parseJsonStrict(args.payload_json)
    } catch (error) {
      throw new ProtocolError("payload_json", "invalid JSON", error instanceof Error ? error.message : String(error))
    }
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new ProtocolError("payload_json", "root must be an object")
    const event: EventInput = { transition_id: args.transition_id, type: args.event_type, payload: payload as Record<string, unknown> }
    const { state, result } = await store.apply(event, args.expected_state_revision)
    return { state_revision: state.state_revision, status: state.status, result }
  }),
})

export const validate = tool({
  description: "Validate technical-analysis state and artifacts without advancing the workflow.",
  args: { request: requestSchema },
  execute: (args, context) => withStore(args.request, context, async (store) => ({ validation: await store.validate() })),
})
'''


prepare.step7_runtime.RELEASE_GATES_TEST = r'''
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
'''


CLI_TEST = r'''
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "opencode-agents.py"
VERSION = "6.0.1"
AGENTS = [
    "orchestrator-analyst.md",
    "orchestrator-discovery.md",
    "orchestrator-stage-planner.md",
    "orchestrator-stage-reviewer.md",
]

SPEC = importlib.util.spec_from_file_location("opencode_agents", CLI)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load installer")
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)


class InstallerTests(unittest.TestCase):
    def run_cli(self, target: Path, command: str, *extra: str, check: bool = True):
        arguments = [sys.executable, str(CLI), command, "--target", str(target)]
        if command != "status":
            arguments.extend(["--source", str(ROOT)])
        arguments.extend(extra)
        return subprocess.run(arguments, text=True, capture_output=True, check=check)

    def test_release_inventory(self):
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(INSTALLER.VERSION, VERSION)
        self.assertEqual(package["version"], VERSION)
        self.assertEqual(sorted(path.name for path in (ROOT / "agents").glob("*.md")), AGENTS)
        self.assertTrue((ROOT / "tools/orchestrator.ts").is_file())
        self.assertTrue((ROOT / "runtime/orchestrator.js").is_file())
        self.assertTrue((ROOT / "runtime/orchestrator.d.ts").is_file())
        self.assertFalse((ROOT / "runtime/orchestrator.py").exists())
        self.assertFalse((ROOT / "orchestrator_core").exists())
        self.assertFalse((ROOT / "runtime/orchestrator_core").exists())

    def test_fresh_install_and_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "config"
            installed = self.run_cli(target, "install")
            self.assertEqual(installed.returncode, 0, installed.stderr)
            for relative in [
                "agents/orchestrator-analyst.md",
                "tools/orchestrator.ts",
                "runtime/orchestrator.js",
                "runtime/orchestrator.d.ts",
                ".opencode-agents-manifest.json",
            ]:
                self.assertTrue((target / relative).is_file(), relative)
            status = self.run_cli(target, "status", check=False)
            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            payload = json.loads(status.stdout)
            self.assertTrue(payload["installed"])
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["missing"], [])
            self.assertEqual(payload["modified"], [])

    def test_second_install_is_rejected_and_update_replaces_with_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "config"
            backup = root / "backup"
            self.run_cli(target, "install")
            analyst = target / "agents/orchestrator-analyst.md"
            analyst.write_text("local modification\n", encoding="utf-8")

            second_install = self.run_cli(target, "install", check=False)
            self.assertEqual(second_install.returncode, 2)
            self.assertIn("use update", second_install.stderr.lower())
            self.assertEqual(analyst.read_text(encoding="utf-8"), "local modification\n")

            self.run_cli(target, "update", "--backup", str(backup))
            self.assertEqual(analyst.read_bytes(), (ROOT / "agents/orchestrator-analyst.md").read_bytes())
            self.assertEqual((backup / "agents/orchestrator-analyst.md").read_text(encoding="utf-8"), "local modification\n")

    def test_update_preserves_unknown_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "config"
            self.run_cli(target, "install")
            custom = target / "tools/custom.ts"
            custom.write_text("export const custom = true\n", encoding="utf-8")
            self.run_cli(target, "update")
            self.assertEqual(custom.read_text(encoding="utf-8"), "export const custom = true\n")


if __name__ == "__main__":
    unittest.main()
'''


_original_build_apply = prepare.step7_build.apply


def build_with_6_0_1_contract_tests(root, log):
    changed = prepare.step7_build.write_files(
        root,
        {"tests/test_cli.py": CLI_TEST},
    )
    return changed + _original_build_apply(root, log)


prepare.step7_build.apply = build_with_6_0_1_contract_tests
