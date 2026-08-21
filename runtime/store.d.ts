import type { EventInput, JsonRecord, State } from "./schema.js";
export declare class WorkflowStore {
    readonly base: string;
    readonly root: string;
    readonly internal: string;
    readonly statePath: string;
    readonly planPath: string;
    readonly analysisPath: string;
    readonly journalPath: string;
    readonly transactionPath: string;
    readonly lockPath: string;
    readonly stateV1BackupPath: string;
    readonly request: string;
    constructor(directory: string, request: string);
    private ensureRoot;
    private withLock;
    private recover;
    private loadState;
    private loadAnalysis;
    private journal;
    private commit;
    reserve(expectedStateRevision?: number): Promise<{
        state: State;
        action: JsonRecord;
    }>;
    apply(event: EventInput, expectedStateRevision?: number): Promise<{
        state: State;
        result: JsonRecord;
    }>;
    validate(): Promise<JsonRecord>;
}
