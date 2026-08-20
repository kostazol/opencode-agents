from __future__ import annotations

from pathlib import Path
import sys

from common import compile_runtime, expect_failure, node_test, write_files


SCHEMA_TS = r'''
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
'''


ARTIFACTS_TS = r'''
import { createHash } from "node:crypto"
import { lstat, readFile, realpath, stat } from "node:fs/promises"
import path from "node:path"
import type { Analysis, ArtifactSnapshot, EventInput, PendingAction, RevisionMetadata, State } from "./schema.js"
import { ProtocolError, canonicalRelative, integer, record, stageId, text } from "./schema.js"

const ARTIFACT_SCHEMA_VERSION = 1
const ARTIFACT_FIELDS = ["schema_version", "artifact", "stage", "revision", "source_revision", "status"] as const

export interface ArtifactContract {
  artifact: string
  stage: string | null
  revision: number
  source_revision: number
  status: string
}

function digest(content: string): string {
  return createHash("sha256").update(content).digest("hex")
}

function isWithin(base: string, candidate: string): boolean {
  const relative = path.relative(path.resolve(base), path.resolve(candidate))
  return relative === "" || (relative !== ".." && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative))
}

function errorCode(error: unknown): string | undefined {
  return (error as { code?: string }).code
}

async function containedText(root: string, relativeInput: string, required: boolean): Promise<string | null> {
  const relative = canonicalRelative(relativeInput, "artifact.path")
  const absolute = path.resolve(root, ...relative.split("/"))
  if (!isWithin(root, absolute)) throw new ProtocolError("artifact.path", "path escapes workflow root", relative)
  let entry: Awaited<ReturnType<typeof lstat>>
  try {
    entry = await lstat(absolute)
  } catch (error) {
    if (errorCode(error) === "ENOENT" && !required) return null
    throw new ProtocolError("artifact.path", required ? "required file is missing" : "cannot inspect file", { path: relative, error: String(error) })
  }
  if (!entry.isFile() && !entry.isSymbolicLink()) throw new ProtocolError("artifact.path", "must resolve to a regular file", relative)
  let resolvedRoot: string
  let resolvedCandidate: string
  try {
    resolvedRoot = await realpath(root)
    resolvedCandidate = await realpath(absolute)
  } catch (error) {
    throw new ProtocolError("artifact.path", "cannot resolve file", { path: relative, error: String(error) })
  }
  if (!isWithin(resolvedRoot, resolvedCandidate)) throw new ProtocolError("artifact.path", "symlink escapes workflow root", relative)
  const resolvedStat = await stat(resolvedCandidate)
  if (!resolvedStat.isFile()) throw new ProtocolError("artifact.path", "must resolve to a regular file", relative)
  try {
    return await readFile(resolvedCandidate, "utf8")
  } catch (error) {
    throw new ProtocolError("artifact.path", "cannot read file", { path: relative, error: String(error) })
  }
}

function frontmatter(content: string, field: string): { values: Map<string, string>; body: string } {
  const lines = content.split(/\r?\n/)
  if (lines[0] !== "---") throw new ProtocolError(field, "frontmatter start delimiter is missing")
  const end = lines.indexOf("---", 1)
  if (end < 0) throw new ProtocolError(field, "frontmatter end delimiter is missing")
  const values = new Map<string, string>()
  for (const [index, line] of lines.slice(1, end).entries()) {
    const separator = line.indexOf(":")
    if (separator <= 0) throw new ProtocolError(`${field}[${index}]`, "expected key: value", line)
    const key = line.slice(0, separator).trim()
    const value = line.slice(separator + 1).trim()
    if (!key || !value) throw new ProtocolError(`${field}.${key || index}`, "key and value must be non-empty", line)
    if (values.has(key)) throw new ProtocolError(`${field}.${key}`, "duplicate frontmatter field")
    values.set(key, value)
  }
  return { values, body: lines.slice(end + 1).join("\n").trim() }
}

function parseInteger(value: string | undefined, field: string): number {
  if (value === undefined || !/^(?:0|[1-9][0-9]*)$/.test(value)) throw new ProtocolError(field, "must be a non-negative integer", value)
  return integer(Number(value), field)
}

export function parseArtifactMetadata(content: string, field = "artifact"): RevisionMetadata {
  const parsed = frontmatter(content, `${field}.frontmatter`)
  const actual = [...parsed.values.keys()].sort()
  const expected: string[] = [...ARTIFACT_FIELDS].sort()
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new ProtocolError(`${field}.frontmatter`, "field mismatch", {
      missing: expected.filter((item) => !actual.includes(item)),
      unknown: actual.filter((item) => !expected.includes(item)),
    })
  }
  if (!parsed.body) throw new ProtocolError(`${field}.body`, "must not be empty")
  const schemaVersion = parseInteger(parsed.values.get("schema_version"), `${field}.schema_version`)
  if (schemaVersion !== ARTIFACT_SCHEMA_VERSION) throw new ProtocolError(`${field}.schema_version`, `must be ${ARTIFACT_SCHEMA_VERSION}`, schemaVersion)
  const artifact = text(parsed.values.get("artifact"), `${field}.artifact`)
  const rawStage = text(parsed.values.get("stage"), `${field}.stage`)
  const stage = rawStage === "none" ? null : stageId(rawStage, `${field}.stage`)
  return {
    schema_version: schemaVersion,
    artifact,
    stage,
    revision: parseInteger(parsed.values.get("revision"), `${field}.revision`),
    source_revision: parseInteger(parsed.values.get("source_revision"), `${field}.source_revision`),
    status: text(parsed.values.get("status"), `${field}.status`),
  }
}

function looseMetadata(content: string): RevisionMetadata | null {
  if (!content.startsWith("---\n") && !content.startsWith("---\r\n")) return null
  try {
    const parsed = frontmatter(content, "snapshot.frontmatter")
    const numberOrNull = (name: string): number | null => {
      const value = parsed.values.get(name)
      return value !== undefined && /^(?:0|[1-9][0-9]*)$/.test(value) ? Number(value) : null
    }
    const rawStage = parsed.values.get("stage")
    return {
      schema_version: numberOrNull("schema_version"),
      artifact: parsed.values.get("artifact") ?? null,
      stage: !rawStage || rawStage === "none" ? null : rawStage,
      revision: numberOrNull("revision") ?? numberOrNull("state_revision"),
      source_revision: numberOrNull("source_revision"),
      status: parsed.values.get("status") ?? null,
    }
  } catch {
    return null
  }
}

export async function captureSnapshot(root: string, relativeInput: string, contentOverride?: string): Promise<ArtifactSnapshot> {
  const relative = canonicalRelative(relativeInput, "snapshot.path")
  const content = contentOverride === undefined ? await containedText(root, relative, false) : contentOverride
  if (content === null) return { path: relative, exists: false, digest: null, metadata: null }
  return { path: relative, exists: true, digest: digest(content), metadata: looseMetadata(content) }
}

export async function capturePendingSnapshots(root: string, pending: PendingAction, overrides: Record<string, string> = {}): Promise<void> {
  pending.input_snapshot = []
  for (const relative of pending.inputs) pending.input_snapshot.push(await captureSnapshot(root, relative, overrides[relative]))
  pending.output_snapshot = pending.output === null ? null : await captureSnapshot(root, pending.output, overrides[pending.output])
  pending.snapshots_captured = true
}

function snapshotEqual(left: ArtifactSnapshot, right: ArtifactSnapshot): boolean {
  return JSON.stringify(left) === JSON.stringify(right)
}

function mutableInputPaths(pending: PendingAction): Set<string> {
  const result = new Set<string>()
  if (pending.output) result.add(pending.output)
  if (pending.action === "DISCOVER") {
    result.add("analysis.json")
    result.add("discovery.md")
    result.add("questions.md")
  }
  return result
}

export async function assertInputSnapshotsCurrent(root: string, pending: PendingAction): Promise<void> {
  if (!pending.snapshots_captured) throw new ProtocolError("state.pending.snapshots_captured", "pending transition has no immutable snapshot")
  if (pending.input_snapshot.length !== pending.inputs.length) throw new ProtocolError("state.pending.input_snapshot", "snapshot count does not match inputs")
  const mutable = mutableInputPaths(pending)
  for (const expected of pending.input_snapshot) {
    if (mutable.has(expected.path)) continue
    const actual = await captureSnapshot(root, expected.path)
    if (!snapshotEqual(expected, actual)) throw new ProtocolError("state.pending.input_snapshot", "reserved input is stale or changed", { path: expected.path, expected, actual })
  }
}

export async function assertFreshPrimaryOutput(root: string, pending: PendingAction): Promise<void> {
  if (!pending.output) throw new ProtocolError("state.pending.output", "agent success requires a canonical output path")
  if (!pending.output_snapshot) throw new ProtocolError("state.pending.output_snapshot", "pending transition has no output baseline")
  const actual = await captureSnapshot(root, pending.output)
  if (!actual.exists) throw new ProtocolError("state.pending.output", "reserved output artifact is missing", pending.output)
  if (snapshotEqual(pending.output_snapshot, actual)) throw new ProtocolError("state.pending.output", "reserved output is stale and was not regenerated", pending.output)
}

export async function assertArtifact(root: string, relativeInput: string, expected: ArtifactContract): Promise<RevisionMetadata> {
  const relative = canonicalRelative(relativeInput, "artifact.path")
  const content = await containedText(root, relative, true)
  const actual = parseArtifactMetadata(content!, relative)
  const contract: RevisionMetadata = {
    schema_version: ARTIFACT_SCHEMA_VERSION,
    artifact: expected.artifact,
    stage: expected.stage,
    revision: expected.revision,
    source_revision: expected.source_revision,
    status: expected.status,
  }
  if (JSON.stringify(actual) !== JSON.stringify(contract)) throw new ProtocolError(relative, "artifact contract mismatch", { expected: contract, actual })
  return actual
}

function payloadStatus(event: EventInput): string | null {
  const payload = record(event.payload, "event.payload")
  return typeof payload.status === "string" ? payload.status : null
}

export async function assertPendingOutputContracts(root: string, state: State, event: EventInput, analysis?: Analysis): Promise<void> {
  const pending = state.pending
  if (!pending) throw new ProtocolError("state.pending", "output validation requires pending action")
  if (event.type === "task_failure") return
  const status = payloadStatus(event)
  if (status === "BLOCKED" || status === null) return

  if (pending.action === "DISCOVER") {
    if (status !== "READY_FOR_REVIEW") return
    if (!analysis) throw new ProtocolError("analysis.json", "READY_FOR_REVIEW requires a valid analysis artifact")
    await assertFreshPrimaryOutput(root, pending)
    await assertArtifact(root, "discovery.md", {
      artifact: "discovery",
      stage: null,
      revision: pending.revision!,
      source_revision: Math.max(0, pending.revision! - 1),
      status,
    })
    return
  }

  if (!new Set(["REVIEW_DISCOVERY", "PLAN_STAGE", "REVIEW_STAGE", "PLAN_HUMAN_REVIEW", "REVIEW_HUMAN_REVIEW"]).has(pending.action)) return
  await assertFreshPrimaryOutput(root, pending)
  if (!pending.output) throw new ProtocolError("state.pending.output", "agent result requires output")

  if (pending.action === "REVIEW_DISCOVERY") {
    await assertArtifact(root, pending.output, { artifact: "discovery-review", stage: null, revision: pending.revision!, source_revision: pending.revision!, status })
  } else if (pending.action === "PLAN_STAGE") {
    await assertArtifact(root, pending.output, { artifact: "technical-stage", stage: pending.stage, revision: pending.revision!, source_revision: pending.source_revision!, status })
  } else if (pending.action === "REVIEW_STAGE") {
    await assertArtifact(root, pending.output, { artifact: "technical-review", stage: pending.stage, revision: pending.revision!, source_revision: pending.source_revision!, status })
  } else if (pending.action === "PLAN_HUMAN_REVIEW") {
    await assertArtifact(root, pending.output, { artifact: "human-review", stage: pending.stage, revision: pending.revision!, source_revision: pending.source_revision!, status })
  } else {
    await assertArtifact(root, pending.output, { artifact: "human-review-review", stage: pending.stage, revision: pending.revision!, source_revision: pending.source_revision!, status })
  }
}

export async function assertCompleteArtifactGraph(root: string, state: State, analysis: Analysis | undefined): Promise<void> {
  if (!analysis) throw new ProtocolError("analysis.json", "complete artifact graph requires valid analysis.json")
  if (!state.stages.length) throw new ProtocolError("state.stages", "complete artifact graph requires an approved stage map")
  await assertArtifact(root, "discovery.md", {
    artifact: "discovery",
    stage: null,
    revision: state.analysis_revision,
    source_revision: Math.max(0, state.analysis_revision - 1),
    status: "READY_FOR_REVIEW",
  })
  await assertArtifact(root, "reviews/discovery.md", {
    artifact: "discovery-review",
    stage: null,
    revision: state.analysis_revision,
    source_revision: state.analysis_revision,
    status: "PASS",
  })
  for (const stage of state.stages) {
    await assertArtifact(root, stage.details, {
      artifact: "technical-stage",
      stage: stage.id,
      revision: stage.revision,
      source_revision: state.analysis_revision,
      status: "REVIEW",
    })
    await assertArtifact(root, stage.review, {
      artifact: "technical-review",
      stage: stage.id,
      revision: stage.revision,
      source_revision: stage.revision,
      status: "PASS",
    })
    await assertArtifact(root, stage.human_review, {
      artifact: "human-review",
      stage: stage.id,
      revision: stage.human_revision,
      source_revision: stage.revision,
      status: "REVIEW",
    })
    await assertArtifact(root, stage.human_review_review, {
      artifact: "human-review-review",
      stage: stage.id,
      revision: stage.human_revision,
      source_revision: stage.revision,
      status: "PASS",
    })
  }
}
'''


