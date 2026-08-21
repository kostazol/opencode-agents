import type { Analysis, State } from "./schema.js";
export interface LegacyStageSnapshot {
    id: string;
    title: string;
    slug: string;
    status: "proposed" | "planning" | "review" | "pass";
    revision: number;
    human_status: "pending" | "planning" | "review" | "pass";
    human_revision: number;
    details: string;
    review: string;
    human_review: string;
    human_review_review: string;
    semantic_fingerprint: string | null;
}
export interface LegacySnapshot {
    schema_version: 1;
    request_id: string;
    source_sha256: string;
    stages: LegacyStageSnapshot[];
}
export declare function renderPlan(state: State, analysis?: Analysis): string;
export declare function parseLegacySnapshot(content: string, requestId: string): LegacySnapshot;
export declare function parseLegacyPlan(content: string, requestId: string): State;
export declare function legacyFingerprintMatches(snapshot: LegacySnapshot, analysis: Analysis, stageId: string, fingerprint: (analysis: Analysis, stageId: string) => string): boolean;
