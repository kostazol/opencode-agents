from __future__ import annotations

from pathlib import Path
import sys

from common import compile_runtime, expect_failure, node_test, write_files


ROUTING_TS = r'''
import type { Analysis, JsonRecord, PendingAction, State } from "./schema.js"
import { ProtocolError, clone } from "./schema.js"
import { validateAnalysis } from "./analysis.js"
import { completeAction, normalizeProgress, pendingAction, stageMap, validateState } from "./state.js"

function uniqueInputs(values: string[]): string[] {
  return [...new Set(values)]
}

function hasCorrection(state: State, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(state.convergence, key)
}

function completeGraphInputs(state: State): string[] {
  return uniqueInputs([
    "plan.md",
    "analysis.json",
    "discovery.md",
    "reviews/discovery.md",
    ...state.stages.flatMap((stage) => [stage.details, stage.review, stage.human_review, stage.human_review_review]),
  ])
}

export function reserveNext(input: unknown, analysisInput?: unknown, expectedStateRevision?: number): { state: State; action: JsonRecord } {
  const candidate = input as Partial<State> | null
  const cross = analysisInput !== undefined && Array.isArray(candidate?.stages) && candidate.stages.length && !candidate.legacy_migrated ? analysisInput : undefined
  const state = validateState(input, cross)
  if (expectedStateRevision !== undefined && state.state_revision !== expectedStateRevision) throw new ProtocolError("expected_state_revision", "state revision conflict", { expected: expectedStateRevision, actual: state.state_revision })
  if (state.pending) return { state, action: clone(state.pending) as unknown as JsonRecord }
  if (state.status === "ready") return { state, action: completeAction(state) }
  const next = clone(state)
  normalizeProgress(next)
  if (next.status === "ready") return { state: next, action: completeAction(next) }

  let action: PendingAction
  if (next.status === "discovery") {
    const correction = hasCorrection(next, "DISCOVERY")
    next.analysis_revision += 1
    next.analysis_status = "draft"
    action = pendingAction(next, "DISCOVER", "orchestrator-discovery", correction ? "correct-discovery-from-independent-review" : "collect-and-structure-evidence", {
      mode: correction ? "CORRECTION" : next.analysis_revision === 1 ? "INITIAL" : next.legacy_migrated ? "LEGACY_MIGRATION" : "FOLLOW_UP",
      revision: next.analysis_revision,
      inputs: uniqueInputs([
        ...(correction ? ["analysis.json", "discovery.md", "reviews/discovery.md"] : ["discovery.md"]),
        ...(next.legacy_migrated ? [".orchestrator/legacy-plan.md"] : []),
        ...(next.question_revision ? ["questions.md"] : []),
        "feedback.md",
      ]),
      output: "analysis.json",
    })
  } else if (next.status === "discovery_review") {
    if (analysisInput === undefined) throw new ProtocolError("analysis", "discovery review requires analysis.json")
    validateAnalysis(analysisInput)
    action = pendingAction(next, "REVIEW_DISCOVERY", "orchestrator-stage-reviewer", "independent-discovery-quality-gate", { mode: "DISCOVERY", revision: next.analysis_revision, inputs: ["analysis.json", "discovery.md"], output: "reviews/discovery.md" })
  } else if (next.status === "waiting_answers") {
    action = pendingAction(next, "ASK_QUESTIONS", "user", "material-user-decisions-required", { revision: next.question_revision, inputs: ["questions.md"] })
  } else if (next.status === "waiting_map_approval") {
    action = pendingAction(next, "APPROVE_MAP", "user", "reviewed-stage-map-requires-user-approval", { revision: next.analysis_revision, inputs: ["plan.md", "analysis.json", "discovery.md", "reviews/discovery.md"] })
  } else if (next.status === "planning") {
    if (analysisInput === undefined) throw new ProtocolError("analysis", "stage planning requires analysis.json")
    const current = next.stages.find((item) => item.status !== "pass")
    if (!current) throw new ProtocolError("stages", "planning has no unfinished stage")
    next.current_stage = current.id
    const stages = stageMap(next)
    const dependencies = current.depends_on.map((id) => stages.get(id)!.details)
    const correction = hasCorrection(next, `TECHNICAL:${current.id}`)
    if (current.status === "proposed" || current.status === "planning") {
      if (current.status === "proposed") {
        current.revision += 1
        current.status = "planning"
      }
      action = pendingAction(next, "PLAN_STAGE", "orchestrator-stage-planner", correction ? "correct-current-stage-from-independent-review" : "create-current-stage-plan", {
        mode: correction ? "TECHNICAL_CORRECTION" : "TECHNICAL",
        stage: current.id,
        revision: current.revision,
        source_revision: next.analysis_revision,
        inputs: uniqueInputs([
          "analysis.json",
          "discovery.md",
          "plan.md",
          ...dependencies,
          ...(correction ? [current.details, current.review] : []),
        ]),
        output: current.details,
      })
    } else {
      action = pendingAction(next, "REVIEW_STAGE", "orchestrator-stage-reviewer", "independent-current-stage-review", { mode: "TECHNICAL", stage: current.id, revision: current.revision, source_revision: current.revision, inputs: uniqueInputs(["analysis.json", "discovery.md", "plan.md", current.details, ...dependencies]), output: current.review })
    }
  } else if (next.status === "human_reviewing") {
    const current = next.stages.find((item) => item.human_status !== "pass")
    if (!current) throw new ProtocolError("stages", "human review has no unfinished stage")
    next.current_stage = current.id
    const correction = hasCorrection(next, `HUMAN:${current.id}`)
    if (current.human_status === "pending" || current.human_status === "planning") {
      if (current.human_status === "pending") {
        current.human_revision += 1
        current.human_status = "planning"
      }
      action = pendingAction(next, "PLAN_HUMAN_REVIEW", "orchestrator-stage-planner", correction ? "correct-human-review-from-independent-review" : "create-user-readable-stage-plan", {
        mode: correction ? "HUMAN_REVIEW_CORRECTION" : "HUMAN_REVIEW",
        stage: current.id,
        revision: current.human_revision,
        source_revision: current.revision,
        inputs: uniqueInputs([
          "analysis.json",
          "plan.md",
          current.details,
          current.review,
          ...(correction ? [current.human_review, current.human_review_review] : []),
        ]),
        output: current.human_review,
      })
    } else {
      action = pendingAction(next, "REVIEW_HUMAN_REVIEW", "orchestrator-stage-reviewer", "independent-human-review-fidelity-gate", { mode: "HUMAN_REVIEW", stage: current.id, revision: current.human_revision, source_revision: current.revision, inputs: ["analysis.json", "plan.md", current.details, current.review, current.human_review], output: current.human_review_review })
    }
  } else if (next.status === "waiting_plan_approval") {
    action = pendingAction(next, "APPROVE_PLAN", "user", "fully-reviewed-plan-requires-user-approval", { inputs: completeGraphInputs(next) })
  } else if (next.status === "waiting_reopen_approval") {
    action = pendingAction(next, "APPROVE_REOPEN", "user", "passed-stage-reopening-requires-user-approval", { inputs: completeGraphInputs(next) })
  } else if (next.status === "blocked") {
    action = pendingAction(next, "RESOLVE_BLOCKER", "user", "workflow-blocker-requires-resolution", { inputs: ["plan.md"] })
  } else {
    throw new ProtocolError("state.status", "no action for status", next.status)
  }
  return { state: validateState(next, analysisInput !== undefined && next.stages.length && !next.legacy_migrated ? analysisInput : undefined), action: clone(action) as unknown as JsonRecord }
}
'''