STATE_TS = r'''
import { createHash } from "node:crypto"
import type { Analysis, ArtifactSnapshot, JsonRecord, PendingAction, RevisionMetadata, StageState, State, WorkflowStatus } from "./schema.js"
import { EVENT_BY_ACTION, HUMAN_STATUSES, ProtocolError, STAGE_STATUSES, STATE_SCHEMA_VERSION, WORKFLOW_STATUSES, boolean, canonicalRelative, clone, exactFields, integer, record, stageId, strings, text } from "./schema.js"
import { validateAnalysis } from "./analysis.js"

export interface StateMigrationResult {
  state: JsonRecord
  migrated: boolean
  from_version: number
  to_version: number
  invalidated_transition: string | null
}

export function migrateState(input: unknown): StateMigrationResult {
  const raw = clone(record(input, "state"))
  const version = integer(raw.schema_version, "state.schema_version", 1)
  if (version === STATE_SCHEMA_VERSION) return { state: raw, migrated: false, from_version: version, to_version: version, invalidated_transition: null }
  if (version !== 1 || STATE_SCHEMA_VERSION !== 2) throw new ProtocolError("state.schema_version", `cannot migrate schema ${version} to ${STATE_SCHEMA_VERSION}`)
  const oldPending = raw.pending && typeof raw.pending === "object" && !Array.isArray(raw.pending) ? raw.pending as JsonRecord : null
  const invalidated = oldPending && typeof oldPending.transition_id === "string" ? oldPending.transition_id : null
  raw.schema_version = STATE_SCHEMA_VERSION
  if (oldPending) {
    const previousStatus = typeof raw.status === "string" && WORKFLOW_STATUSES.has(raw.status) ? raw.status as WorkflowStatus : "discovery"
    const resumeStatus: WorkflowStatus = previousStatus === "ready" || previousStatus === "blocked" ? "discovery" : previousStatus
    raw.pending = null
    raw.status = "blocked"
    raw.blocker = {
      reason: "state_schema_migration_requires_retry",
      detail: "The v1 pending transition had no immutable input snapshot and was invalidated safely; retry the action.",
      resume_status: resumeStatus,
      retryable: true,
      source_transition: invalidated ?? "schema-v1",
    }
  }
  return { state: raw, migrated: true, from_version: version, to_version: STATE_SCHEMA_VERSION, invalidated_transition: invalidated }
}

function validateMetadata(input: unknown, field: string): RevisionMetadata {
  const metadata = record(input, field) as unknown as RevisionMetadata
  exactFields(metadata as unknown as JsonRecord, ["schema_version", "artifact", "stage", "revision", "source_revision", "status"], field)
  for (const name of ["schema_version", "revision", "source_revision"] as const) if (metadata[name] !== null) metadata[name] = integer(metadata[name], `${field}.${name}`)
  if (metadata.artifact !== null) metadata.artifact = text(metadata.artifact, `${field}.artifact`)
  if (metadata.stage !== null) metadata.stage = stageId(metadata.stage, `${field}.stage`)
  if (metadata.status !== null) metadata.status = text(metadata.status, `${field}.status`)
  return metadata
}

function validateSnapshot(input: unknown, field: string): ArtifactSnapshot {
  const snapshot = record(input, field) as unknown as ArtifactSnapshot
  exactFields(snapshot as unknown as JsonRecord, ["path", "exists", "digest", "metadata"], field)
  snapshot.path = canonicalRelative(snapshot.path, `${field}.path`)
  snapshot.exists = boolean(snapshot.exists, `${field}.exists`)
  if (snapshot.exists) {
    const value = text(snapshot.digest, `${field}.digest`)
    if (!/^[0-9a-f]{64}$/.test(value)) throw new ProtocolError(`${field}.digest`, "must be a SHA-256 digest", value)
    snapshot.digest = value
  } else if (snapshot.digest !== null) {
    throw new ProtocolError(`${field}.digest`, "must be null when the path did not exist", snapshot.digest)
  }
  snapshot.metadata = snapshot.metadata === null ? null : validateMetadata(snapshot.metadata, `${field}.metadata`)
  if (!snapshot.exists && snapshot.metadata !== null) throw new ProtocolError(`${field}.metadata`, "must be null when the path did not exist")
  return snapshot
}

export function newState(requestId: string): State {
  if (!/^[a-z0-9][a-z0-9-]{0,79}$/.test(requestId)) throw new ProtocolError("request_id", "must be lower kebab-case and at most 80 characters", requestId)
  return {
    schema_version: STATE_SCHEMA_VERSION,
    request_id: requestId,
    state_revision: 0,
    sequence: 0,
    status: "discovery",
    current_stage: null,
    analysis_revision: 0,
    analysis_status: "missing",
    question_revision: 0,
    feedback_revision: 0,
    stages: [],
    pending: null,
    applied: {},
    blocker: null,
    reopen: null,
    convergence: {},
    legacy_migrated: false,
  }
}

export function stagesFromAnalysis(analysis: Analysis): StageState[] {
  return analysis.stages.map((item, index) => ({
    id: item.id,
    title: item.title,
    slug: item.slug,
    depends_on: [...item.depends_on],
    status: "proposed",
    revision: 0,
    human_status: "pending",
    human_revision: 0,
    details: `stages/${String(index + 1).padStart(2, "0")}-${item.slug}.md`,
    review: `reviews/${String(index + 1).padStart(2, "0")}.md`,
    human_review: `stages/${String(index + 1).padStart(2, "0")}-${item.slug}.human-review.md`,
    human_review_review: `reviews/${String(index + 1).padStart(2, "0")}-human-review.md`,
  }))
}

export function stageMap(state: State): Map<string, StageState> {
  return new Map(state.stages.map((item) => [item.id, item]))
}

export function validateState(input: unknown, analysisInput?: unknown): State {
  const state = clone(record(input, "state")) as unknown as State
  exactFields(state as unknown as JsonRecord, [
    "schema_version", "request_id", "state_revision", "sequence", "status", "current_stage",
    "analysis_revision", "analysis_status", "question_revision", "feedback_revision", "stages",
    "pending", "applied", "blocker", "reopen", "convergence", "legacy_migrated",
  ], "state")
  if (state.schema_version !== STATE_SCHEMA_VERSION) throw new ProtocolError("state.schema_version", `must be ${STATE_SCHEMA_VERSION}`, state.schema_version)
  if (!/^[a-z0-9][a-z0-9-]{0,79}$/.test(state.request_id)) throw new ProtocolError("state.request_id", "invalid request id", state.request_id)
  for (const field of ["state_revision", "sequence", "analysis_revision", "question_revision", "feedback_revision"] as const) integer(state[field], `state.${field}`)
  if (!WORKFLOW_STATUSES.has(state.status)) throw new ProtocolError("state.status", "unsupported status", state.status)
  if (!new Set(["missing", "draft", "review", "reviewed", "approved"]).has(state.analysis_status)) throw new ProtocolError("state.analysis_status", "unsupported status", state.analysis_status)
  if (!Array.isArray(state.stages)) throw new ProtocolError("state.stages", "must be an array")

  const seen = new Set<string>()
  for (const [index, stage] of state.stages.entries()) {
    const field = `state.stages[${index}]`
    exactFields(stage as unknown as JsonRecord, [
      "id", "title", "slug", "depends_on", "status", "revision", "human_status", "human_revision",
      "details", "review", "human_review", "human_review_review",
    ], field)
    const id = stageId(stage.id, `${field}.id`)
    if (id !== `S${String(index + 1).padStart(2, "0")}`) throw new ProtocolError(`${field}.id`, "stages must be contiguous and ordered", id)
    stage.title = text(stage.title, `${field}.title`)
    stage.slug = text(stage.slug, `${field}.slug`)
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(stage.slug)) throw new ProtocolError(`${field}.slug`, "must be lower kebab-case", stage.slug)
    stage.depends_on = strings(stage.depends_on, `${field}.depends_on`)
    for (const dependency of stage.depends_on) if (!seen.has(dependency)) throw new ProtocolError(`${field}.depends_on`, "must reference earlier stages", dependency)
    seen.add(id)
    if (!STAGE_STATUSES.has(stage.status)) throw new ProtocolError(`${field}.status`, "unsupported stage status", stage.status)
    if (!HUMAN_STATUSES.has(stage.human_status)) throw new ProtocolError(`${field}.human_status`, "unsupported human-review status", stage.human_status)
    integer(stage.revision, `${field}.revision`)
    integer(stage.human_revision, `${field}.human_revision`)
    stage.details = canonicalRelative(stage.details, `${field}.details`, "stages/")
    stage.review = canonicalRelative(stage.review, `${field}.review`, "reviews/")
    stage.human_review = canonicalRelative(stage.human_review, `${field}.human_review`, "stages/")
    stage.human_review_review = canonicalRelative(stage.human_review_review, `${field}.human_review_review`, "reviews/")
    if (stage.status === "pass" && stage.revision === 0) throw new ProtocolError(`${field}.revision`, "passed stage requires a revision")
    if (stage.human_status === "pass" && stage.human_revision === 0) throw new ProtocolError(`${field}.human_revision`, "passed human review requires a revision")
  }

  if (state.current_stage !== null) {
    state.current_stage = stageId(state.current_stage, "state.current_stage")
    if (!seen.has(state.current_stage)) throw new ProtocolError("state.current_stage", "unknown stage", state.current_stage)
  }
  if ((state.status === "planning" || state.status === "human_reviewing") && state.stages.length && state.current_stage === null) throw new ProtocolError("state.current_stage", "active workflow requires a stage")

  if (state.pending !== null) {
    const pending = record(state.pending, "state.pending") as unknown as PendingAction
    exactFields(pending as unknown as JsonRecord, [
      "transition_id", "action", "actor", "mode", "stage", "revision", "source_revision",
      "inputs", "input_snapshot", "output", "output_snapshot", "snapshots_captured", "reason", "issued_state_revision",
    ], "state.pending")
    pending.transition_id = text(pending.transition_id, "state.pending.transition_id")
    pending.action = text(pending.action, "state.pending.action")
    if (!EVENT_BY_ACTION[pending.action]) throw new ProtocolError("state.pending.action", "unsupported action", pending.action)
    pending.actor = text(pending.actor, "state.pending.actor")
    if (pending.mode !== null) pending.mode = text(pending.mode, "state.pending.mode")
    if (pending.stage !== null) {
      pending.stage = stageId(pending.stage, "state.pending.stage")
      if (!seen.has(pending.stage)) throw new ProtocolError("state.pending.stage", "unknown stage", pending.stage)
    }
    if (pending.revision !== null) pending.revision = integer(pending.revision, "state.pending.revision", 1)
    if (pending.source_revision !== null) pending.source_revision = integer(pending.source_revision, "state.pending.source_revision")
    pending.inputs = strings(pending.inputs, "state.pending.inputs").map((value, index) => canonicalRelative(value, `state.pending.inputs[${index}]`))
    if (!Array.isArray(pending.input_snapshot)) throw new ProtocolError("state.pending.input_snapshot", "must be an array")
    pending.input_snapshot = pending.input_snapshot.map((item, index) => validateSnapshot(item, `state.pending.input_snapshot[${index}]`))
    if (pending.output !== null) pending.output = canonicalRelative(pending.output, "state.pending.output")
    pending.output_snapshot = pending.output_snapshot === null ? null : validateSnapshot(pending.output_snapshot, "state.pending.output_snapshot")
    pending.snapshots_captured = boolean(pending.snapshots_captured, "state.pending.snapshots_captured")
    if (pending.snapshots_captured) {
      if (pending.input_snapshot.length !== pending.inputs.length) throw new ProtocolError("state.pending.input_snapshot", "must contain one immutable snapshot per input")
      pending.input_snapshot.forEach((snapshot, index) => {
        if (snapshot.path !== pending.inputs[index]) throw new ProtocolError(`state.pending.input_snapshot[${index}].path`, "must match the corresponding input", snapshot.path)
      })
      if ((pending.output === null) !== (pending.output_snapshot === null)) throw new ProtocolError("state.pending.output_snapshot", "must exist exactly when output is reserved")
      if (pending.output !== null && pending.output_snapshot!.path !== pending.output) throw new ProtocolError("state.pending.output_snapshot.path", "must match reserved output", pending.output_snapshot!.path)
    } else if (pending.input_snapshot.length || pending.output_snapshot !== null) {
      throw new ProtocolError("state.pending.snapshots_captured", "uncaptured transition cannot contain partial snapshots")
    }
    pending.reason = text(pending.reason, "state.pending.reason")
    pending.issued_state_revision = integer(pending.issued_state_revision, "state.pending.issued_state_revision")
    if (pending.issued_state_revision !== state.state_revision) throw new ProtocolError("state.pending.issued_state_revision", "must equal state revision")
    state.pending = pending
  }

  const applied = record(state.applied, "state.applied")
  for (const [transition, raw] of Object.entries(applied)) {
    text(transition, "state.applied.transition_id")
    const item = record(raw, `state.applied.${transition}`)
    exactFields(item, ["event_digest", "result"], `state.applied.${transition}`)
    const eventDigest = text(item.event_digest, `state.applied.${transition}.event_digest`)
    if (!/^[0-9a-f]{64}$/.test(eventDigest)) throw new ProtocolError(`state.applied.${transition}.event_digest`, "must be a SHA-256 digest", eventDigest)
    record(item.result, `state.applied.${transition}.result`)
  }

  if ((state.status === "blocked") !== (state.blocker !== null)) throw new ProtocolError("state.blocker", "must exist exactly while blocked")
  if (state.blocker !== null) {
    const blocker = record(state.blocker, "state.blocker")
    exactFields(blocker, ["reason", "detail", "resume_status", "retryable", "source_transition"], "state.blocker")
    text(blocker.reason, "state.blocker.reason")
    text(blocker.detail, "state.blocker.detail")
    const resume = text(blocker.resume_status, "state.blocker.resume_status")
    if (!WORKFLOW_STATUSES.has(resume) || resume === "blocked" || resume === "ready") throw new ProtocolError("state.blocker.resume_status", "unsupported resume status", resume)
    boolean(blocker.retryable, "state.blocker.retryable")
    text(blocker.source_transition, "state.blocker.source_transition")
  }

  if ((state.status === "waiting_reopen_approval") !== (state.reopen !== null)) throw new ProtocolError("state.reopen", "must exist exactly while waiting for reopening approval")
  if (state.reopen !== null) {
    const reopen = record(state.reopen, "state.reopen")
    exactFields(reopen, ["requested_by", "reason", "seeds", "affected", "resume_status", "resume_stage"], "state.reopen")
    const requestedBy = text(reopen.requested_by, "state.reopen.requested_by")
    if (!new Set(["reviewer", "user"]).has(requestedBy)) throw new ProtocolError("state.reopen.requested_by", "unsupported requester", requestedBy)
    text(reopen.reason, "state.reopen.reason")
    const seeds = strings(reopen.seeds, "state.reopen.seeds", false).map((value) => stageId(value, "state.reopen.seeds"))
    const affected = strings(reopen.affected, "state.reopen.affected", false).map((value) => stageId(value, "state.reopen.affected"))
    for (const value of [...seeds, ...affected]) if (!seen.has(value)) throw new ProtocolError("state.reopen", "references unknown stage", value)
    for (const seed of seeds) if (!affected.includes(seed)) throw new ProtocolError("state.reopen", "affected stages must include seeds", seed)
    const resume = text(reopen.resume_status, "state.reopen.resume_status")
    if (!WORKFLOW_STATUSES.has(resume) || new Set(["blocked", "ready", "waiting_reopen_approval"]).has(resume)) throw new ProtocolError("state.reopen.resume_status", "unsupported resume status", resume)
    if (reopen.resume_stage !== null) {
      const resumeStage = stageId(reopen.resume_stage, "state.reopen.resume_stage")
      if (!seen.has(resumeStage)) throw new ProtocolError("state.reopen.resume_stage", "unknown stage", resumeStage)
    }
  }

  const convergence = record(state.convergence, "state.convergence")
  for (const [key, raw] of Object.entries(convergence)) {
    text(key, "state.convergence.key")
    const item = record(raw, `state.convergence.${key}`)
    exactFields(item, ["fingerprint", "evidence_digest", "repeats", "last_revision"], `state.convergence.${key}`)
    for (const field of ["fingerprint", "evidence_digest"] as const) {
      const value = text(item[field], `state.convergence.${key}.${field}`)
      if (!/^[0-9a-f]{64}$/.test(value)) throw new ProtocolError(`state.convergence.${key}.${field}`, "must be a SHA-256 digest", value)
    }
    integer(item.repeats, `state.convergence.${key}.repeats`, 1)
    integer(item.last_revision, `state.convergence.${key}.last_revision`, 1)
  }

  if (typeof state.legacy_migrated !== "boolean") throw new ProtocolError("state.legacy_migrated", "must be boolean")
  if (analysisInput !== undefined && state.stages.length) {
    const analysis = validateAnalysis(analysisInput)
    const actual = state.stages.map((item) => [item.id, item.title, item.slug, item.depends_on])
    const expected = analysis.stages.map((item) => [item.id, item.title, item.slug, item.depends_on])
    if (JSON.stringify(actual) !== JSON.stringify(expected)) throw new ProtocolError("state.stages", "state stage map does not match analysis")
  }
  return state
}

export function stableJson(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value)
  if (Array.isArray(value)) return `[${value.map(stableJson).join(",")}]`
  return `{${Object.entries(value as JsonRecord).sort(([left], [right]) => left.localeCompare(right)).map(([key, item]) => `${JSON.stringify(key)}:${stableJson(item)}`).join(",")}}`
}

export function sha(value: unknown): string {
  return createHash("sha256").update(typeof value === "string" ? value : stableJson(value)).digest("hex")
}

export function transitionId(state: State, action: string, stage: string | null, revision: number | null): string {
  return `T${String(state.sequence).padStart(6, "0")}-${sha(`${state.request_id}|${state.sequence}|${action}|${stage ?? "-"}|${revision ?? 0}`).slice(0, 12)}`
}

export function pendingAction(state: State, action: string, actor: string, reason: string, options: Partial<PendingAction> = {}): PendingAction {
  state.sequence += 1
  state.state_revision += 1
  const result: PendingAction = {
    transition_id: transitionId(state, action, options.stage ?? null, options.revision ?? null),
    action,
    actor,
    mode: options.mode ?? null,
    stage: options.stage ?? null,
    revision: options.revision ?? null,
    source_revision: options.source_revision ?? null,
    inputs: options.inputs ?? [],
    input_snapshot: [],
    output: options.output ?? null,
    output_snapshot: null,
    snapshots_captured: false,
    reason,
    issued_state_revision: state.state_revision,
  }
  state.pending = result
  return result
}

export function normalizeProgress(state: State): void {
  if (state.status === "planning" && state.stages.length && state.stages.every((item) => item.status === "pass")) {
    state.status = "human_reviewing"
    state.current_stage = state.stages.find((item) => item.human_status !== "pass")?.id ?? null
  }
  if (state.status === "human_reviewing" && state.stages.length && state.stages.every((item) => item.human_status === "pass")) {
    state.status = "waiting_plan_approval"
    state.current_stage = null
  }
}

export function completeAction(state: State): JsonRecord {
  return { transition_id: null, action: "COMPLETE", actor: "none", mode: null, stage: null, revision: null, source_revision: null, inputs: ["plan.md"], output: null, reason: "workflow-ready", issued_state_revision: state.state_revision }
}
'''


