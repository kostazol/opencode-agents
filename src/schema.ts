
import path from "node:path"

export const ANALYSIS_SCHEMA_VERSION = 1
export const STATE_SCHEMA_VERSION = 2
export const REPEAT_LIMIT = 2

export const CHANGE_SURFACES = new Set(["api", "data", "ui", "infra", "security", "migration", "background", "library"])
export const NFR_CATEGORIES = new Set([
  "performance-capacity",
  "availability-recovery",
  "security-privacy-compliance",
  "data-integrity-concurrency",
  "compatibility-migration",
  "observability-support",
  "rollout-rollback",
  "accessibility-localization",
  "cost-resources",
])
export const SURFACE_NFR: Record<string, string[]> = {
  api: ["performance-capacity", "availability-recovery", "security-privacy-compliance", "compatibility-migration", "observability-support"],
  data: ["data-integrity-concurrency", "compatibility-migration", "availability-recovery", "observability-support"],
  ui: ["performance-capacity", "accessibility-localization", "compatibility-migration"],
  infra: ["availability-recovery", "observability-support", "rollout-rollback", "cost-resources", "security-privacy-compliance"],
  security: ["security-privacy-compliance", "observability-support"],
  migration: ["compatibility-migration", "data-integrity-concurrency", "rollout-rollback", "availability-recovery"],
  background: ["availability-recovery", "data-integrity-concurrency", "observability-support", "cost-resources"],
  library: ["compatibility-migration"],
}

export const WORKFLOW_STATUSES = new Set([
  "discovery",
  "discovery_review",
  "waiting_answers",
  "waiting_map_approval",
  "planning",
  "human_reviewing",
  "waiting_plan_approval",
  "waiting_reopen_approval",
  "ready",
  "blocked",
])
export const STAGE_STATUSES = new Set(["proposed", "planning", "review", "pass"])
export const HUMAN_STATUSES = new Set(["pending", "planning", "review", "pass"])
export const AGENT_ACTIONS = new Set(["DISCOVER", "REVIEW_DISCOVERY", "PLAN_STAGE", "REVIEW_STAGE", "PLAN_HUMAN_REVIEW", "REVIEW_HUMAN_REVIEW"])
export const EVENT_BY_ACTION: Record<string, string> = {
  DISCOVER: "discovery_result",
  REVIEW_DISCOVERY: "discovery_review_result",
  ASK_QUESTIONS: "answers",
  APPROVE_MAP: "map_decision",
  PLAN_STAGE: "stage_plan_result",
  REVIEW_STAGE: "stage_review_result",
  PLAN_HUMAN_REVIEW: "human_plan_result",
  REVIEW_HUMAN_REVIEW: "human_review_result",
  APPROVE_PLAN: "plan_decision",
  APPROVE_REOPEN: "reopen_decision",
  RESOLVE_BLOCKER: "blocker_resolution",
}

export type JsonRecord = Record<string, unknown>
export type WorkflowStatus =
  | "discovery"
  | "discovery_review"
  | "waiting_answers"
  | "waiting_map_approval"
  | "planning"
  | "human_reviewing"
  | "waiting_plan_approval"
  | "waiting_reopen_approval"
  | "ready"
  | "blocked"

export interface AnalysisStage {
  id: string
  title: string
  slug: string
  depends_on: string[]
  requirements: string[]
  nfrs: string[]
  contracts_consumed: string[]
  contracts_produced: string[]
  affected_area: string
  risks: string[]
}

export interface Analysis {
  schema_version: number
  request: { summary: string; outcomes: string[] }
  change_surfaces: string[]
  requirements: Array<{ id: string; text: string; stage: string; acceptance: string[]; scenarios: string[] }>
  nfrs: Array<{ id: string; text: string; category: string; stage: string; acceptance: string[]; scenarios: string[] }>
  decisions: Array<{ id: string; text: string }>
  contracts: Array<{ id: string; text: string; producer: string | null; consumers: string[]; external: boolean; terminal: boolean }>
  acceptance: Array<{ id: string; text: string; stage: string; verification: string }>
  scenarios: Array<{ id: string; text: string; stage: string; requirements: string[]; expected: string }>
  nfr_applicability: Array<{ category: string; status: "required" | "not_applicable" | "deferred"; evidence: string; owner: string | null; acceptance: string[] }>
  stages: AnalysisStage[]
  assumptions: string[]
  non_goals: string[]
}

