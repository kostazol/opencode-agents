import { ProtocolError, clone } from "./schema.js";
import { validateAnalysis } from "./analysis.js";
import { completeAction, normalizeProgress, pendingAction, stageMap, validateState } from "./state.js";
export function reserveNext(input, analysisInput, expectedStateRevision) {
    const cross = analysisInput !== undefined && input.stages?.length && !input.legacy_migrated ? analysisInput : undefined;
    const state = validateState(input, cross);
    if (expectedStateRevision !== undefined && state.state_revision !== expectedStateRevision)
        throw new ProtocolError("expected_state_revision", "state revision conflict", { expected: expectedStateRevision, actual: state.state_revision });
    if (state.pending)
        return { state, action: clone(state.pending) };
    if (state.status === "ready")
        return { state, action: completeAction(state) };
    const next = clone(state);
    normalizeProgress(next);
    if (next.status === "ready")
        return { state: next, action: completeAction(next) };
    let action;
    if (next.status === "discovery") {
        next.analysis_revision += 1;
        next.analysis_status = "draft";
        action = pendingAction(next, "DISCOVER", "orchestrator-discovery", "collect-and-structure-evidence", {
            mode: next.analysis_revision === 1 ? "INITIAL" : "FOLLOW_UP",
            revision: next.analysis_revision,
            inputs: ["discovery.md", ...(next.question_revision ? ["questions.md"] : []), "feedback.md"],
            output: "analysis.json",
        });
    }
    else if (next.status === "discovery_review") {
        if (analysisInput === undefined)
            throw new ProtocolError("analysis", "discovery review requires analysis.json");
        validateAnalysis(analysisInput);
        action = pendingAction(next, "REVIEW_DISCOVERY", "orchestrator-stage-reviewer", "independent-discovery-quality-gate", { mode: "DISCOVERY", revision: next.analysis_revision, inputs: ["analysis.json", "discovery.md"], output: "reviews/discovery.md" });
    }
    else if (next.status === "waiting_answers") {
        action = pendingAction(next, "ASK_QUESTIONS", "user", "material-user-decisions-required", { revision: next.question_revision, inputs: ["questions.md"] });
    }
    else if (next.status === "waiting_map_approval") {
        action = pendingAction(next, "APPROVE_MAP", "user", "reviewed-stage-map-requires-user-approval", { revision: next.analysis_revision, inputs: ["plan.md", "analysis.json", "reviews/discovery.md"] });
    }
    else if (next.status === "planning") {
        if (analysisInput === undefined)
            throw new ProtocolError("analysis", "stage planning requires analysis.json");
        const current = next.stages.find((item) => item.status !== "pass");
        if (!current)
            throw new ProtocolError("stages", "planning has no unfinished stage");
        next.current_stage = current.id;
        const stages = stageMap(next);
        const dependencies = current.depends_on.map((id) => stages.get(id).details);
        if (current.status === "proposed" || current.status === "planning") {
            if (current.status === "proposed") {
                current.revision += 1;
                current.status = "planning";
            }
            action = pendingAction(next, "PLAN_STAGE", "orchestrator-stage-planner", "create-or-correct-current-stage-plan", { mode: "TECHNICAL", stage: current.id, revision: current.revision, source_revision: next.analysis_revision, inputs: ["analysis.json", "discovery.md", "plan.md", ...dependencies], output: current.details });
        }
        else {
            action = pendingAction(next, "REVIEW_STAGE", "orchestrator-stage-reviewer", "independent-current-stage-review", { mode: "TECHNICAL", stage: current.id, revision: current.revision, source_revision: current.revision, inputs: ["analysis.json", "discovery.md", "plan.md", current.details, ...dependencies], output: current.review });
        }
    }
    else if (next.status === "human_reviewing") {
        const current = next.stages.find((item) => item.human_status !== "pass");
        if (!current)
            throw new ProtocolError("stages", "human review has no unfinished stage");
        next.current_stage = current.id;
        if (current.human_status === "pending" || current.human_status === "planning") {
            if (current.human_status === "pending") {
                current.human_revision += 1;
                current.human_status = "planning";
            }
            action = pendingAction(next, "PLAN_HUMAN_REVIEW", "orchestrator-stage-planner", "create-user-readable-stage-plan", { mode: "HUMAN_REVIEW", stage: current.id, revision: current.human_revision, source_revision: current.revision, inputs: ["analysis.json", "plan.md", current.details, current.review], output: current.human_review });
        }
        else {
            action = pendingAction(next, "REVIEW_HUMAN_REVIEW", "orchestrator-stage-reviewer", "independent-human-review-fidelity-gate", { mode: "HUMAN_REVIEW", stage: current.id, revision: current.human_revision, source_revision: current.revision, inputs: ["analysis.json", "plan.md", current.details, current.review, current.human_review], output: current.human_review_review });
        }
    }
    else if (next.status === "waiting_plan_approval") {
        action = pendingAction(next, "APPROVE_PLAN", "user", "fully-reviewed-plan-requires-user-approval", { inputs: ["plan.md", ...next.stages.map((item) => item.human_review)] });
    }
    else if (next.status === "waiting_reopen_approval") {
        action = pendingAction(next, "APPROVE_REOPEN", "user", "passed-stage-reopening-requires-user-approval", { inputs: ["plan.md", "analysis.json"] });
    }
    else if (next.status === "blocked") {
        action = pendingAction(next, "RESOLVE_BLOCKER", "user", "workflow-blocker-requires-resolution", { inputs: ["plan.md"] });
    }
    else {
        throw new ProtocolError("state.status", "no action for status", next.status);
    }
    return { state: validateState(next, analysisInput !== undefined && next.stages.length && !next.legacy_migrated ? analysisInput : undefined), action: clone(action) };
}