LEGAL_MATRIX = r'''
function assertLegalStateMatrix(state: State): void {
  const allTechnicalPass = state.stages.length > 0 && state.stages.every((stage) => stage.status === "pass")
  const allHumanPass = state.stages.length > 0 && state.stages.every((stage) => stage.human_status === "pass")
  const anyTechnicalPass = state.stages.some((stage) => stage.status === "pass")
  const anyHumanProgress = state.stages.some((stage) => stage.human_status !== "pending")

  const pendingByStatus: Record<WorkflowStatus, Set<string>> = {
    discovery: new Set(["DISCOVER"]),
    discovery_review: new Set(["REVIEW_DISCOVERY"]),
    waiting_answers: new Set(["ASK_QUESTIONS"]),
    waiting_map_approval: new Set(["APPROVE_MAP"]),
    planning: new Set(["PLAN_STAGE", "REVIEW_STAGE"]),
    human_reviewing: new Set(["PLAN_HUMAN_REVIEW", "REVIEW_HUMAN_REVIEW"]),
    waiting_plan_approval: new Set(["APPROVE_PLAN"]),
    waiting_reopen_approval: new Set(["APPROVE_REOPEN"]),
    ready: new Set(),
    blocked: new Set(["RESOLVE_BLOCKER"]),
  }

  if (state.pending && !pendingByStatus[state.status].has(state.pending.action)) {
    throw new ProtocolError("state.pending.action", "action is illegal for workflow status", { status: state.status, action: state.pending.action })
  }
  if (state.status === "ready" && state.pending) throw new ProtocolError("state.pending", "ready state cannot have a pending action")

  if (state.status === "discovery") {
    if (!new Set(["missing", "draft"]).has(state.analysis_status)) throw new ProtocolError("state.analysis_status", "discovery requires missing or draft analysis", state.analysis_status)
    if (anyTechnicalPass || anyHumanProgress) throw new ProtocolError("state.stages", "discovery cannot retain approved stage progress")
  } else if (state.status === "discovery_review") {
    if (state.analysis_status !== "review" || !state.stages.length) throw new ProtocolError("state", "discovery_review requires reviewed candidate analysis and a non-empty stage map")
    if (anyTechnicalPass || anyHumanProgress) throw new ProtocolError("state.stages", "discovery review cannot contain passed stage work")
  } else if (state.status === "waiting_answers") {
    if (!new Set(["draft", "missing"]).has(state.analysis_status)) throw new ProtocolError("state.analysis_status", "waiting_answers requires unfinished analysis")
  } else if (state.status === "waiting_map_approval") {
    if (state.analysis_status !== "reviewed" || !state.stages.length) throw new ProtocolError("state", "waiting_map_approval requires a reviewed non-empty stage map")
    if (state.stages.some((stage) => stage.status !== "proposed" || stage.human_status !== "pending")) throw new ProtocolError("state.stages", "map approval must precede stage execution")
  } else if (state.status === "planning") {
    if (state.analysis_status !== "approved" || !state.stages.length || !state.current_stage) throw new ProtocolError("state", "planning requires an approved non-empty stage map and current stage")
    if (allTechnicalPass || anyHumanProgress) throw new ProtocolError("state.stages", "planning must have unfinished technical work and no human-review progress")
    const currentIndex = state.stages.findIndex((stage) => stage.id === state.current_stage)
    if (currentIndex < 0) throw new ProtocolError("state.current_stage", "unknown current stage", state.current_stage)
    if (state.stages.slice(0, currentIndex).some((stage) => stage.status !== "pass")) throw new ProtocolError("state.stages", "stages before current stage must pass")
    if (state.stages.slice(currentIndex + 1).some((stage) => stage.status !== "proposed")) throw new ProtocolError("state.stages", "stages after current stage must remain proposed")
  } else if (state.status === "human_reviewing") {
    if (state.analysis_status !== "approved" || !state.stages.length || !state.current_stage || !allTechnicalPass || allHumanPass) throw new ProtocolError("state", "human_reviewing requires all technical stages passed and unfinished human review")
    const currentIndex = state.stages.findIndex((stage) => stage.id === state.current_stage)
    if (state.stages.slice(0, currentIndex).some((stage) => stage.human_status !== "pass")) throw new ProtocolError("state.stages", "human reviews before current stage must pass")
    if (state.stages.slice(currentIndex + 1).some((stage) => stage.human_status !== "pending")) throw new ProtocolError("state.stages", "future human reviews must remain pending")
  } else if (state.status === "waiting_plan_approval" || state.status === "ready") {
    if (state.analysis_status !== "approved" || !state.stages.length || !allTechnicalPass || !allHumanPass || state.current_stage !== null) {
      throw new ProtocolError("state", `${state.status} requires a non-empty approved stage map and complete PASS statuses`)
    }
  } else if (state.status === "waiting_reopen_approval") {
    if (state.analysis_status !== "approved" || !state.stages.length || state.reopen === null) throw new ProtocolError("state", "reopen approval requires an approved non-empty stage map")
  }

  if (state.pending?.action === "PLAN_STAGE" || state.pending?.action === "REVIEW_STAGE") {
    if (state.pending.stage !== state.current_stage) throw new ProtocolError("state.pending.stage", "technical action must target current stage")
    const current = state.stages.find((stage) => stage.id === state.current_stage)!
    const expected = state.pending.action === "PLAN_STAGE" ? "planning" : "review"
    if (current.status !== expected) throw new ProtocolError("state.pending.action", "technical action does not match current stage status", { action: state.pending.action, stage_status: current.status })
  }
  if (state.pending?.action === "PLAN_HUMAN_REVIEW" || state.pending?.action === "REVIEW_HUMAN_REVIEW") {
    if (state.pending.stage !== state.current_stage) throw new ProtocolError("state.pending.stage", "human-review action must target current stage")
    const current = state.stages.find((stage) => stage.id === state.current_stage)!
    const expected = state.pending.action === "PLAN_HUMAN_REVIEW" ? "planning" : "review"
    if (current.human_status !== expected) throw new ProtocolError("state.pending.action", "human-review action does not match current stage status", { action: state.pending.action, human_status: current.human_status })
  }
}
'''


