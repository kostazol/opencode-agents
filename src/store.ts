
import { constants as fsConstants } from "node:fs"
import { access, lstat, mkdir, open, readFile, realpath, rename, rm, stat } from "node:fs/promises"
import path from "node:path"
import { setTimeout as delay } from "node:timers/promises"
import type { Analysis, EventInput, JsonRecord, State } from "./schema.js"
import { ProtocolError, clone, integer, parseJsonStrict, record } from "./schema.js"
import { semanticStageFingerprint, validateAnalysis } from "./analysis.js"
import { assertArtifact, assertCompleteArtifactGraph, assertInputSnapshotsCurrent, assertPendingOutputContracts, capturePendingSnapshots } from "./artifacts.js"
import { applyEvent } from "./events.js"
import { parseLegacyPlan, parseLegacySnapshot, renderPlan } from "./render.js"
import type { LegacySnapshot } from "./render.js"
import { reserveNext } from "./routing.js"
import { migrateState, newState, normalizeProgress, stableJson, validateState } from "./state.js"

async function exists(candidate: string): Promise<boolean> {
  try { await access(candidate, fsConstants.F_OK); return true } catch { return false }
}

function within(base: string, candidate: string): boolean {
  const relative = path.relative(path.resolve(base), path.resolve(candidate))
  return relative === "" || (relative !== ".." && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative))
}

async function atomicWrite(candidate: string, content: string): Promise<void> {
  await mkdir(path.dirname(candidate), { recursive: true })
  if (await exists(candidate) && (await lstat(candidate)).isSymbolicLink()) throw new ProtocolError(candidate, "refusing to replace a symlink")
  const temporary = path.join(path.dirname(candidate), `.${path.basename(candidate)}.${process.pid}.${Date.now()}.tmp`)
  const handle = await open(temporary, "wx", 0o600)
  try { await handle.writeFile(content, "utf8"); await handle.sync() } finally { await handle.close() }
  try { await rename(temporary, candidate) }
  catch (error) {
    const code = (error as { code?: string }).code
    if (!new Set(["EEXIST", "EPERM", "EACCES"]).has(code ?? "")) throw error
    await rm(candidate, { force: true })
    await rename(temporary, candidate)
  } finally { await rm(temporary, { force: true }) }
}

async function parseJsonFile(candidate: string): Promise<unknown> {
  let content: string
  try { content = await readFile(candidate, "utf8") } catch (error) { throw new ProtocolError(candidate, "cannot read JSON", String(error)) }
  return parseJsonStrict(content)
}