ROUTING_TS = r'''
import type { Analysis, JsonRecord, PendingAction, State } from "./schema.js"
import { ProtocolError, clone } from "./schema.js"
import { validateAnalysis } from "./analysis.js"
import { completeAction, normalizeProgress, pendingAction, stageMap, validateState } from "./state.js"

export function reserveNext(input: unknown, analysisInput?: unknown, expectedStateRevision?: number): { state: State; action: JsonRecord } {
  const cross = analysisInput !== undefined && (input as State).stages?.length && !(input as State).legacy_migrated ? analysisInput : undefined
  const state = validateState(input, cross)
  if (expectedStateRevision !== undefined && state.state_revision !== expectedStateRevision) throw new ProtocolError("expected_state_revision", "state revision conflict", { expected: expectedStateRevision, actual: state.state_revision })
  if (state.pending) return { state, action: clone(state.pending) as unknown as JsonRecord }
  if (state.status === "ready") return { state, action: completeAction(state) }
  const next = clone(state)
  normalizeProgress(next)
  if (next.status === "ready") return { state: next, action: completeAction(next) }

  let action: PendingAction
  if (next.status === "discovery") {
    next.analysis_revision += 1
    next.analysis_status = "draft"
    action = pendingAction(next, "DISCOVER", "orchestrator-discovery", "collect-and-structure-evidence", {
      mode: next.analysis_revision === 1 ? "INITIAL" : "FOLLOW_UP",
      revision: next.analysis_revision,
      inputs: ["discovery.md", ...(next.question_revision ? ["questions.md"] : []), "feedback.md"],
      output: "analysis.json",
    })
  } else if (next.status === "discovery_review") {
    if (analysisInput === undefined) throw new ProtocolError("analysis", "discovery review requires analysis.json")
    validateAnalysis(analysisInput)
    action = pendingAction(next, "REVIEW_DISCOVERY", "orchestrator-stage-reviewer", "independent-discovery-quality-gate", { mode: "DISCOVERY", revision: next.analysis_revision, inputs: ["analysis.json", "discovery.md"], output: "reviews/discovery.md" })
  } else if (next.status === "waiting_answers") {
    action = pendingAction(next, "ASK_QUESTIONS", "user", "material-user-decisions-required", { revision: next.question_revision, inputs: ["questions.md"] })
  } else if (next.status === "waiting_map_approval") {
    action = pendingAction(next, "APPROVE_MAP", "user", "reviewed-stage-map-requires-user-approval", { revision: next.analysis_revision, inputs: ["plan.md", "analysis.json", "reviews/discovery.md"] })
  } else if (next.status === "planning") {
    if (analysisInput === undefined) throw new ProtocolError("analysis", "stage planning requires analysis.json")
    const current = next.stages.find((item) => item.status !== "pass")
    if (!current) throw new ProtocolError("stages", "planning has no unfinished stage")
    next.current_stage = current.id
    const stages = stageMap(next)
    const dependencies = current.depends_on.map((id) => stages.get(id)!.details)
    if (current.status === "proposed" || current.status === "planning") {
      if (current.status === "proposed") {
        current.revision += 1
        current.status = "planning"
      }
      action = pendingAction(next, "PLAN_STAGE", "orchestrator-stage-planner", "create-or-correct-current-stage-plan", { mode: "TECHNICAL", stage: current.id, revision: current.revision, source_revision: next.analysis_revision, inputs: ["analysis.json", "discovery.md", "plan.md", ...dependencies], output: current.details })
    } else {
      action = pendingAction(next, "REVIEW_STAGE", "orchestrator-stage-reviewer", "independent-current-stage-review", { mode: "TECHNICAL", stage: current.id, revision: current.revision, source_revision: current.revision, inputs: ["analysis.json", "discovery.md", "plan.md", current.details, ...dependencies], output: current.review })
    }
  } else if (next.status === "human_reviewing") {
    const current = next.stages.find((item) => item.human_status !== "pass")
    if (!current) throw new ProtocolError("stages", "human review has no unfinished stage")
    next.current_stage = current.id
    if (current.human_status === "pending" || current.human_status === "planning") {
      if (current.human_status === "pending") {
        current.human_revision += 1
        current.human_status = "planning"
      }
      action = pendingAction(next, "PLAN_HUMAN_REVIEW", "orchestrator-stage-planner", "create-user-readable-stage-plan", { mode: "HUMAN_REVIEW", stage: current.id, revision: current.human_revision, source_revision: current.revision, inputs: ["analysis.json", "plan.md", current.details, current.review], output: current.human_review })
    } else {
      action = pendingAction(next, "REVIEW_HUMAN_REVIEW", "orchestrator-stage-reviewer", "independent-human-review-fidelity-gate", { mode: "HUMAN_REVIEW", stage: current.id, revision: current.human_revision, source_revision: current.revision, inputs: ["analysis.json", "plan.md", current.details, current.review, current.human_review], output: current.human_review_review })
    }
  } else if (next.status === "waiting_plan_approval") {
    action = pendingAction(next, "APPROVE_PLAN", "user", "fully-reviewed-plan-requires-user-approval", { inputs: ["plan.md", ...next.stages.map((item) => item.human_review)] })
  } else if (next.status === "waiting_reopen_approval") {
    action = pendingAction(next, "APPROVE_REOPEN", "user", "passed-stage-reopening-requires-user-approval", { inputs: ["plan.md", "analysis.json"] })
  } else if (next.status === "blocked") {
    action = pendingAction(next, "RESOLVE_BLOCKER", "user", "workflow-blocker-requires-resolution", { inputs: ["plan.md"] })
  } else {
    throw new ProtocolError("state.status", "no action for status", next.status)
  }
  return { state: validateState(next, analysisInput !== undefined && next.stages.length && !next.legacy_migrated ? analysisInput : undefined), action: clone(action) as unknown as JsonRecord }
}
'''


