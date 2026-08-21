import { JsonRecord, State } from "./orchestrator.js";
export declare function reserveNext(input: unknown, analysisInput?: unknown, expectedStateRevision?: number): {
    state: State;
    action: JsonRecord;
};