async function appendJournal(candidate: string, entry: JsonRecord): Promise<void> {
  const entries: JsonRecord[] = []
  if (await exists(candidate)) {
    for (const [index, line] of (await readFile(candidate, "utf8")).split(/\r?\n/).filter(Boolean).entries()) entries.push(record(parseJsonStrict(line), `journal[${index}]`))
  }
  const existing = entries.find((item) => item.entry_id === entry.entry_id)
  if (existing) {
    if (stableJson(existing) !== stableJson(entry)) throw new ProtocolError("journal.entry_id", "journal conflict: duplicate entry_id has different content", entry.entry_id)
    return
  }
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
  readonly legacyBackupPath: string
  readonly legacySnapshotPath: string
  readonly request: string

  constructor(directory: string, request: string) {
    newState(request)
    this.base = path.resolve(directory)
    this.root = path.resolve(this.base, "1_orchestrator", request)
    if (path.dirname(this.root) !== path.resolve(this.base, "1_orchestrator")) throw new ProtocolError("workflow_root", "request path escapes workflow base", this.root)
    this.request = request
    this.internal = path.join(this.root, ".orchestrator")
    this.statePath = path.join(this.internal, "state.json")
    this.planPath = path.join(this.root, "plan.md")
    this.analysisPath = path.join(this.root, "analysis.json")
    this.journalPath = path.join(this.internal, "journal.jsonl")
    this.transactionPath = path.join(this.internal, "transaction.json")
    this.lockPath = path.join(this.internal, "lock")
    this.stateV1BackupPath = path.join(this.internal, "state-v1.json")
    this.legacyBackupPath = path.join(this.internal, "legacy-plan.md")
    this.legacySnapshotPath = path.join(this.internal, "legacy-state.json")
  }

  private async ensureRoot(): Promise<void> {
    const parent = path.resolve(this.base, "1_orchestrator")
    await mkdir(parent, { recursive: true })
    await mkdir(this.internal, { recursive: true })
    const resolvedParent = await realpath(parent)
    const resolvedRoot = await realpath(this.root)
    if (!within(resolvedParent, resolvedRoot) || resolvedRoot === resolvedParent) throw new ProtocolError("workflow_root", "resolved request root escapes 1_orchestrator", resolvedRoot)
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
        const info = await lstat(this.lockPath)
        if (info.isSymbolicLink()) throw new ProtocolError("workflow_lock", "lock path is a symlink")
        if (Date.now() - info.mtimeMs > staleMs) { await rm(this.lockPath, { force: true }); continue }
        if (Date.now() >= deadline) throw new ProtocolError("workflow_lock", "request is already being advanced")
        await delay(25)
      }
    }
    try { return await operation() } finally { await rm(this.lockPath, { force: true }) }
  }

  private async recover(): Promise<boolean> {
    if (!(await exists(this.transactionPath))) return false
    const transaction = record(await parseJsonFile(this.transactionPath), "transaction")
    if (transaction.schema_version !== 2) throw new ProtocolError("transaction.schema_version", "unsupported transaction", transaction.schema_version)
    const baseRevision = integer(transaction.base_state_revision, "transaction.base_state_revision")
    const target = validateState(transaction.state)
    if (typeof transaction.plan !== "string" || !transaction.plan.trim()) throw new ProtocolError("transaction.plan", "must be a non-empty string")
    const current = await exists(this.statePath) ? validateState(await parseJsonFile(this.statePath)) : null
    if (current) {
      if (current.state_revision === target.state_revision) {
        if (stableJson(current) !== stableJson(target)) throw new ProtocolError("transaction.state", "journal recovery conflict at target revision")
      } else if (current.state_revision === baseRevision) await atomicWrite(this.statePath, `${JSON.stringify(target, null, 2)}\n`)
      else throw new ProtocolError("transaction.base_state_revision", "journal recovery conflict", { base: baseRevision, current: current.state_revision, target: target.state_revision })
    } else {
      if (baseRevision !== 0) throw new ProtocolError("transaction.base_state_revision", "missing base state for recovery", baseRevision)
      await atomicWrite(this.statePath, `${JSON.stringify(target, null, 2)}\n`)
    }
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
        await appendJournal(this.journalPath, { entry_id: `state-schema:${migration.from_version}-${migration.to_version}:${state.state_revision}`, timestamp: new Date().toISOString(), action: "state_schema_migration", state_revision: state.state_revision, transition_id: migration.invalidated_transition, detail: clone(migration as unknown as JsonRecord) })
      }
      return state
    }
    if (await exists(this.planPath)) {
      const content = await readFile(this.planPath, "utf8")
      if (!(await exists(this.legacyBackupPath))) await atomicWrite(this.legacyBackupPath, content)
      const snapshot = parseLegacySnapshot(content, this.request)
      await atomicWrite(this.legacySnapshotPath, `${JSON.stringify(snapshot, null, 2)}\n`)
      return parseLegacyPlan(content, this.request)
    }
    return newState(this.request)
  }

  private async loadLegacySnapshot(): Promise<LegacySnapshot | undefined> {
    return await exists(this.legacySnapshotPath) ? await parseJsonFile(this.legacySnapshotPath) as LegacySnapshot : undefined
  }

  private async restoreLegacyPasses(state: State, analysis: Analysis): Promise<void> {
    const snapshot = await this.loadLegacySnapshot()
    if (!snapshot) { state.legacy_migrated = false; return }
    for (const stage of state.stages) {
      const legacy = snapshot.stages.find((item) => item.id === stage.id)
      if (!legacy || legacy.status !== "pass" || !legacy.semantic_fingerprint || legacy.semantic_fingerprint !== semanticStageFingerprint(analysis, stage.id)) continue
      const revision = Math.max(1, legacy.revision)
      try {
        await assertArtifact(this.root, stage.details, { artifact: "technical-stage", stage: stage.id, revision, source_revision: state.analysis_revision, status: "REVIEW" })
        await assertArtifact(this.root, stage.review, { artifact: "technical-review", stage: stage.id, revision, source_revision: revision, status: "PASS" })
      } catch { continue }
      stage.status = "pass"
      stage.revision = revision
      if (legacy.human_status === "pass") {
        const humanRevision = Math.max(1, legacy.human_revision)
        try {
          await assertArtifact(this.root, stage.human_review, { artifact: "human-review", stage: stage.id, revision: humanRevision, source_revision: revision, status: "REVIEW" })
          await assertArtifact(this.root, stage.human_review_review, { artifact: "human-review-review", stage: stage.id, revision: humanRevision, source_revision: revision, status: "PASS" })
          stage.human_status = "pass"
          stage.human_revision = humanRevision
        } catch { stage.human_status = "pending"; stage.human_revision = 0 }
      }
    }
    state.legacy_migrated = false
    normalizeProgress(state)
    if (state.status === "planning") state.current_stage = state.stages.find((stage) => stage.status !== "pass")?.id ?? state.current_stage
    if (state.status === "human_reviewing") state.current_stage = state.stages.find((stage) => stage.human_status !== "pass")?.id ?? state.current_stage
  }

  private async loadAnalysis(): Promise<Analysis | undefined> {
    return await exists(this.analysisPath) ? validateAnalysis(await parseJsonFile(this.analysisPath)) : undefined
  }

  private journal(action: string, state: State, detail: JsonRecord): JsonRecord {
    const transition = typeof detail.transition_id === "string" ? detail.transition_id : "state"
    return { entry_id: `${transition}:${action}:${state.state_revision}`, timestamp: new Date().toISOString(), action, state_revision: state.state_revision, transition_id: detail.transition_id ?? null, detail: clone(detail) }
  }

  private async commit(baseStateRevision: number, state: State, analysis: Analysis | undefined, journal: JsonRecord): Promise<void> {
    const validated = validateState(state, analysis && state.stages.length && !state.legacy_migrated ? analysis : undefined)
    const plan = renderPlan(validated, analysis)
    const transaction = { schema_version: 2, base_state_revision: baseStateRevision, state: validated, plan, journal }
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
      if (stableJson(result.state) !== stableJson(state)) await this.commit(state.state_revision, result.state, analysis, this.journal("reserve", result.state, result.action))
      return result
    })
  }

  async apply(event: EventInput, expectedStateRevision?: number): Promise<{ state: State; result: JsonRecord }> {
    return this.withLock(async () => {
      const state = await this.loadState()
      const analysis = await this.loadAnalysis()
      if (!state.pending) {
        if (state.applied[event.transition_id]) return applyEvent(this.base, state, event, analysis, undefined)
        throw new ProtocolError("state.pending", "event cannot be applied without a pending transition")
      }
      await assertInputSnapshotsCurrent(this.root, state.pending)
      await assertPendingOutputContracts(this.root, state, event, analysis)
      const payload = record(event.payload, "event.payload")
      if (state.pending.action === "APPROVE_PLAN" && String(payload.decision).toUpperCase() === "APPROVE") await assertCompleteArtifactGraph(this.root, state, analysis)
      const result = await applyEvent(this.base, state, event, analysis, expectedStateRevision)
      if (event.type === "map_decision" && String(payload.decision).toUpperCase() === "APPROVE" && result.state.legacy_migrated && analysis) await this.restoreLegacyPasses(result.state, analysis)
      if (result.state.status === "ready") await assertCompleteArtifactGraph(this.root, result.state, analysis)
      if (stableJson(result.state) !== stableJson(state)) await this.commit(state.state_revision, result.state, analysis, this.journal("apply", result.state, { transition_id: event.transition_id, event_type: event.type, result: result.result }))
      return result
    })
  }

  async validate(): Promise<JsonRecord> {
    return this.withLock(async () => {
      const state = await this.loadState()
      const analysis = await this.loadAnalysis()
      validateState(state, analysis && state.stages.length && !state.legacy_migrated ? analysis : undefined)
      if (state.legacy_migrated && !(await exists(this.statePath))) await this.commit(0, state, analysis, this.journal("migrate", state, { transition_id: null, source: "legacy-plan.md" }))
      const issues: string[] = []
      const expected = renderPlan(state, analysis)
      if (await exists(this.planPath) && await readFile(this.planPath, "utf8") !== expected) issues.push("plan.md differs from deterministic rendering")
      if (["review", "reviewed", "approved"].includes(state.analysis_status) && !analysis) issues.push("analysis.json is required by current state")
      if (state.status === "waiting_plan_approval" || state.status === "ready") {
        try { await assertCompleteArtifactGraph(this.root, state, analysis) } catch (error) { issues.push(error instanceof Error ? error.message : String(error)) }
      }
      return { valid: !issues.length, state_revision: state.state_revision, status: state.status, pending: state.pending, issues }
    })
  }
}
