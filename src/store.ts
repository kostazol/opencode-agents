
import { constants as fsConstants } from "node:fs"
import { access, mkdir, open, readFile, rename, rm, stat } from "node:fs/promises"
import path from "node:path"
import { setTimeout as delay } from "node:timers/promises"
import type { Analysis, EventInput, JsonRecord, State } from "./schema.js"
import { ProtocolError, clone, parseJsonStrict, record } from "./schema.js"
import { validateAnalysis } from "./analysis.js"
import { assertCompleteArtifactGraph, assertInputSnapshotsCurrent, assertPendingOutputContracts, capturePendingSnapshots } from "./artifacts.js"
import { applyEvent } from "./events.js"
import { parseLegacyPlan, renderPlan } from "./render.js"
import { reserveNext } from "./routing.js"
import { migrateState, newState, validateState } from "./state.js"

async function exists(candidate: string): Promise<boolean> {
  try {
    await access(candidate, fsConstants.F_OK)
    return true
  } catch {
    return false
  }
}

async function atomicWrite(candidate: string, content: string): Promise<void> {
  await mkdir(path.dirname(candidate), { recursive: true })
  const temporary = path.join(path.dirname(candidate), `.${path.basename(candidate)}.${process.pid}.${Date.now()}.tmp`)
  const handle = await open(temporary, "wx", 0o600)
  try {
    await handle.writeFile(content, "utf8")
    await handle.sync()
  } finally {
    await handle.close()
  }
  try {
    await rename(temporary, candidate)
  } catch (error) {
    const code = (error as { code?: string }).code
    if (!new Set(["EEXIST", "EPERM", "EACCES"]).has(code ?? "")) throw error
    await rm(candidate, { force: true })
    await rename(temporary, candidate)
  } finally {
    await rm(temporary, { force: true })
  }
}

async function parseJsonFile(candidate: string): Promise<unknown> {
  let content: string
  try {
    content = await readFile(candidate, "utf8")
  } catch (error) {
    throw new ProtocolError(candidate, "cannot read JSON", String(error))
  }
  try {
    return parseJsonStrict(content)
  } catch (error) {
    if (error instanceof ProtocolError) throw error
    throw new ProtocolError(candidate, "invalid JSON", String(error))
  }
}

async function appendJournal(candidate: string, entry: JsonRecord): Promise<void> {
  const entries: JsonRecord[] = []
  if (await exists(candidate)) {
    for (const [index, line] of (await readFile(candidate, "utf8")).split(/\r?\n/).filter(Boolean).entries()) {
      try {
        entries.push(record(parseJsonStrict(line), `journal[${index}]`))
      } catch (error) {
        throw new ProtocolError(`journal[${index}]`, "invalid JSON", String(error))
      }
    }
  }
  if (entries.some((item) => item.entry_id === entry.entry_id)) return
  entries.push(entry)
  await atomicWrite(candidate, entries.map((item) => JSON.stringify(item)).join("\n") + "\n")
}

export class WorkflowStore {
  readonly base: string
  readonly root: string
  readonly internal: string
  readonly statePath: string
  readonly planPath: string
  readonly analysisPath: string
  readonly journalPath: string
  readonly transactionPath: string
  readonly lockPath: string
  readonly stateV1BackupPath: string
  readonly request: string

  constructor(directory: string, request: string) {
    newState(request)
    this.base = path.resolve(directory)
    this.root = path.resolve(this.base, "1_orchestrator", request)
    const expectedParent = path.resolve(this.base, "1_orchestrator")
    if (path.dirname(this.root) !== expectedParent) throw new ProtocolError("workflow_root", "request path escapes workflow base", this.root)
    this.request = request
    this.internal = path.join(this.root, ".orchestrator")
    this.statePath = path.join(this.internal, "state.json")
    this.planPath = path.join(this.root, "plan.md")
    this.analysisPath = path.join(this.root, "analysis.json")
    this.journalPath = path.join(this.internal, "journal.jsonl")
    this.transactionPath = path.join(this.internal, "transaction.json")
    this.lockPath = path.join(this.internal, "lock")
    this.stateV1BackupPath = path.join(this.internal, "state-v1.json")
  }

  private async ensureRoot(): Promise<void> {
    await mkdir(this.internal, { recursive: true })
    const resolved = path.resolve(this.root)
    if (path.dirname(resolved) !== path.resolve(this.base, "1_orchestrator")) throw new ProtocolError("workflow_root", "resolved request path escapes workflow base")
  }

  private async withLock<T>(operation: () => Promise<T>, timeoutMs = 5000, staleMs = 300000): Promise<T> {
    await this.ensureRoot()
    const deadline = Date.now() + timeoutMs
    while (true) {
      try {
        const handle = await open(this.lockPath, "wx", 0o600)
        await handle.writeFile(JSON.stringify({ pid: process.pid, created_at: new Date().toISOString() }))
        await handle.close()
        break
      } catch (error) {
        if ((error as { code?: string }).code !== "EEXIST") throw error
        try {
          if (Date.now() - (await stat(this.lockPath)).mtimeMs > staleMs) {
            await rm(this.lockPath, { force: true })
            continue
          }
        } catch {
          continue
        }
        if (Date.now() >= deadline) throw new ProtocolError("workflow_lock", "request is already being advanced")
        await delay(25)
      }
    }
    try {
      return await operation()
    } finally {
      await rm(this.lockPath, { force: true })
    }
  }

