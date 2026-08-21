import type { JsonRecord, State } from "./schema.js";
export declare function correctionDigests(payload: JsonRecord): {
    fingerprint: string;
    evidence_digest: string;
};
export declare function recordCorrection(state: State, key: string, revision: number, payload: JsonRecord): boolean;
export declare function clearCorrection(state: State, key: string): void;
export declare function dependentStages(state: State, seeds: string[]): string[];
