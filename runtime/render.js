import { createHash } from "node:crypto";
import { ProtocolError } from "./schema.js";
import { newState } from "./state.js";
function yaml(value) {
    return value === null ? "null" : value;
}
export function renderPlan(state, analysis) {
    const lines = [
        "---",
        `schema_version: ${state.schema_version}`,
        `request_id: ${state.request_id}`,
        `state_revision: ${state.state_revision}`,
        `status: ${state.status}`,
        `analysis_revision: ${state.analysis_revision}`,
        `analysis_status: ${state.analysis_status}`,
        `current_stage: ${yaml(state.current_stage)}`,
        `legacy_migrated: ${state.legacy_migrated}`,
        "---",
        "",
        `# Plan: ${state.request_id}`,
        "",
        `Workflow status: **${state.status}**`,
        "",
    ];
    if (analysis) {
        lines.push("## Request", "", analysis.request.summary, "");
        if (analysis.request.outcomes.length) {
            lines.push("### Outcomes", "", ...analysis.request.outcomes.map((item) => `- ${item}`), "");
        }
    }
    lines.push("## Stage map", "");
    if (!state.stages.length)
        lines.push("No approved stage map yet.", "");
    for (const stage of state.stages) {
        lines.push(`### ${stage.id}: ${stage.title}`, "", `- Slug: ${stage.slug}`, `- Depends on: ${stage.depends_on.length ? stage.depends_on.join(", ") : "none"}`, `- Technical status: ${stage.status}`, `- Technical revision: ${stage.revision}`, `- Human status: ${stage.human_status}`, `- Human revision: ${stage.human_revision}`, `- Technical artifact: ${stage.details}`, `- Technical review: ${stage.review}`, `- Human artifact: ${stage.human_review}`, `- Human review: ${stage.human_review_review}`, "");
    }
    if (state.pending) {
        lines.push("## Pending transition", "", `- Transition: ${state.pending.transition_id}`, `- Action: ${state.pending.action}`, `- Actor: ${state.pending.actor}`, `- Stage: ${yaml(state.pending.stage)}`, `- Revision: ${state.pending.revision ?? "null"}`, `- Reason: ${state.pending.reason}`, "");
    }
    if (state.blocker)
        lines.push("## Blocker", "", `- Reason: ${state.blocker.reason}`, `- Detail: ${state.blocker.detail}`, "");
    return lines.join("\n").trimEnd() + "\n";
}
function normalizeStatus(value, fallback) {
    const normalized = value?.trim().toLowerCase().replace(/^pass(?:ed)?$/, "pass");
    return new Set(["proposed", "planning", "review", "pass"]).has(normalized ?? "") ? normalized : fallback;
}
function normalizeHumanStatus(value) {
    const normalized = value?.trim().toLowerCase().replace(/^pass(?:ed)?$/, "pass");
    return new Set(["pending", "planning", "review", "pass"]).has(normalized ?? "") ? normalized : "pending";
}
function legacyValue(block, names) {
    for (const name of names) {
        const match = block.match(new RegExp(`^\\s*(?:[-*]\\s*)?${name}\\s*:\\s*(.+?)\\s*$`, "im"));
        if (match)
            return match[1].replace(/^`|`$/g, "").trim();
    }
    return undefined;
}
function canonicalLegacyPath(value, fallback) {
    if (!value)
        return fallback;
    const normalized = value.replace(/\\\\/g, "/").replace(/^\.\//, "");
    if (normalized.startsWith("../") || normalized.startsWith("/") || /^[A-Za-z]:\//.test(normalized))
        return fallback;
    return normalized;
}
export function parseLegacySnapshot(content, requestId) {
    if (!content.trim())
        throw new ProtocolError("legacy-plan.md", "must not be empty");
    const heading = /^(?:#{2,4})\s+(?:Stage\s+)?(S\d{2})\s*(?::|[-—])?\s*(.*?)\s*$/gim;
    const matches = [...content.matchAll(heading)];
    const stages = [];
    for (const [index, match] of matches.entries()) {
        const start = match.index ?? 0;
        const end = index + 1 < matches.length ? matches[index + 1].index ?? content.length : content.length;
        const block = content.slice(start, end);
        const id = match[1];
        const title = match[2]?.trim() || `Legacy ${id}`;
        const ordinal = Number(id.slice(1));
        const rawSlug = legacyValue(block, ["Slug"]);
        const slug = rawSlug && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(rawSlug) ? rawSlug : title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || `legacy-${id.toLowerCase()}`;
        const revision = Math.max(0, Number.parseInt(legacyValue(block, ["Technical revision", "Revision"]) ?? "0", 10) || 0);
        const humanRevision = Math.max(0, Number.parseInt(legacyValue(block, ["Human revision"]) ?? "0", 10) || 0);
        const status = normalizeStatus(legacyValue(block, ["Technical status", "Status"]), revision > 0 ? "review" : "proposed");
        const humanStatus = normalizeHumanStatus(legacyValue(block, ["Human status"]));
        const prefix = String(ordinal).padStart(2, "0");
        const fingerprint = legacyValue(block, ["Semantic fingerprint", "Fingerprint"]);
        stages.push({
            id,
            title,
            slug,
            status,
            revision: status === "pass" ? Math.max(1, revision) : revision,
            human_status: humanStatus,
            human_revision: humanStatus === "pass" ? Math.max(1, humanRevision) : humanRevision,
            details: canonicalLegacyPath(legacyValue(block, ["Technical artifact", "Details"]), `stages/${prefix}-${slug}.md`),
            review: canonicalLegacyPath(legacyValue(block, ["Technical review", "Review"]), `reviews/${prefix}.md`),
            human_review: canonicalLegacyPath(legacyValue(block, ["Human artifact"]), `stages/${prefix}-${slug}.human-review.md`),
            human_review_review: canonicalLegacyPath(legacyValue(block, ["Human review"]), `reviews/${prefix}-human-review.md`),
            semantic_fingerprint: fingerprint && /^[0-9a-f]{64}$/i.test(fingerprint) ? fingerprint.toLowerCase() : null,
        });
    }
    return {
        schema_version: 1,
        request_id: requestId,
        source_sha256: createHash("sha256").update(content).digest("hex"),
        stages,
    };
}
export function parseLegacyPlan(content, requestId) {
    parseLegacySnapshot(content, requestId);
    const state = newState(requestId);
    state.legacy_migrated = true;
    state.status = "discovery";
    state.analysis_status = "missing";
    state.stages = [];
    state.current_stage = null;
    return state;
}
export function legacyFingerprintMatches(snapshot, analysis, stageId, fingerprint) {
    const legacy = snapshot.stages.find((stage) => stage.id === stageId);
    return Boolean(legacy?.status === "pass" && legacy.semantic_fingerprint && legacy.semantic_fingerprint === fingerprint(analysis, stageId));
}