export interface StageState {
  id: string
  title: string
  slug: string
  depends_on: string[]
  status: "proposed" | "planning" | "review" | "pass"
  revision: number
  human_status: "pending" | "planning" | "review" | "pass"
  human_revision: number
  details: string
  review: string
  human_review: string
  human_review_review: string
}

export interface RevisionMetadata {
  schema_version: number | null
  artifact: string | null
  stage: string | null
  revision: number | null
  source_revision: number | null
  status: string | null
}

export interface ArtifactSnapshot {
  path: string
  exists: boolean
  digest: string | null
  metadata: RevisionMetadata | null
}

export interface PendingAction {
  transition_id: string
  action: string
  actor: string
  mode: string | null
  stage: string | null
  revision: number | null
  source_revision: number | null
  inputs: string[]
  input_snapshot: ArtifactSnapshot[]
  output: string | null
  output_snapshot: ArtifactSnapshot | null
  snapshots_captured: boolean
  reason: string
  issued_state_revision: number
}

export interface State {
  schema_version: number
  request_id: string
  state_revision: number
  sequence: number
  status: WorkflowStatus
  current_stage: string | null
  analysis_revision: number
  analysis_status: "missing" | "draft" | "review" | "reviewed" | "approved"
  question_revision: number
  feedback_revision: number
  stages: StageState[]
  pending: PendingAction | null
  applied: Record<string, { event_digest: string; result: JsonRecord }>
  blocker: null | { reason: string; detail: string; resume_status: WorkflowStatus; retryable: boolean; source_transition: string }
  reopen: null | { requested_by: "reviewer" | "user"; reason: string; seeds: string[]; affected: string[]; resume_status: WorkflowStatus; resume_stage: string | null }
  convergence: Record<string, { fingerprint: string; evidence_digest: string; repeats: number; last_revision: number }>
  legacy_migrated: boolean
}

export interface EventInput {
  transition_id: string
  type: string
  payload: JsonRecord
}

export class ProtocolError extends Error {
  readonly field: string
  readonly value: unknown

  constructor(field: string, message: string, value?: unknown) {
    super(`${field}: ${message}${value === undefined ? "" : `; value=${JSON.stringify(value)}`}`)
    this.name = "ProtocolError"
    this.field = field
    this.value = value
  }
}

export function parseJsonStrict(source: string): unknown {
  let index = 0

  function skipWhitespace(): void {
    while (index < source.length && /\s/.test(source[index])) index += 1
  }

  function parseString(field: string): string {
    if (source[index] !== '"') throw new ProtocolError(field, "expected JSON string")
    const start = index
    index += 1
    while (index < source.length) {
      const character = source[index]
      if (character === '"') {
        index += 1
        try {
          return JSON.parse(source.slice(start, index)) as string
        } catch (error) {
          throw new ProtocolError(field, "invalid JSON string", String(error))
        }
      }
      if (character === "\\") {
        index += 2
        continue
      }
      if (character.charCodeAt(0) < 0x20) throw new ProtocolError(field, "control character in JSON string")
      index += 1
    }
    throw new ProtocolError(field, "unterminated JSON string")
  }

  function parseValue(field: string): unknown {
    skipWhitespace()
    const character = source[index]
    if (character === "{") return parseObject(field)
    if (character === "[") return parseArray(field)
    if (character === '"') return parseString(field)
    for (const [literal, value] of [["true", true], ["false", false], ["null", null]] as const) {
      if (source.startsWith(literal, index)) {
        index += literal.length
        return value
      }
    }
    const match = source.slice(index).match(/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/)
    if (match) {
      index += match[0].length
      const value = Number(match[0])
      if (!Number.isFinite(value)) throw new ProtocolError(field, "JSON number is not finite", match[0])
      return value
    }
    throw new ProtocolError(field, "unexpected JSON token", source.slice(index, index + 20))
  }

  function parseObject(field: string): JsonRecord {
    index += 1
    const result: JsonRecord = {}
    const keys = new Set<string>()
    skipWhitespace()
    if (source[index] === "}") {
      index += 1
      return result
    }
    while (index < source.length) {
      skipWhitespace()
      const key = parseString(`${field}.key`)
      if (keys.has(key)) throw new ProtocolError(`${field}.${key}`, "duplicate JSON key")
      keys.add(key)
      skipWhitespace()
      if (source[index] !== ":") throw new ProtocolError(`${field}.${key}`, "expected ':'")
      index += 1
      result[key] = parseValue(`${field}.${key}`)
      skipWhitespace()
      if (source[index] === "}") {
        index += 1
        return result
      }
      if (source[index] !== ",") throw new ProtocolError(field, "expected ',' or '}'")
      index += 1
    }
    throw new ProtocolError(field, "unterminated JSON object")
  }

  function parseArray(field: string): unknown[] {
    index += 1
    const result: unknown[] = []
    skipWhitespace()
    if (source[index] === "]") {
      index += 1
      return result
    }
    while (index < source.length) {
      result.push(parseValue(`${field}[${result.length}]`))
      skipWhitespace()
      if (source[index] === "]") {
        index += 1
        return result
      }
      if (source[index] !== ",") throw new ProtocolError(field, "expected ',' or ']' ")
      index += 1
    }
    throw new ProtocolError(field, "unterminated JSON array")
  }

  const result = parseValue("json")
  skipWhitespace()
  if (index !== source.length) throw new ProtocolError("json", "trailing content", source.slice(index, index + 20))
  return result
}