STORE_TS = r'''
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
'''


ORCHESTRATOR_TS = r'''
export * from "./schema.js"
export * from "./analysis.js"
export * from "./state.js"
export * from "./artifacts.js"
export * from "./routing.js"
export * from "./review.js"
export * from "./events.js"
export * from "./render.js"
export * from "./store.js"
'''


NODE_SHIMS = r'''
declare const process: { pid: number }
declare module "node:crypto" { export const createHash: any }
declare module "node:fs" { export const constants: any }
declare module "node:fs/promises" { export const access: any; export const mkdir: any; export const open: any; export const readFile: any; export const rename: any; export const rm: any; export const stat: any; export const lstat: any; export const realpath: any; export const writeFile: any }
declare module "node:path" { const path: any; export default path }
declare module "node:timers/promises" { export const setTimeout: any }
'''


CONTROLLER_TEST = r'''
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
'''


def apply(root: Path, log: Path) -> list[str]:
    test_path = "tests-ts/controller-hardening.test.mjs"
    changed = write_files(root, {test_path: CONTROLLER_TEST})
    expect_failure(["node", "--test", test_path], cwd=root, log=log)

    changed += write_files(root, {
        "src/schema.ts": SCHEMA_TS,
        "src/artifacts.ts": ARTIFACTS_TS,
        "src/state.ts": STATE_TS,
        "src/routing.ts": ROUTING_TS,
        "src/store.ts": STORE_TS,
        "src/orchestrator.ts": ORCHESTRATOR_TS,
        "types/node-shims.d.ts": NODE_SHIMS,
    })
    compile_runtime(root, log=log)
    node_test(root, [test_path], log=log)
    node_test(
        root,
        ["tests-ts/release-blockers.test.mjs"],
        pattern="planner REVIEW|reviewer PASS|reserved input changes|APPROVE_PLAN cannot",
        log=log,
    )
    return changed + ["runtime"]


if __name__ == "__main__":
    repository = Path(sys.argv[1]).resolve()
    log = Path(sys.argv[2]).resolve()
    print("\n".join(apply(repository, log)))
