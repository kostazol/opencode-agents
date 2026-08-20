import { JsonRecord, State } from "./orchestrator.js";
export declare function applyEvent(base: string, input: unknown, eventInput: unknown, analysisInput?: unknown, expectedStateRevision?: number): Promise<{
    state: State;
    result: JsonRecord;
}>;
