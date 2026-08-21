import type { JsonRecord, State } from "./schema.js";
export declare function reserveNext(input: unknown, analysisInput?: unknown, expectedStateRevision?: number): {
    state: State;
    action: JsonRecord;
};