TEST = r'''
import assert from "node:assert/strict"
import test from "node:test"

import {
  ProtocolError,
  newState,
  reserveNext,
  stagesFromAnalysis,
  validateState,
} from "../runtime/orchestrator.js"
import { analysisFixture } from "./helpers.mjs"

const hash = "a".repeat(64)
const marker = (revision = 1) => ({ fingerprint: hash, evidence_digest: "b".repeat(64), repeats: 1, last_revision: revision })

function approvedState() {
  const analysis = analysisFixture()
  const state = newState("routing")
  state.analysis_revision = 1
  state.analysis_status = "approved"
  state.stages = stagesFromAnalysis(analysis)
  return { state, analysis }
}

test("discovery correction receives the failed discovery review", () => {
  const state = newState("discovery-correction")
  state.analysis_revision = 1
  state.analysis_status = "draft"
  state.convergence.DISCOVERY = marker()
  const result = reserveNext(state)
  assert.equal(result.action.mode, "CORRECTION")
  assert.ok(result.action.inputs.includes("reviews/discovery.md"))
  assert.ok(result.action.inputs.includes("discovery.md"))
})

test("technical correction receives current stage and failed technical review", () => {
  const { state, analysis } = approvedState()
  state.status = "planning"
  state.current_stage = "S01"
  state.stages[0].status = "planning"
  state.stages[0].revision = 2
  state.convergence["TECHNICAL:S01"] = marker(2)
  const result = reserveNext(state, analysis)
  assert.equal(result.action.mode, "TECHNICAL_CORRECTION")
  assert.ok(result.action.inputs.includes(state.stages[0].details))
  assert.ok(result.action.inputs.includes(state.stages[0].review))
})

test("human correction receives current human artifact and failed human review", () => {
  const { state, analysis } = approvedState()
  state.status = "human_reviewing"
  state.current_stage = "S01"
  for (const stage of state.stages) {
    stage.status = "pass"
    stage.revision = 1
  }
  state.stages[0].human_status = "planning"
  state.stages[0].human_revision = 2
  state.convergence["HUMAN:S01"] = marker(2)
  const result = reserveNext(state, analysis)
  assert.equal(result.action.mode, "HUMAN_REVIEW_CORRECTION")
  assert.ok(result.action.inputs.includes(state.stages[0].human_review))
  assert.ok(result.action.inputs.includes(state.stages[0].human_review_review))
})

test("ready and waiting_plan_approval reject empty or incomplete stage maps", () => {
  const empty = newState("impossible-ready")
  empty.status = "ready"
  empty.analysis_status = "approved"
  assert.throws(() => validateState(empty), ProtocolError)

  const { state } = approvedState()
  state.status = "waiting_plan_approval"
  state.current_stage = null
  assert.throws(() => validateState(state), ProtocolError)
})

test("pending action must be legal for status and current stage", () => {
  const { state, analysis } = approvedState()
  state.status = "planning"
  state.current_stage = "S01"
  state.stages[0].status = "planning"
  state.stages[0].revision = 1
  const reserved = reserveNext(state, analysis).state
  reserved.pending.action = "REVIEW_STAGE"
  assert.throws(() => validateState(reserved, analysis), /does not match|illegal/i)
})
'''


