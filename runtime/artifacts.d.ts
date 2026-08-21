import type { Analysis, ArtifactSnapshot, EventInput, PendingAction, RevisionMetadata, State } from "./schema.js";
export interface ArtifactContract {
    artifact: string;
    stage: string | null;
    revision: number;
    source_revision: number;
    status: string;
}
export declare function parseArtifactMetadata(content: string, field?: string): RevisionMetadata;
export declare function captureSnapshot(root: string, relativeInput: string, contentOverride?: string): Promise<ArtifactSnapshot>;
export declare function capturePendingSnapshots(root: string, pending: PendingAction, overrides?: Record<string, string>): Promise<void>;
export declare function assertInputSnapshotsCurrent(root: string, pending: PendingAction): Promise<void>;
export declare function assertFreshPrimaryOutput(root: string, pending: PendingAction): Promise<void>;
export declare function assertArtifact(root: string, relativeInput: string, expected: ArtifactContract): Promise<RevisionMetadata>;
export declare function assertPendingOutputContracts(root: string, state: State, event: EventInput, analysis?: Analysis): Promise<void>;
export declare function assertCompleteArtifactGraph(root: string, state: State, analysis: Analysis | undefined): Promise<void>;
