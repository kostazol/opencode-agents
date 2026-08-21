import type { Analysis, EventInput, JsonRecord, State } from "./schema.js";
export declare function requestReopen(stateInput: State, seedsInput: string[], reason: string, requestedBy?: "reviewer" | "user"): State;
export declare function applyEvent(_directory: string, input: State, eventInput: EventInput, analysis?: Analysis, expectedStateRevision?: number): Promise<{
    state: State;
    result: JsonRecord;
}>;
