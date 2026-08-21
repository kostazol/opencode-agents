import { EVENT_BY_ACTION, ProtocolError, clone, record, strings, text } from "./schema.js";
import { clearCorrection, dependentStages, recordCorrection } from "./review.js";
import { normalizeProgress, sha, stagesFromAnalysis, validateState } from "./state.js";
function uppercase(value, field) {
    return text(value, field).toUpperCase();
}
function revisionMatches(payload, expected) {
    if (payload.revision !== undefined && expected !== null && payload.revision !== expected)
        throw new ProtocolError("event.payload.revision", "does not match reserved revision", { expected, actual: payload.revision });
}
function resetStageProgress(state) {
    for (const stage of state.stages) {
        stage.status = "proposed";
        stage.revision = 0;
        stage.human_status = "pending";
        stage.human_revision = 0;
    }
    state.current_stage = null;
}
function block(state, reason, detail, resumeStatus, transition, retryable = true) {
    state.status = "blocked";
    state.blocker = { reason, detail, resume_status: resumeStatus, retryable, source_transition: transition };
}
export function requestReopen(stateInput, seedsInput, reason, requestedBy = "reviewer") {
    const state = clone(stateInput);
    const seeds = [...new Set(seedsInput)];
    if (!seeds.length)
        throw new ProtocolError("reopen.seeds", "must not be empty");
    for (const seed of seeds) {
        const stage = state.stages.find((item) => item.id === seed);
        if (!stage || stage.status !== "pass")
            throw new ProtocolError("reopen.seeds", "only passed stages can be reopened", seed);
    }
    const affected = dependentStages(state, seeds);
    state.reopen = { requested_by: requestedBy, reason: text(reason, "reopen.reason"), seeds, affected, resume_status: state.status, resume_stage: state.current_stage };
    state.status = "waiting_reopen_approval";
    state.current_stage = null;
    state.pending = null;
    return validateState(state);
}
function applyReopenDecision(state, payload) {
    if (!state.reopen)
        throw new ProtocolError("state.reopen", "reopen decision requires a pending reopen request");
    const decision = uppercase(payload.decision, "event.payload.decision");
    const reopen = clone(state.reopen);
    state.reopen = null;
    if (decision === "REJECT") {
        state.status = reopen.resume_status;
        state.current_stage = reopen.resume_stage;
        return;
    }
    if (decision !== "APPROVE")
        throw new ProtocolError("event.payload.decision", "must be APPROVE or REJECT", decision);
    for (const stage of state.stages) {
        if (!reopen.affected.includes(stage.id))
            continue;
        stage.status = "proposed";
        stage.human_status = "pending";
        stage.human_revision = 0;
    }
    state.status = "planning";
    state.current_stage = state.stages.find((stage) => reopen.affected.includes(stage.id))?.id ?? null;
}
export async function applyEvent(_directory, input, eventInput, analysis, expectedStateRevision) {
    const event = clone(eventInput);
    const state = validateState(input, analysis && input.stages.length && !input.legacy_migrated ? analysis : undefined);
    if (expectedStateRevision !== undefined && state.state_revision !== expectedStateRevision)
        throw new ProtocolError("expected_state_revision", "state revision conflict", { expected: expectedStateRevision, actual: state.state_revision });
    const eventDigest = sha(event);
    const applied = state.applied[event.transition_id];
    if (applied) {
        if (applied.event_digest !== eventDigest)
            throw new ProtocolError("event.transition_id", "journal conflict: transition was already applied with different content", event.transition_id);
        return { state, result: clone(applied.result) };
    }
    if (!state.pending)
        throw new ProtocolError("state.pending", "event cannot be applied without a pending transition");
    if (event.transition_id !== state.pending.transition_id)
        throw new ProtocolError("event.transition_id", "does not match pending transition", { expected: state.pending.transition_id, actual: event.transition_id });
    const expectedType = EVENT_BY_ACTION[state.pending.action];
    if (event.type !== expectedType && event.type !== "task_failure")
        throw new ProtocolError("event.type", "does not match pending action", { action: state.pending.action, expected: expectedType, actual: event.type });
    const next = clone(state);
    const pending = next.pending;
    const payload = record(event.payload, "event.payload");
    const resumeStatus = next.status;
    revisionMatches(payload, pending.revision);
    next.pending = null;
    if (event.type === "task_failure") {
        block(next, text(payload.reason ?? "task_failure", "event.payload.reason"), text(payload.detail ?? "Agent task failed before a valid artifact was produced.", "event.payload.detail"), resumeStatus, event.transition_id, payload.retryable !== false);
    }
    else if (event.type === "discovery_result") {
        const status = uppercase(payload.status, "event.payload.status");
        if (status === "READY_FOR_REVIEW") {
            if (!analysis)
                throw new ProtocolError("analysis.json", "discovery result requires valid analysis");
            next.stages = stagesFromAnalysis(analysis);
            next.analysis_status = "review";
            next.status = "discovery_review";
            next.current_stage = null;
        }
        else if (status === "NEEDS_INPUT") {
            next.analysis_status = "draft";
            next.question_revision += 1;
            next.status = "waiting_answers";
            resetStageProgress(next);
            next.stages = [];
        }
        else if (status === "BLOCKED") {
            block(next, text(payload.reason ?? "discovery_blocked", "event.payload.reason"), text(payload.detail ?? "Discovery reported a blocker.", "event.payload.detail"), "discovery", event.transition_id);
        }
        else
            throw new ProtocolError("event.payload.status", "unsupported discovery result", status);
    }
    else if (event.type === "discovery_review_result") {
        const status = uppercase(payload.status, "event.payload.status");
        if (status === "PASS") {
            next.analysis_status = "reviewed";
            next.status = "waiting_map_approval";
            clearCorrection(next, "DISCOVERY");
        }
        else if (status === "REVISE") {
            next.analysis_status = "draft";
            next.status = "discovery";
            resetStageProgress(next);
            if (recordCorrection(next, "DISCOVERY", pending.revision ?? next.analysis_revision, payload))
                block(next, "non_converging_discovery", "The same discovery findings and evidence repeated without semantic progress.", "discovery", event.transition_id);
        }
        else if (status === "BLOCKED")
            block(next, text(payload.reason ?? "discovery_review_blocked", "event.payload.reason"), text(payload.detail ?? "Discovery reviewer reported a blocker.", "event.payload.detail"), "discovery_review", event.transition_id);
        else
            throw new ProtocolError("event.payload.status", "unsupported discovery review result", status);
    }
    else if (event.type === "answers") {
        next.feedback_revision += 1;
        next.status = "discovery";
        next.analysis_status = "draft";
    }
    else if (event.type === "map_decision") {
        const decision = uppercase(payload.decision, "event.payload.decision");
        if (decision === "APPROVE") {
            if (!next.stages.length)
                throw new ProtocolError("state.stages", "cannot approve an empty stage map");
            next.analysis_status = "approved";
            next.status = "planning";
            next.current_stage = next.stages[0].id;
        }
        else if (decision === "REVISE") {
            next.analysis_status = "draft";
            next.status = "discovery";
            resetStageProgress(next);
        }
        else
            throw new ProtocolError("event.payload.decision", "must be APPROVE or REVISE", decision);
    }
    else if (event.type === "stage_plan_result") {
        const status = uppercase(payload.status, "event.payload.status");
        const stage = next.stages.find((item) => item.id === pending.stage);
        if (status === "REVIEW")
            stage.status = "review";
        else if (status === "BLOCKED")
            block(next, text(payload.reason ?? "stage_plan_blocked", "event.payload.reason"), text(payload.detail ?? "Stage planner reported a blocker.", "event.payload.detail"), "planning", event.transition_id);
        else
            throw new ProtocolError("event.payload.status", "stage planner must return REVIEW or BLOCKED", status);
    }
    else if (event.type === "stage_review_result") {
        const reopen = Array.isArray(payload.reopen_stages) ? strings(payload.reopen_stages, "event.payload.reopen_stages", false) : [];
        if (reopen.length) {
            const requested = requestReopen(next, reopen, text(payload.reason ?? "Reviewer found a stale passed-stage contract.", "event.payload.reason"), "reviewer");
            Object.assign(next, requested);
        }
        else {
            const status = uppercase(payload.status, "event.payload.status");
            const stage = next.stages.find((item) => item.id === pending.stage);
            if (status === "PASS") {
                stage.status = "pass";
                clearCorrection(next, `TECHNICAL:${stage.id}`);
                next.current_stage = next.stages.find((item) => item.status !== "pass")?.id ?? null;
                normalizeProgress(next);
            }
            else if (status === "REVISE") {
                stage.status = "planning";
                stage.revision += 1;
                stage.human_status = "pending";
                stage.human_revision = 0;
                next.current_stage = stage.id;
                if (recordCorrection(next, `TECHNICAL:${stage.id}`, stage.revision, payload))
                    block(next, "non_converging_technical_review", `The same technical findings repeated for ${stage.id} without semantic progress.`, "planning", event.transition_id);
            }
            else if (status === "BLOCKED")
                block(next, text(payload.reason ?? "stage_review_blocked", "event.payload.reason"), text(payload.detail ?? "Technical reviewer reported a blocker.", "event.payload.detail"), "planning", event.transition_id);
            else
                throw new ProtocolError("event.payload.status", "unsupported stage review result", status);
        }
    }
    else if (event.type === "human_plan_result") {
        const status = uppercase(payload.status, "event.payload.status");
        const stage = next.stages.find((item) => item.id === pending.stage);
        if (status === "REVIEW")
            stage.human_status = "review";
        else if (status === "BLOCKED")
            block(next, text(payload.reason ?? "human_plan_blocked", "event.payload.reason"), text(payload.detail ?? "Human-review planner reported a blocker.", "event.payload.detail"), "human_reviewing", event.transition_id);
        else
            throw new ProtocolError("event.payload.status", "human-review planner must return REVIEW or BLOCKED", status);
    }
    else if (event.type === "human_review_result") {
        const reopen = Array.isArray(payload.reopen_stages) ? strings(payload.reopen_stages, "event.payload.reopen_stages", false) : [];
        if (reopen.length) {
            const requested = requestReopen(next, reopen, text(payload.reason ?? "Human reviewer found a stale passed-stage contract.", "event.payload.reason"), "reviewer");
            Object.assign(next, requested);
        }
        else {
            const status = uppercase(payload.status, "event.payload.status");
            const stage = next.stages.find((item) => item.id === pending.stage);
            if (status === "PASS") {
                stage.human_status = "pass";
                clearCorrection(next, `HUMAN:${stage.id}`);
                next.current_stage = next.stages.find((item) => item.human_status !== "pass")?.id ?? null;
                normalizeProgress(next);
            }
            else if (status === "REVISE") {
                stage.human_status = "planning";
                stage.human_revision += 1;
                next.current_stage = stage.id;
                if (recordCorrection(next, `HUMAN:${stage.id}`, stage.human_revision, payload))
                    block(next, "non_converging_human_review", `The same human-review findings repeated for ${stage.id} without semantic progress.`, "human_reviewing", event.transition_id);
            }
            else if (status === "BLOCKED")
                block(next, text(payload.reason ?? "human_review_blocked", "event.payload.reason"), text(payload.detail ?? "Human reviewer reported a blocker.", "event.payload.detail"), "human_reviewing", event.transition_id);
            else
                throw new ProtocolError("event.payload.status", "unsupported human review result", status);
        }
    }
    else if (event.type === "plan_decision") {
        const decision = uppercase(payload.decision, "event.payload.decision");
        if (decision === "APPROVE")
            next.status = "ready";
        else if (decision === "REVISE") {
            const stageId = typeof payload.stage === "string" ? payload.stage : next.stages[0]?.id;
            const stage = next.stages.find((item) => item.id === stageId);
            if (!stage)
                throw new ProtocolError("event.payload.stage", "unknown stage", stageId);
            stage.human_status = "planning";
            stage.human_revision += 1;
            next.status = "human_reviewing";
            next.current_stage = stage.id;
        }
        else
            throw new ProtocolError("event.payload.decision", "must be APPROVE or REVISE", decision);
    }
    else if (event.type === "reopen_decision")
        applyReopenDecision(next, payload);
    else if (event.type === "blocker_resolution") {
        if (!next.blocker)
            throw new ProtocolError("state.blocker", "resolution requires blocker");
        const decision = uppercase(payload.decision ?? payload.resolution, "event.payload.decision");
        const resume = next.blocker.resume_status;
        next.blocker = null;
        if (decision === "RETRY" || decision === "RESUME")
            next.status = resume;
        else if (decision === "REDISCOVER") {
            next.status = "discovery";
            next.analysis_status = "draft";
            resetStageProgress(next);
        }
        else
            throw new ProtocolError("event.payload.decision", "must be RETRY, RESUME, or REDISCOVER", decision);
    }
    next.state_revision += 1;
    const result = { transition_id: event.transition_id, event_type: event.type, status: next.status, state_revision: next.state_revision };
    next.applied[event.transition_id] = { event_digest: eventDigest, result: clone(result) };
    return { state: validateState(next, analysis && next.stages.length && !next.legacy_migrated ? analysis : undefined), result };
}
