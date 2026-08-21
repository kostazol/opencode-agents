import { constants as fsConstants } from "node:fs"
import { access, mkdir, open, readFile, rename, rm, stat, writeFile } from "node:fs/promises"
import path from "node:path"
import { setTimeout as delay } from "node:timers/promises"
import { Analysis, EventInput, JsonRecord, ProtocolError, State, clone, parseJsonStrict, record, validateAnalysis } from "./orchestrator.js"
import { applyEvent } from "./events.js"
import { parseLegacyPlan, renderPlan } from "./render.js"
import { reserveNext } from "./routing.js"
import { newState, validateState } from "./state.js"

function isWithin(base: string, candidate: string): boolean {
  const relative = path.relative(path.resolve(base), path.resolve(candidate))
  return relative === "" || (!relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative))
}

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
    if (await exists(this.statePath)) return validateState(await parseJsonFile(this.statePath))
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
      const result = reserveNext(state, analysis, expectedStateRevision)
      if (JSON.stringify(result.state) !== JSON.stringify(state)) await this.commit(result.state, analysis, this.journal("reserve", result.state, result.action))
      return result
    })
  }

  async apply(event: EventInput, expectedStateRevision?: number): Promise<{ state: State; result: JsonRecord }> {
    return this.withLock(async () => {
      const state = await this.loadState()
      const analysis = await this.loadAnalysis()
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
      if (state.legacy_migrated && !(await exists(this.statePath))) {
        await this.commit(state, analysis, this.journal("migrate", state, { transition_id: null, source: "legacy-plan.md" }))
      }
      const issues: string[] = []
      const expected = renderPlan(state, analysis)
      if (await exists(this.planPath) && await readFile(this.planPath, "utf8") !== expected) issues.push("plan.md differs from deterministic rendering")
      if (["review", "reviewed", "approved"].includes(state.analysis_status) && !analysis) issues.push("analysis.json is required by current state")
      return { valid: !issues.length, state_revision: state.state_revision, status: state.status, pending: state.pending, issues }
    })
  }
}
