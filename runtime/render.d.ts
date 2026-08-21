import { State } from "./orchestrator.js";
export declare function renderPlan(stateInput: unknown, analysisInput?: unknown): string;
export declare function parseLegacyPlan(content: string, requestId: string): State;
