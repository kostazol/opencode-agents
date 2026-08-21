import { Analysis, AnalysisStage } from "./schema.js";
export declare function requiredNfrCategories(surfaces: string[]): Set<string>;
export declare function hasDependency(stages: Map<string, AnalysisStage>, consumer: string, producer: string): boolean;
export declare function validateAnalysis(input: unknown): Analysis;
export declare function canonicalRelative(value: unknown, field: string, prefix?: string): string;
export declare function affectedStageClosure(analysisInput: unknown, seedsInput: string[]): string[];