def apply(root: Path, log: Path) -> list[str]:
    test_path = "tests-ts/routing-state-hardening.test.mjs"
    changed = write_files(root, {test_path: TEST})
    expect_failure(["node", "--test", test_path], cwd=root, log=log)

    state_path = root / "src/state.ts"
    state_source = state_path.read_text(encoding="utf-8")
    marker = "export function validateState(input: unknown, analysisInput?: unknown): State {"
    if marker not in state_source or "function assertLegalStateMatrix" in state_source:
        raise RuntimeError("unexpected state.ts shape before legal-state patch")
    state_source = state_source.replace(marker, LEGAL_MATRIX + "\n\n" + marker, 1)
    tail = "  if (typeof state.legacy_migrated !== \"boolean\") throw new ProtocolError(\"state.legacy_migrated\", \"must be boolean\")\n  if (analysisInput !== undefined && state.stages.length) {"
    replacement = "  if (typeof state.legacy_migrated !== \"boolean\") throw new ProtocolError(\"state.legacy_migrated\", \"must be boolean\")\n  assertLegalStateMatrix(state)\n  if (analysisInput !== undefined && state.stages.length) {"
    if tail not in state_source:
        raise RuntimeError("cannot insert legal-state validation call")
    state_source = state_source.replace(tail, replacement, 1)

    changed += write_files(root, {
        "src/routing.ts": ROUTING_TS,
        "src/state.ts": state_source,
    })
    compile_runtime(root, log=log)
    node_test(root, [test_path], log=log)
    node_test(root, ["tests-ts/release-blockers.test.mjs"], pattern="correction routing|legal state|ready|waiting_plan", log=log)
    return changed + ["runtime"]


if __name__ == "__main__":
    repository = Path(sys.argv[1]).resolve()
    log = Path(sys.argv[2]).resolve()
    print("\n".join(apply(repository, log)))
