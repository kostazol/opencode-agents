import { createHash } from "node:crypto";
import { EVENT_BY_ACTION, HUMAN_STATUSES, ProtocolError, STAGE_STATUSES, STATE_SCHEMA_VERSION, WORKFLOW_STATUSES, boolean, canonicalRelative, clone, exactFields, integer, record, stageId, strings, text } from "./schema.js";
import { validateAnalysis } from "./analysis.js";
export function migrateState(input) {
    const raw = clone(record(input, "state"));
    const version = integer(raw.schema_version, "state.schema_version", 1);
    if (version === STATE_SCHEMA_VERSION)
        return { state: raw, migrated: false, from_version: version, to_version: version, invalidated_transition: null };
    if (version !== 1 || STATE_SCHEMA_VERSION !== 2)
        throw new ProtocolError("state.schema_version", `cannot migrate schema ${version} to ${STATE_SCHEMA_VERSION}`);
    const oldPending = raw.pending && typeof raw.pending === "object" && !Array.isArray(raw.pending) ? raw.pending : null;
    const invalidated = oldPending && typeof oldPending.transition_id === "string" ? oldPending.transition_id : null;
    raw.schema_version = STATE_SCHEMA_VERSION;
    if (oldPending) {
        const previousStatus = typeof raw.status === "string" && WORKFLOW_STATUSES.has(raw.status) ? raw.status : "discovery";
        const resumeStatus = previousStatus === "ready" || previousStatus === "blocked" ? "discovery" : previousStatus;
        raw.pending = null;
        raw.status = "blocked";
        raw.blocker = {
            reason: "state_schema_migration_requires_retry",
            detail: "The v1 pending transition had no immutable input snapshot and was invalidated safely; retry the action.",
            resume_status: resumeStatus,
            retryable: true,
            source_transition: invalidated ?? "schema-v1",
        };
    }
    return { state: raw, migrated: true, from_version: version, to_version: STATE_SCHEMA_VERSION, invalidated_transition: invalidated };
}
function validateMetadata(input, field) {
    const metadata = record(input, field);
    exactFields(metadata, ["schema_version", "artifact", "stage", "revision", "source_revision", "status"], field);
    for (const name of ["schema_version", "revision", "source_revision"])
        if (metadata[name] !== null)
            metadata[name] = integer(metadata[name], `${field}.${name}`);
    if (metadata.artifact !== null)
        metadata.artifact = text(metadata.artifact, `${field}.artifact`);
    if (metadata.stage !== null)
        metadata.stage = stageId(metadata.stage, `${field}.stage`);
    if (metadata.status !== null)
        metadata.status = text(metadata.status, `${field}.status`);
    return metadata;
}
function validateSnapshot(input, field) {
    const snapshot = record(input, field);
    exactFields(snapshot, ["path", "exists", "digest", "metadata"], field);
    snapshot.path = canonicalRelative(snapshot.path, `${field}.path`);
    snapshot.exists = boolean(snapshot.exists, `${field}.exists`);
    if (snapshot.exists) {
        const value = text(snapshot.digest, `${field}.digest`);
        if (!/^[0-9a-f]{64}$/.test(value))
            throw new ProtocolError(`${field}.digest`, "must be a SHA-256 digest", value);
        snapshot.digest = value;
    }
    else if (snapshot.digest !== null) {
        throw new ProtocolError(`${field}.digest`, "must be null when the path did not exist", snapshot.digest);
    }
    snapshot.metadata = snapshot.metadata === null ? null : validateMetadata(snapshot.metadata, `${field}.metadata`);
    if (!snapshot.exists && snapshot.metadata !== null)
        throw new ProtocolError(`${field}.metadata`, "must be null when the path did not exist");
    return snapshot;
}
export function newState(requestId) {
    if (!/^[a-z0-9][a-z0-9-]{0,79}$/.test(requestId))
        throw new ProtocolError("request_id", "must be lower kebab-case and at most 80 characters", requestId);
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
    };
}
export function stagesFromAnalysis(analysis) {
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
    }));
}
export function stageMap(state) {
    return new Map(state.stages.map((item) => [item.id, item]));
}
function assertLegalStateMatrix(state) {
    const allTechnicalPass = state.stages.length > 0 && state.stages.every((stage) => stage.status === "pass");
    const allHumanPass = state.stages.length > 0 && state.stages.every((stage) => stage.human_status === "pass");
    const anyTechnicalPass = state.stages.some((stage) => stage.status === "pass");
    const anyHumanProgress = state.stages.some((stage) => stage.human_status !== "pending");
    const pendingByStatus = {
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
    };
    if (state.pending && !pendingByStatus[state.status].has(state.pending.action)) {
        throw new ProtocolError("state.pending.action", "action is illegal for workflow status", { status: state.status, action: state.pending.action });
    }
    if (state.status === "ready" && state.pending)
        throw new ProtocolError("state.pending", "ready state cannot have a pending action");
    if (state.status === "discovery") {
        if (!new Set(["missing", "draft"]).has(state.analysis_status))
            throw new ProtocolError("state.analysis_status", "discovery requires missing or draft analysis", state.analysis_status);
        if (anyTechnicalPass || anyHumanProgress)
            throw new ProtocolError("state.stages", "discovery cannot retain approved stage progress");
    }
    else if (state.status === "discovery_review") {
        if (state.analysis_status !== "review" || !state.stages.length)
            throw new ProtocolError("state", "discovery_review requires reviewed candidate analysis and a non-empty stage map");
        if (anyTechnicalPass || anyHumanProgress)
            throw new ProtocolError("state.stages", "discovery review cannot contain passed stage work");
    }
    else if (state.status === "waiting_answers") {
        if (!new Set(["draft", "missing"]).has(state.analysis_status))
            throw new ProtocolError("state.analysis_status", "waiting_answers requires unfinished analysis");
    }
    else if (state.status === "waiting_map_approval") {
        if (state.analysis_status !== "reviewed" || !state.stages.length)
            throw new ProtocolError("state", "waiting_map_approval requires a reviewed non-empty stage map");
        if (state.stages.some((stage) => stage.status !== "proposed" || stage.human_status !== "pending"))
            throw new ProtocolError("state.stages", "map approval must precede stage execution");
    }
    else if (state.status === "planning") {
        if (state.analysis_status !== "approved" || !state.stages.length || !state.current_stage)
            throw new ProtocolError("state", "planning requires an approved non-empty stage map and current stage");
        if (allTechnicalPass || anyHumanProgress)
            throw new ProtocolError("state.stages", "planning must have unfinished technical work and no human-review progress");
        const currentIndex = state.stages.findIndex((stage) => stage.id === state.current_stage);
        if (currentIndex < 0)
            throw new ProtocolError("state.current_stage", "unknown current stage", state.current_stage);
        if (state.stages.slice(0, currentIndex).some((stage) => stage.status !== "pass"))
            throw new ProtocolError("state.stages", "stages before current stage must pass");
        if (state.stages.slice(currentIndex + 1).some((stage) => stage.status !== "proposed"))
            throw new ProtocolError("state.stages", "stages after current stage must remain proposed");
    }
    else if (state.status === "human_reviewing") {
        if (state.analysis_status !== "approved" || !state.stages.length || !state.current_stage || !allTechnicalPass || allHumanPass)
            throw new ProtocolError("state", "human_reviewing requires all technical stages passed and unfinished human review");
        const currentIndex = state.stages.findIndex((stage) => stage.id === state.current_stage);
        if (state.stages.slice(0, currentIndex).some((stage) => stage.human_status !== "pass"))
            throw new ProtocolError("state.stages", "human reviews before current stage must pass");
        if (state.stages.slice(currentIndex + 1).some((stage) => stage.human_status !== "pending"))
            throw new ProtocolError("state.stages", "future human reviews must remain pending");
    }
    else if (state.status === "waiting_plan_approval" || state.status === "ready") {
        if (state.analysis_status !== "approved" || !state.stages.length || !allTechnicalPass || !allHumanPass || state.current_stage !== null) {
            throw new ProtocolError("state", `${state.status} requires a non-empty approved stage map and complete PASS statuses`);
        }
    }
    else if (state.status === "waiting_reopen_approval") {
        if (state.analysis_status !== "approved" || !state.stages.length || state.reopen === null)
            throw new ProtocolError("state", "reopen approval requires an approved non-empty stage map");
    }
    if (state.pending?.action === "PLAN_STAGE" || state.pending?.action === "REVIEW_STAGE") {
        if (state.pending.stage !== state.current_stage)
            throw new ProtocolError("state.pending.stage", "technical action must target current stage");
        const current = state.stages.find((stage) => stage.id === state.current_stage);
        const expected = state.pending.action === "PLAN_STAGE" ? "planning" : "review";
        if (current.status !== expected)
            throw new ProtocolError("state.pending.action", "technical action does not match current stage status", { action: state.pending.action, stage_status: current.status });
    }
    if (state.pending?.action === "PLAN_HUMAN_REVIEW" || state.pending?.action === "REVIEW_HUMAN_REVIEW") {
        if (state.pending.stage !== state.current_stage)
            throw new ProtocolError("state.pending.stage", "human-review action must target current stage");
        const current = state.stages.find((stage) => stage.id === state.current_stage);
        const expected = state.pending.action === "PLAN_HUMAN_REVIEW" ? "planning" : "review";
        if (current.human_status !== expected)
            throw new ProtocolError("state.pending.action", "human-review action does not match current stage status", { action: state.pending.action, human_status: current.human_status });
    }
}
export function validateState(input, analysisInput) {
    const state = clone(record(input, "state"));
    exactFields(state, [
        "schema_version", "request_id", "state_revision", "sequence", "status", "current_stage",
        "analysis_revision", "analysis_status", "question_revision", "feedback_revision", "stages",
        "pending", "applied", "blocker", "reopen", "convergence", "legacy_migrated",
    ], "state");
    if (state.schema_version !== STATE_SCHEMA_VERSION)
        throw new ProtocolError("state.schema_version", `must be ${STATE_SCHEMA_VERSION}`, state.schema_version);
    if (!/^[a-z0-9][a-z0-9-]{0,79}$/.test(state.request_id))
        throw new ProtocolError("state.request_id", "invalid request id", state.request_id);
    for (const field of ["state_revision", "sequence", "analysis_revision", "question_revision", "feedback_revision"])
        integer(state[field], `state.${field}`);
    if (!WORKFLOW_STATUSES.has(state.status))
        throw new ProtocolError("state.status", "unsupported status", state.status);
    if (!new Set(["missing", "draft", "review", "reviewed", "approved"]).has(state.analysis_status))
        throw new ProtocolError("state.analysis_status", "unsupported status", state.analysis_status);
    if (!Array.isArray(state.stages))
        throw new ProtocolError("state.stages", "must be an array");
    const seen = new Set();
    for (const [index, stage] of state.stages.entries()) {
        const field = `state.stages[${index}]`;
        exactFields(stage, [
            "id", "title", "slug", "depends_on", "status", "revision", "human_status", "human_revision",
            "details", "review", "human_review", "human_review_review",
        ], field);
        const id = stageId(stage.id, `${field}.id`);
        if (id !== `S${String(index + 1).padStart(2, "0")}`)
            throw new ProtocolError(`${field}.id`, "stages must be contiguous and ordered", id);
        stage.title = text(stage.title, `${field}.title`);
        stage.slug = text(stage.slug, `${field}.slug`);
        if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(stage.slug))
            throw new ProtocolError(`${field}.slug`, "must be lower kebab-case", stage.slug);
        stage.depends_on = strings(stage.depends_on, `${field}.depends_on`);
        for (const dependency of stage.depends_on)
            if (!seen.has(dependency))
                throw new ProtocolError(`${field}.depends_on`, "must reference earlier stages", dependency);
        seen.add(id);
        if (!STAGE_STATUSES.has(stage.status))
            throw new ProtocolError(`${field}.status`, "unsupported stage status", stage.status);
        if (!HUMAN_STATUSES.has(stage.human_status))
            throw new ProtocolError(`${field}.human_status`, "unsupported human-review status", stage.human_status);
        integer(stage.revision, `${field}.revision`);
        integer(stage.human_revision, `${field}.human_revision`);
        stage.details = canonicalRelative(stage.details, `${field}.details`, "stages/");
        stage.review = canonicalRelative(stage.review, `${field}.review`, "reviews/");
        stage.human_review = canonicalRelative(stage.human_review, `${field}.human_review`, "stages/");
        stage.human_review_review = canonicalRelative(stage.human_review_review, `${field}.human_review_review`, "reviews/");
        if (stage.status === "pass" && stage.revision === 0)
            throw new ProtocolError(`${field}.revision`, "passed stage requires a revision");
        if (stage.human_status === "pass" && stage.human_revision === 0)
            throw new ProtocolError(`${field}.human_revision`, "passed human review requires a revision");
    }
    if (state.current_stage !== null) {
        state.current_stage = stageId(state.current_stage, "state.current_stage");
        if (!seen.has(state.current_stage))
            throw new ProtocolError("state.current_stage", "unknown stage", state.current_stage);
    }
    if ((state.status === "planning" || state.status === "human_reviewing") && state.stages.length && state.current_stage === null)
        throw new ProtocolError("state.current_stage", "active workflow requires a stage");
    if (state.pending !== null) {
        const pending = record(state.pending, "state.pending");
        exactFields(pending, [
            "transition_id", "action", "actor", "mode", "stage", "revision", "source_revision",
            "inputs", "input_snapshot", "output", "output_snapshot", "snapshots_captured", "reason", "issued_state_revision",
        ], "state.pending");
        pending.transition_id = text(pending.transition_id, "state.pending.transition_id");
        pending.action = text(pending.action, "state.pending.action");
        if (!EVENT_BY_ACTION[pending.action])
            throw new ProtocolError("state.pending.action", "unsupported action", pending.action);
        pending.actor = text(pending.actor, "state.pending.actor");
        if (pending.mode !== null)
            pending.mode = text(pending.mode, "state.pending.mode");
        if (pending.stage !== null) {
            pending.stage = stageId(pending.stage, "state.pending.stage");
            if (!seen.has(pending.stage))
                throw new ProtocolError("state.pending.stage", "unknown stage", pending.stage);
        }
        if (pending.revision !== null)
            pending.revision = integer(pending.revision, "state.pending.revision", 1);
        if (pending.source_revision !== null)
            pending.source_revision = integer(pending.source_revision, "state.pending.source_revision");
        pending.inputs = strings(pending.inputs, "state.pending.inputs").map((value, index) => canonicalRelative(value, `state.pending.inputs[${index}]`));
        if (!Array.isArray(pending.input_snapshot))
            throw new ProtocolError("state.pending.input_snapshot", "must be an array");
        pending.input_snapshot = pending.input_snapshot.map((item, index) => validateSnapshot(item, `state.pending.input_snapshot[${index}]`));
        if (pending.output !== null)
            pending.output = canonicalRelative(pending.output, "state.pending.output");
        pending.output_snapshot = pending.output_snapshot === null ? null : validateSnapshot(pending.output_snapshot, "state.pending.output_snapshot");
        pending.snapshots_captured = boolean(pending.snapshots_captured, "state.pending.snapshots_captured");
        if (pending.snapshots_captured) {
            if (pending.input_snapshot.length !== pending.inputs.length)
                throw new ProtocolError("state.pending.input_snapshot", "must contain one immutable snapshot per input");
            pending.input_snapshot.forEach((snapshot, index) => {
                if (snapshot.path !== pending.inputs[index])
                    throw new ProtocolError(`state.pending.input_snapshot[${index}].path`, "must match the corresponding input", snapshot.path);
            });
            if ((pending.output === null) !== (pending.output_snapshot === null))
                throw new ProtocolError("state.pending.output_snapshot", "must exist exactly when output is reserved");
            if (pending.output !== null && pending.output_snapshot.path !== pending.output)
                throw new ProtocolError("state.pending.output_snapshot.path", "must match reserved output", pending.output_snapshot.path);
        }
        else if (pending.input_snapshot.length || pending.output_snapshot !== null) {
            throw new ProtocolError("state.pending.snapshots_captured", "uncaptured transition cannot contain partial snapshots");
        }
        pending.reason = text(pending.reason, "state.pending.reason");
        pending.issued_state_revision = integer(pending.issued_state_revision, "state.pending.issued_state_revision");
        if (pending.issued_state_revision !== state.state_revision)
            throw new ProtocolError("state.pending.issued_state_revision", "must equal state revision");
        state.pending = pending;
    }
    const applied = record(state.applied, "state.applied");
    for (const [transition, raw] of Object.entries(applied)) {
        text(transition, "state.applied.transition_id");
        const item = record(raw, `state.applied.${transition}`);
        exactFields(item, ["event_digest", "result"], `state.applied.${transition}`);
        const eventDigest = text(item.event_digest, `state.applied.${transition}.event_digest`);
        if (!/^[0-9a-f]{64}$/.test(eventDigest))
            throw new ProtocolError(`state.applied.${transition}.event_digest`, "must be a SHA-256 digest", eventDigest);
        record(item.result, `state.applied.${transition}.result`);
    }
    if ((state.status === "blocked") !== (state.blocker !== null))
        throw new ProtocolError("state.blocker", "must exist exactly while blocked");
    if (state.blocker !== null) {
        const blocker = record(state.blocker, "state.blocker");
        exactFields(blocker, ["reason", "detail", "resume_status", "retryable", "source_transition"], "state.blocker");
        text(blocker.reason, "state.blocker.reason");
        text(blocker.detail, "state.blocker.detail");
        const resume = text(blocker.resume_status, "state.blocker.resume_status");
        if (!WORKFLOW_STATUSES.has(resume) || resume === "blocked" || resume === "ready")
            throw new ProtocolError("state.blocker.resume_status", "unsupported resume status", resume);
        boolean(blocker.retryable, "state.blocker.retryable");
        text(blocker.source_transition, "state.blocker.source_transition");
    }
    if ((state.status === "waiting_reopen_approval") !== (state.reopen !== null))
        throw new ProtocolError("state.reopen", "must exist exactly while waiting for reopening approval");
    if (state.reopen !== null) {
        const reopen = record(state.reopen, "state.reopen");
        exactFields(reopen, ["requested_by", "reason", "seeds", "affected", "resume_status", "resume_stage"], "state.reopen");
        const requestedBy = text(reopen.requested_by, "state.reopen.requested_by");
        if (!new Set(["reviewer", "user"]).has(requestedBy))
            throw new ProtocolError("state.reopen.requested_by", "unsupported requester", requestedBy);
        text(reopen.reason, "state.reopen.reason");
        const seeds = strings(reopen.seeds, "state.reopen.seeds", false).map((value) => stageId(value, "state.reopen.seeds"));
        const affected = strings(reopen.affected, "state.reopen.affected", false).map((value) => stageId(value, "state.reopen.affected"));
        for (const value of [...seeds, ...affected])
            if (!seen.has(value))
                throw new ProtocolError("state.reopen", "references unknown stage", value);
        for (const seed of seeds)
            if (!affected.includes(seed))
                throw new ProtocolError("state.reopen", "affected stages must include seeds", seed);
        const resume = text(reopen.resume_status, "state.reopen.resume_status");
        if (!WORKFLOW_STATUSES.has(resume) || new Set(["blocked", "ready", "waiting_reopen_approval"]).has(resume))
            throw new ProtocolError("state.reopen.resume_status", "unsupported resume status", resume);
        if (reopen.resume_stage !== null) {
            const resumeStage = stageId(reopen.resume_stage, "state.reopen.resume_stage");
            if (!seen.has(resumeStage))
                throw new ProtocolError("state.reopen.resume_stage", "unknown stage", resumeStage);
        }
    }
    const convergence = record(state.convergence, "state.convergence");
    for (const [key, raw] of Object.entries(convergence)) {
        text(key, "state.convergence.key");
        const item = record(raw, `state.convergence.${key}`);
        exactFields(item, ["fingerprint", "evidence_digest", "repeats", "last_revision"], `state.convergence.${key}`);
        for (const field of ["fingerprint", "evidence_digest"]) {
            const value = text(item[field], `state.convergence.${key}.${field}`);
            if (!/^[0-9a-f]{64}$/.test(value))
                throw new ProtocolError(`state.convergence.${key}.${field}`, "must be a SHA-256 digest", value);
        }
        integer(item.repeats, `state.convergence.${key}.repeats`, 1);
        integer(item.last_revision, `state.convergence.${key}.last_revision`, 1);
    }
    if (typeof state.legacy_migrated !== "boolean")
        throw new ProtocolError("state.legacy_migrated", "must be boolean");
    assertLegalStateMatrix(state);
    if (analysisInput !== undefined && state.stages.length) {
        const analysis = validateAnalysis(analysisInput);
        const actual = state.stages.map((item) => [item.id, item.title, item.slug, item.depends_on]);
        const expected = analysis.stages.map((item) => [item.id, item.title, item.slug, item.depends_on]);
        if (JSON.stringify(actual) !== JSON.stringify(expected))
            throw new ProtocolError("state.stages", "state stage map does not match analysis");
    }
    return state;
}
export function stableJson(value) {
    if (value === null || typeof value !== "object")
        return JSON.stringify(value);
    if (Array.isArray(value))
        return `[${value.map(stableJson).join(",")}]`;
    return `{${Object.entries(value).sort(([left], [right]) => left.localeCompare(right)).map(([key, item]) => `${JSON.stringify(key)}:${stableJson(item)}`).join(",")}}`;
}
export function sha(value) {
    return createHash("sha256").update(typeof value === "string" ? value : stableJson(value)).digest("hex");
}
export function transitionId(state, action, stage, revision) {
    return `T${String(state.sequence).padStart(6, "0")}-${sha(`${state.request_id}|${state.sequence}|${action}|${stage ?? "-"}|${revision ?? 0}`).slice(0, 12)}`;
}
export function pendingAction(state, action, actor, reason, options = {}) {
    state.sequence += 1;
    state.state_revision += 1;
    const result = {
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
    };
    state.pending = result;
    return result;
}
export function normalizeProgress(state) {
    if (state.status === "planning" && state.stages.length && state.stages.every((item) => item.status === "pass")) {
        state.status = "human_reviewing";
        state.current_stage = state.stages.find((item) => item.human_status !== "pass")?.id ?? null;
    }
    if (state.status === "human_reviewing" && state.stages.length && state.stages.every((item) => item.human_status === "pass")) {
        state.status = "waiting_plan_approval";
        state.current_stage = null;
    }
}
export function completeAction(state) {
    return { transition_id: null, action: "COMPLETE", actor: "none", mode: null, stage: null, revision: null, source_revision: null, inputs: ["plan.md"], output: null, reason: "workflow-ready", issued_state_revision: state.state_revision };
}
