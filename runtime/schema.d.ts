export declare const ANALYSIS_SCHEMA_VERSION = 1;
export declare const STATE_SCHEMA_VERSION = 1;
export declare const REPEAT_LIMIT = 2;
export declare const CHANGE_SURFACES: Set<string>;
export declare const NFR_CATEGORIES: Set<string>;
export declare const SURFACE_NFR: Record<string, string[]>;
export declare const WORKFLOW_STATUSES: Set<string>;
export declare const STAGE_STATUSES: Set<string>;
export declare const HUMAN_STATUSES: Set<string>;
export declare const AGENT_ACTIONS: Set<string>;
export declare const EVENT_BY_ACTION: Record<string, string>;
export type JsonRecord = Record<string, unknown>;
export type WorkflowStatus = "discovery" | "discovery_review" | "waiting_answers" | "waiting_map_approval" | "planning" | "human_reviewing" | "waiting_plan_approval" | "waiting_reopen_approval" | "ready" | "blocked";
export interface AnalysisStage {
    id: string;
    title: string;
    slug: string;
    depends_on: string[];
    requirements: string[];
    nfrs: string[];
    contracts_consumed: string[];
    contracts_produced: string[];
    affected_area: string;
    risks: string[];
}
export interface Analysis {
    schema_version: number;
    request: {
        summary: string;
        outcomes: string[];
    };
    change_surfaces: string[];
    requirements: Array<{
        id: string;
        text: string;
        stage: string;
        acceptance: string[];
        scenarios: string[];
    }>;
    nfrs: Array<{
        id: string;
        text: string;
        category: string;
        stage: string;
        acceptance: string[];
        scenarios: string[];
    }>;
    decisions: Array<{
        id: string;
        text: string;
    }>;
    contracts: Array<{
        id: string;
        text: string;
        producer: string | null;
        consumers: string[];
        external: boolean;
        terminal: boolean;
    }>;
    acceptance: Array<{
        id: string;
        text: string;
        stage: string;
        verification: string;
    }>;
    scenarios: Array<{
        id: string;
        text: string;
        stage: string;
        requirements: string[];
        expected: string;
    }>;
    nfr_applicability: Array<{
        category: string;
        status: "required" | "not_applicable" | "deferred";
        evidence: string;
        owner: string | null;
        acceptance: string[];
    }>;
    stages: AnalysisStage[];
    assumptions: string[];
    non_goals: string[];
}
export interface StageState {
    id: string;
    title: string;
    slug: string;
    depends_on: string[];
    status: "proposed" | "planning" | "review" | "pass";
    revision: number;
    human_status: "pending" | "planning" | "review" | "pass";
    human_revision: number;
    details: string;
    review: string;
    human_review: string;
    human_review_review: string;
}
export interface PendingAction {
    transition_id: string;
    action: string;
    actor: string;
    mode: string | null;
    stage: string | null;
    revision: number | null;
    source_revision: number | null;
    inputs: string[];
    output: string | null;
    reason: string;
    issued_state_revision: number;
}
export interface State {
    schema_version: number;
    request_id: string;
    state_revision: number;
    sequence: number;
    status: WorkflowStatus;
    current_stage: string | null;
    analysis_revision: number;
    analysis_status: "missing" | "draft" | "review" | "reviewed" | "approved";
    question_revision: number;
    feedback_revision: number;
    stages: StageState[];
    pending: PendingAction | null;
    applied: Record<string, {
        event_digest: string;
        result: JsonRecord;
    }>;
    blocker: null | {
        reason: string;
        detail: string;
        resume_status: WorkflowStatus;
        retryable: boolean;
        source_transition: string;
    };
    reopen: null | {
        requested_by: "reviewer" | "user";
        reason: string;
        seeds: string[];
        affected: string[];
        resume_status: WorkflowStatus;
        resume_stage: string | null;
    };
    convergence: Record<string, {
        fingerprint: string;
        evidence_digest: string;
        repeats: number;
        last_revision: number;
    }>;
    legacy_migrated: boolean;
}
export interface EventInput {
    transition_id: string;
    type: string;
    payload: JsonRecord;
}
export declare class ProtocolError extends Error {
    readonly field: string;
    readonly value: unknown;
    constructor(field: string, message: string, value?: unknown);
}
export declare function parseJsonStrict(source: string): unknown;
export declare function clone<T>(value: T): T;
export declare function record(value: unknown, field: string): JsonRecord;
export declare function text(value: unknown, field: string): string;
export declare function integer(value: unknown, field: string, minimum?: number): number;
export declare function boolean(value: unknown, field: string): boolean;
export declare function array(value: unknown, field: string): unknown[];
export declare function strings(value: unknown, field: string, allowEmpty?: boolean): string[];
export declare function exactFields(value: JsonRecord, expected: string[], field: string): void;
export declare function identifier(value: unknown, family: string, field: string): string;
export declare function stageId(value: unknown, field: string): string;
