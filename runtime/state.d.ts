import type { Analysis, JsonRecord, PendingAction, StageState, State } from "./schema.js";
export interface StateMigrationResult {
    state: JsonRecord;
    migrated: boolean;
    from_version: number;
    to_version: number;
    invalidated_transition: string | null;
}
export declare function migrateState(input: unknown): StateMigrationResult;
export declare function newState(requestId: string): State;
export declare function stagesFromAnalysis(analysis: Analysis): StageState[];
export declare function stageMap(state: State): Map<string, StageState>;
export declare function validateState(input: unknown, analysisInput?: unknown): State;
export declare function stableJson(value: unknown): string;
export declare function sha(value: unknown): string;
export declare function transitionId(state: State, action: string, stage: string | null, revision: number | null): string;
export declare function pendingAction(state: State, action: string, actor: string, reason: string, options?: Partial<PendingAction>): PendingAction;
export declare function normalizeProgress(state: State): void;
export declare function completeAction(state: State): JsonRecord;