export function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

export function record(value: unknown, field: string): JsonRecord {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new ProtocolError(field, "must be an object", value)
  return value as JsonRecord
}

export function text(value: unknown, field: string): string {
  if (typeof value !== "string" || !value.trim()) throw new ProtocolError(field, "must be a non-empty string", value)
  return value.trim()
}

export function integer(value: unknown, field: string, minimum = 0): number {
  if (!Number.isInteger(value) || (value as number) < minimum) throw new ProtocolError(field, `must be an integer >= ${minimum}`, value)
  return value as number
}

export function boolean(value: unknown, field: string): boolean {
  if (typeof value !== "boolean") throw new ProtocolError(field, "must be boolean", value)
  return value
}

export function array(value: unknown, field: string): unknown[] {
  if (!Array.isArray(value)) throw new ProtocolError(field, "must be an array", value)
  return value
}

export function strings(value: unknown, field: string, allowEmpty = true): string[] {
  const result = array(value, field).map((item, index) => text(item, `${field}[${index}]`))
  if (!allowEmpty && !result.length) throw new ProtocolError(field, "must not be empty")
  if (new Set(result).size !== result.length) throw new ProtocolError(field, "must not contain duplicates", result)
  return result
}

export function exactFields(value: JsonRecord, expected: string[], field: string): void {
  const actual = Object.keys(value).sort()
  const wanted = [...expected].sort()
  if (JSON.stringify(actual) !== JSON.stringify(wanted)) {
    throw new ProtocolError(field, "field mismatch", {
      missing: wanted.filter((item) => !actual.includes(item)),
      unknown: actual.filter((item) => !wanted.includes(item)),
    })
  }
}

export function identifier(value: unknown, family: string, field: string): string {
  const result = text(value, field)
  if (!new RegExp(`^${family}-[0-9]{3}$`).test(result)) throw new ProtocolError(field, `must match ${family}-NNN`, result)
  return result
}

export function stageId(value: unknown, field: string): string {
  const result = text(value, field)
  if (!/^S[0-9]{2}$/.test(result)) throw new ProtocolError(field, "must match SNN", result)
  return result
}

export function canonicalRelative(value: unknown, field: string, prefix?: string): string {
  const source = text(value, field).replace(/\\/g, "/")
  if (source.includes("\0") || path.posix.isAbsolute(source) || /^[A-Za-z]:\//.test(source)) throw new ProtocolError(field, "must be a relative path", source)
  const normalized = path.posix.normalize(source)
  if (normalized === "." || normalized === ".." || normalized.startsWith("../") || normalized.includes("/../")) throw new ProtocolError(field, "path escapes workflow root", source)
  if (source !== normalized) throw new ProtocolError(field, "path must be canonical", source)
  if (prefix && !normalized.startsWith(prefix)) throw new ProtocolError(field, `must be under ${prefix}`, normalized)
  return normalized
}
