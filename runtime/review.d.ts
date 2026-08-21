import { Analysis, JsonRecord, PendingAction, State } from "./orchestrator.js";
export declare function choice(payload: JsonRecord, field: string, values: string[]): string;
export declare function requireRevision(payload: JsonRecord, expected: number): void;
export declare function block(state: State, pending: PendingAction, reason: string, detail: string, retryable?: boolean): JsonRecord;
export declare function recordRevise(base: string, state: State, key: string, revision: number, payload: JsonRecord): Promise<{
    stalled: boolean;
    summary: string;
}>;
export declare function proposeReopen(state: State, analysis: Analysis, payload: JsonRecord, requestedBy: "reviewer" | "user"): JsonRecord;
export declare function applyReopen(state: State, analysis: Analysis, payload: JsonRecord): JsonRecord;
export declare function feedbackText(payload: JsonRecord): string;