  private async recover(): Promise<boolean> {
    if (!(await exists(this.transactionPath))) return false
    const transaction = record(await parseJsonFile(this.transactionPath), "transaction")
    if (transaction.schema_version !== 1) throw new ProtocolError("transaction.schema_version", "unsupported transaction")
    await atomicWrite(this.statePath, `${JSON.stringify(transaction.state, null, 2)}\n`)
    if (typeof transaction.plan !== "string" || !transaction.plan.trim()) throw new ProtocolError("transaction.plan", "must be a non-empty string")
    await atomicWrite(this.planPath, transaction.plan)
    await appendJournal(this.journalPath, record(transaction.journal, "transaction.journal"))
    await rm(this.transactionPath, { force: true })
    return true
  }

  private async loadState(): Promise<State> {
    await this.ensureRoot()
    await this.recover()
    if (await exists(this.statePath)) {
      const raw = await parseJsonFile(this.statePath)
      const migration = migrateState(raw)
      const state = validateState(migration.state)
      if (migration.migrated) {
        if (!(await exists(this.stateV1BackupPath))) await atomicWrite(this.stateV1BackupPath, `${JSON.stringify(raw, null, 2)}\n`)
        await atomicWrite(this.statePath, `${JSON.stringify(state, null, 2)}\n`)
        await appendJournal(this.journalPath, {
          entry_id: `state-schema:${migration.from_version}-${migration.to_version}:${state.state_revision}`,
          timestamp: new Date().toISOString(),
          action: "state_schema_migration",
          state_revision: state.state_revision,
          transition_id: migration.invalidated_transition,
          detail: clone(migration as unknown as JsonRecord),
        })
      }
      return state
    }
    if (await exists(this.planPath)) return parseLegacyPlan(await readFile(this.planPath, "utf8"), this.request)
    return newState(this.request)
  }

  private async loadAnalysis(): Promise<Analysis | undefined> {
    return await exists(this.analysisPath) ? validateAnalysis(await parseJsonFile(this.analysisPath)) : undefined
  }

  private journal(action: string, state: State, detail: JsonRecord): JsonRecord {
    const transition = typeof detail.transition_id === "string" ? detail.transition_id : "state"
    return {
      entry_id: `${transition}:${action}:${state.state_revision}`,
      timestamp: new Date().toISOString(),
      action,
      state_revision: state.state_revision,
      transition_id: detail.transition_id ?? null,
      detail: clone(detail),
    }
  }

  private async commit(state: State, analysis: Analysis | undefined, journal: JsonRecord): Promise<void> {
    const validated = validateState(state, analysis && state.stages.length && !state.legacy_migrated ? analysis : undefined)
    const plan = renderPlan(validated, analysis)
    const transaction = { schema_version: 1, state: validated, plan, journal }
    await atomicWrite(this.transactionPath, `${JSON.stringify(transaction, null, 2)}\n`)
    await atomicWrite(this.statePath, `${JSON.stringify(validated, null, 2)}\n`)
    await atomicWrite(this.planPath, plan)
    await appendJournal(this.journalPath, journal)
    await rm(this.transactionPath, { force: true })
  }

  async reserve(expectedStateRevision?: number): Promise<{ state: State; action: JsonRecord }> {
    return this.withLock(async () => {
      const state = await this.loadState()
      const analysis = await this.loadAnalysis()
      if (state.status === "waiting_plan_approval" || state.status === "ready") await assertCompleteArtifactGraph(this.root, state, analysis)
      const result = reserveNext(state, analysis, expectedStateRevision)
      if (result.state.pending && !result.state.pending.snapshots_captured) {
        const projectedPlan = renderPlan(result.state, analysis)
        await capturePendingSnapshots(this.root, result.state.pending, { "plan.md": projectedPlan })
        result.action = clone(result.state.pending) as unknown as JsonRecord
      }
      if (JSON.stringify(result.state) !== JSON.stringify(state)) await this.commit(result.state, analysis, this.journal("reserve", result.state, result.action))
      return result
    })
  }

  async apply(event: EventInput, expectedStateRevision?: number): Promise<{ state: State; result: JsonRecord }> {
    return this.withLock(async () => {
      const state = await this.loadState()
      const analysis = await this.loadAnalysis()
      if (!state.pending) throw new ProtocolError("state.pending", "event cannot be applied without a pending transition")
      await assertInputSnapshotsCurrent(this.root, state.pending)
      await assertPendingOutputContracts(this.root, state, event, analysis)
      const payload = record(event.payload, "event.payload")
      if (state.pending.action === "APPROVE_PLAN" && payload.decision === "APPROVE") await assertCompleteArtifactGraph(this.root, state, analysis)
      const result = await applyEvent(this.base, state, event, analysis, expectedStateRevision)
      if (JSON.stringify(result.state) !== JSON.stringify(state)) await this.commit(result.state, analysis, this.journal("apply", result.state, { transition_id: event.transition_id, event_type: event.type, result: result.result }))
      return result
    })
  }

  async validate(): Promise<JsonRecord> {
    return this.withLock(async () => {
      const state = await this.loadState()
      const analysis = await this.loadAnalysis()
      validateState(state, analysis && state.stages.length && !state.legacy_migrated ? analysis : undefined)
      if (state.legacy_migrated && !(await exists(this.statePath))) await this.commit(state, analysis, this.journal("migrate", state, { transition_id: null, source: "legacy-plan.md" }))
      const issues: string[] = []
      const expected = renderPlan(state, analysis)
      if (await exists(this.planPath) && await readFile(this.planPath, "utf8") !== expected) issues.push("plan.md differs from deterministic rendering")
      if (["review", "reviewed", "approved"].includes(state.analysis_status) && !analysis) issues.push("analysis.json is required by current state")
      if (state.status === "waiting_plan_approval" || state.status === "ready") {
        try {
          await assertCompleteArtifactGraph(this.root, state, analysis)
        } catch (error) {
          issues.push(error instanceof Error ? error.message : String(error))
        }
      }
      return { valid: !issues.length, state_revision: state.state_revision, status: state.status, pending: state.pending, issues }
    })
  }
}
