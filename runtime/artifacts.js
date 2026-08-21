import { createHash } from "node:crypto";
import { lstat, readFile, realpath, stat } from "node:fs/promises";
import path from "node:path";
import { ProtocolError, canonicalRelative, integer, record, stageId, text } from "./schema.js";
const ARTIFACT_SCHEMA_VERSION = 1;
const ARTIFACT_FIELDS = ["schema_version", "artifact", "stage", "revision", "source_revision", "status"];
function digest(content) {
    return createHash("sha256").update(content).digest("hex");
}
function isWithin(base, candidate) {
    const relative = path.relative(path.resolve(base), path.resolve(candidate));
    return relative === "" || (relative !== ".." && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative));
}
function errorCode(error) {
    return error.code;
}
async function containedText(root, relativeInput, required) {
    const relative = canonicalRelative(relativeInput, "artifact.path");
    const absolute = path.resolve(root, ...relative.split("/"));
    if (!isWithin(root, absolute))
        throw new ProtocolError("artifact.path", "path escapes workflow root", relative);
    let entry;
    try {
        entry = await lstat(absolute);
    }
    catch (error) {
        if (errorCode(error) === "ENOENT" && !required)
            return null;
        throw new ProtocolError("artifact.path", required ? "required file is missing" : "cannot inspect file", { path: relative, error: String(error) });
    }
    if (!entry.isFile() && !entry.isSymbolicLink())
        throw new ProtocolError("artifact.path", "must resolve to a regular file", relative);
    let resolvedRoot;
    let resolvedCandidate;
    try {
        resolvedRoot = await realpath(root);
        resolvedCandidate = await realpath(absolute);
    }
    catch (error) {
        throw new ProtocolError("artifact.path", "cannot resolve file", { path: relative, error: String(error) });
    }
    if (!isWithin(resolvedRoot, resolvedCandidate))
        throw new ProtocolError("artifact.path", "symlink escapes workflow root", relative);
    const resolvedStat = await stat(resolvedCandidate);
    if (!resolvedStat.isFile())
        throw new ProtocolError("artifact.path", "must resolve to a regular file", relative);
    try {
        return await readFile(resolvedCandidate, "utf8");
    }
    catch (error) {
        throw new ProtocolError("artifact.path", "cannot read file", { path: relative, error: String(error) });
    }
}
function frontmatter(content, field) {
    const lines = content.split(/\r?\n/);
    if (lines[0] !== "---")
        throw new ProtocolError(field, "frontmatter start delimiter is missing");
    const end = lines.indexOf("---", 1);
    if (end < 0)
        throw new ProtocolError(field, "frontmatter end delimiter is missing");
    const values = new Map();
    for (const [index, line] of lines.slice(1, end).entries()) {
        const separator = line.indexOf(":");
        if (separator <= 0)
            throw new ProtocolError(`${field}[${index}]`, "expected key: value", line);
        const key = line.slice(0, separator).trim();
        const value = line.slice(separator + 1).trim();
        if (!key || !value)
            throw new ProtocolError(`${field}.${key || index}`, "key and value must be non-empty", line);
        if (values.has(key))
            throw new ProtocolError(`${field}.${key}`, "duplicate frontmatter field");
        values.set(key, value);
    }
    return { values, body: lines.slice(end + 1).join("\n").trim() };
}
function parseInteger(value, field) {
    if (value === undefined || !/^(?:0|[1-9][0-9]*)$/.test(value))
        throw new ProtocolError(field, "must be a non-negative integer", value);
    return integer(Number(value), field);
}
export function parseArtifactMetadata(content, field = "artifact") {
    const parsed = frontmatter(content, `${field}.frontmatter`);
    const actual = [...parsed.values.keys()].sort();
    const expected = [...ARTIFACT_FIELDS].sort();
    if (JSON.stringify(actual) !== JSON.stringify(expected)) {
        throw new ProtocolError(`${field}.frontmatter`, "field mismatch", {
            missing: expected.filter((item) => !actual.includes(item)),
            unknown: actual.filter((item) => !expected.includes(item)),
        });
    }
    if (!parsed.body)
        throw new ProtocolError(`${field}.body`, "must not be empty");
    const schemaVersion = parseInteger(parsed.values.get("schema_version"), `${field}.schema_version`);
    if (schemaVersion !== ARTIFACT_SCHEMA_VERSION)
        throw new ProtocolError(`${field}.schema_version`, `must be ${ARTIFACT_SCHEMA_VERSION}`, schemaVersion);
    const artifact = text(parsed.values.get("artifact"), `${field}.artifact`);
    const rawStage = text(parsed.values.get("stage"), `${field}.stage`);
    const stage = rawStage === "none" ? null : stageId(rawStage, `${field}.stage`);
    return {
        schema_version: schemaVersion,
        artifact,
        stage,
        revision: parseInteger(parsed.values.get("revision"), `${field}.revision`),
        source_revision: parseInteger(parsed.values.get("source_revision"), `${field}.source_revision`),
        status: text(parsed.values.get("status"), `${field}.status`),
    };
}
function looseMetadata(content) {
    if (!content.startsWith("---\n") && !content.startsWith("---\r\n"))
        return null;
    try {
        const parsed = frontmatter(content, "snapshot.frontmatter");
        const numberOrNull = (name) => {
            const value = parsed.values.get(name);
            return value !== undefined && /^(?:0|[1-9][0-9]*)$/.test(value) ? Number(value) : null;
        };
        const rawStage = parsed.values.get("stage");
        return {
            schema_version: numberOrNull("schema_version"),
            artifact: parsed.values.get("artifact") ?? null,
            stage: !rawStage || rawStage === "none" ? null : rawStage,
            revision: numberOrNull("revision") ?? numberOrNull("state_revision"),
            source_revision: numberOrNull("source_revision"),
            status: parsed.values.get("status") ?? null,
        };
    }
    catch {
        return null;
    }
}
export async function captureSnapshot(root, relativeInput, contentOverride) {
    const relative = canonicalRelative(relativeInput, "snapshot.path");
    const content = contentOverride === undefined ? await containedText(root, relative, false) : contentOverride;
    if (content === null)
        return { path: relative, exists: false, digest: null, metadata: null };
    return { path: relative, exists: true, digest: digest(content), metadata: looseMetadata(content) };
}
export async function capturePendingSnapshots(root, pending, overrides = {}) {
    pending.input_snapshot = [];
    for (const relative of pending.inputs)
        pending.input_snapshot.push(await captureSnapshot(root, relative, overrides[relative]));
    pending.output_snapshot = pending.output === null ? null : await captureSnapshot(root, pending.output, overrides[pending.output]);
    pending.snapshots_captured = true;
}
function snapshotEqual(left, right) {
    return JSON.stringify(left) === JSON.stringify(right);
}
function mutableInputPaths(pending) {
    const result = new Set();
    if (pending.output)
        result.add(pending.output);
    if (pending.action === "DISCOVER") {
        result.add("analysis.json");
        result.add("discovery.md");
        result.add("questions.md");
    }
    return result;
}
export async function assertInputSnapshotsCurrent(root, pending) {
    if (!pending.snapshots_captured)
        throw new ProtocolError("state.pending.snapshots_captured", "pending transition has no immutable snapshot");
    if (pending.input_snapshot.length !== pending.inputs.length)
        throw new ProtocolError("state.pending.input_snapshot", "snapshot count does not match inputs");
    const mutable = mutableInputPaths(pending);
    for (const expected of pending.input_snapshot) {
        if (mutable.has(expected.path))
            continue;
        const actual = await captureSnapshot(root, expected.path);
        if (!snapshotEqual(expected, actual))
            throw new ProtocolError("state.pending.input_snapshot", "reserved input is stale or changed", { path: expected.path, expected, actual });
    }
}
export async function assertFreshPrimaryOutput(root, pending) {
    if (!pending.output)
        throw new ProtocolError("state.pending.output", "agent success requires a canonical output path");
    if (!pending.output_snapshot)
        throw new ProtocolError("state.pending.output_snapshot", "pending transition has no output baseline");
    const actual = await captureSnapshot(root, pending.output);
    if (!actual.exists)
        throw new ProtocolError("state.pending.output", "reserved output artifact is missing", pending.output);
    if (snapshotEqual(pending.output_snapshot, actual))
        throw new ProtocolError("state.pending.output", "reserved output is stale and was not regenerated", pending.output);
}
export async function assertArtifact(root, relativeInput, expected) {
    const relative = canonicalRelative(relativeInput, "artifact.path");
    const content = await containedText(root, relative, true);
    const actual = parseArtifactMetadata(content, relative);
    const contract = {
        schema_version: ARTIFACT_SCHEMA_VERSION,
        artifact: expected.artifact,
        stage: expected.stage,
        revision: expected.revision,
        source_revision: expected.source_revision,
        status: expected.status,
    };
    if (JSON.stringify(actual) !== JSON.stringify(contract))
        throw new ProtocolError(relative, "artifact contract mismatch", { expected: contract, actual });
    return actual;
}
function payloadStatus(event) {
    const payload = record(event.payload, "event.payload");
    return typeof payload.status === "string" ? payload.status : null;
}
export async function assertPendingOutputContracts(root, state, event, analysis) {
    const pending = state.pending;
    if (!pending)
        throw new ProtocolError("state.pending", "output validation requires pending action");
    if (event.type === "task_failure")
        return;
    const status = payloadStatus(event);
    if (status === "BLOCKED" || status === null)
        return;
    if (pending.action === "DISCOVER") {
        if (status !== "READY_FOR_REVIEW")
            return;
        if (!analysis)
            throw new ProtocolError("analysis.json", "READY_FOR_REVIEW requires a valid analysis artifact");
        await assertFreshPrimaryOutput(root, pending);
        const discoveryBaseline = pending.input_snapshot.find((snapshot) => snapshot.path === "discovery.md");
        const discoveryCurrent = await captureSnapshot(root, "discovery.md");
        if (!discoveryCurrent.exists || (discoveryBaseline && snapshotEqual(discoveryBaseline, discoveryCurrent)))
            throw new ProtocolError("discovery.md", "discovery artifact is missing or stale");
        await assertArtifact(root, "discovery.md", {
            artifact: "discovery",
            stage: null,
            revision: pending.revision,
            source_revision: Math.max(0, pending.revision - 1),
            status,
        });
        return;
    }
    if (!new Set(["REVIEW_DISCOVERY", "PLAN_STAGE", "REVIEW_STAGE", "PLAN_HUMAN_REVIEW", "REVIEW_HUMAN_REVIEW"]).has(pending.action))
        return;
    await assertFreshPrimaryOutput(root, pending);
    if (!pending.output)
        throw new ProtocolError("state.pending.output", "agent result requires output");
    if (pending.action === "REVIEW_DISCOVERY") {
        await assertArtifact(root, pending.output, { artifact: "discovery-review", stage: null, revision: pending.revision, source_revision: pending.revision, status });
    }
    else if (pending.action === "PLAN_STAGE") {
        await assertArtifact(root, pending.output, { artifact: "technical-stage", stage: pending.stage, revision: pending.revision, source_revision: pending.source_revision, status });
    }
    else if (pending.action === "REVIEW_STAGE") {
        await assertArtifact(root, pending.output, { artifact: "technical-review", stage: pending.stage, revision: pending.revision, source_revision: pending.source_revision, status });
    }
    else if (pending.action === "PLAN_HUMAN_REVIEW") {
        await assertArtifact(root, pending.output, { artifact: "human-review", stage: pending.stage, revision: pending.revision, source_revision: pending.source_revision, status });
    }
    else {
        await assertArtifact(root, pending.output, { artifact: "human-review-review", stage: pending.stage, revision: pending.revision, source_revision: pending.source_revision, status });
    }
}
export async function assertCompleteArtifactGraph(root, state, analysis) {
    if (!analysis)
        throw new ProtocolError("analysis.json", "complete artifact graph requires valid analysis.json");
    if (!state.stages.length)
        throw new ProtocolError("state.stages", "complete artifact graph requires an approved stage map");
    await assertArtifact(root, "discovery.md", {
        artifact: "discovery",
        stage: null,
        revision: state.analysis_revision,
        source_revision: Math.max(0, state.analysis_revision - 1),
        status: "READY_FOR_REVIEW",
    });
    await assertArtifact(root, "reviews/discovery.md", {
        artifact: "discovery-review",
        stage: null,
        revision: state.analysis_revision,
        source_revision: state.analysis_revision,
        status: "PASS",
    });
    for (const stage of state.stages) {
        if (stage.status !== "pass" || stage.human_status !== "pass")
            throw new ProtocolError("state.stages", "complete artifact graph requires technical and human PASS statuses", stage.id);
        await assertArtifact(root, stage.details, {
            artifact: "technical-stage",
            stage: stage.id,
            revision: stage.revision,
            source_revision: state.analysis_revision,
            status: "REVIEW",
        });
        await assertArtifact(root, stage.review, {
            artifact: "technical-review",
            stage: stage.id,
            revision: stage.revision,
            source_revision: stage.revision,
            status: "PASS",
        });
        await assertArtifact(root, stage.human_review, {
            artifact: "human-review",
            stage: stage.id,
            revision: stage.human_revision,
            source_revision: stage.revision,
            status: "REVIEW",
        });
        await assertArtifact(root, stage.human_review_review, {
            artifact: "human-review-review",
            stage: stage.id,
            revision: stage.human_revision,
            source_revision: stage.revision,
            status: "PASS",
        });
    }
}
