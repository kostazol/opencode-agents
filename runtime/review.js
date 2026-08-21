import { REPEAT_LIMIT } from "./schema.js";
import { sha } from "./state.js";
function semanticEvidence(payload) {
    return {
        findings: payload.findings ?? [],
        required_changes: payload.required_changes ?? [],
        reason: payload.reason ?? "unspecified",
        stage: payload.stage ?? null,
    };
}
export function correctionDigests(payload) {
    return { fingerprint: sha(semanticEvidence(payload)), evidence_digest: sha(payload.evidence ?? payload) };
}
export function recordCorrection(state, key, revision, payload) {
    const current = correctionDigests(payload);
    const previous = state.convergence[key];
    const repeats = previous && previous.fingerprint === current.fingerprint && previous.evidence_digest === current.evidence_digest ? previous.repeats + 1 : 1;
    state.convergence[key] = { ...current, repeats, last_revision: revision };
    return repeats >= REPEAT_LIMIT;
}
export function clearCorrection(state, key) {
    delete state.convergence[key];
}
export function dependentStages(state, seeds) {
    const affected = new Set(seeds);
    let changed = true;
    while (changed) {
        changed = false;
        for (const stage of state.stages) {
            if (!affected.has(stage.id) && stage.depends_on.some((dependency) => affected.has(dependency))) {
                affected.add(stage.id);
                changed = true;
            }
        }
    }
    return state.stages.filter((stage) => affected.has(stage.id)).map((stage) => stage.id);
}
