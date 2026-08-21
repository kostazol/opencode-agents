import { createHash } from "node:crypto";
import { ANALYSIS_SCHEMA_VERSION, CHANGE_SURFACES, NFR_CATEGORIES, ProtocolError, SURFACE_NFR, array, boolean, clone, exactFields, identifier, record, stageId, strings, text } from "./schema.js";
function sequential(items, prefix, field) {
    items.forEach((item, index) => {
        const expected = `${prefix}-${String(index + 1).padStart(3, "0")}`;
        if (item.id !== expected)
            throw new ProtocolError(`${field}[${index}].id`, "identifiers must be contiguous and ordered", { expected, actual: item.id });
    });
}
function sameMembers(actual, expected, field) {
    const left = [...actual].sort();
    const right = [...expected].sort();
    if (JSON.stringify(left) !== JSON.stringify(right))
        throw new ProtocolError(field, "traceability list mismatch", { expected: right, actual: left });
}
function dependencyClosure(stages) {
    const result = new Map();
    for (const stage of stages) {
        const closure = new Set();
        for (const dependency of stage.depends_on) {
            closure.add(dependency);
            for (const transitive of result.get(dependency) ?? [])
                closure.add(transitive);
        }
        result.set(stage.id, closure);
    }
    return result;
}
export function validateAnalysis(input) {
    const source = clone(record(input, "analysis"));
    exactFields(source, [
        "schema_version", "request", "change_surfaces", "requirements", "nfrs", "decisions", "contracts",
        "acceptance", "scenarios", "nfr_applicability", "stages", "assumptions", "non_goals",
    ], "analysis");
    if (source.schema_version !== ANALYSIS_SCHEMA_VERSION)
        throw new ProtocolError("analysis.schema_version", `must be ${ANALYSIS_SCHEMA_VERSION}`, source.schema_version);
    const request = record(source.request, "analysis.request");
    exactFields(request, ["summary", "outcomes"], "analysis.request");
    const requestValue = { summary: text(request.summary, "analysis.request.summary"), outcomes: strings(request.outcomes, "analysis.request.outcomes", false) };
    const changeSurfaces = strings(source.change_surfaces, "analysis.change_surfaces", false);
    for (const surface of changeSurfaces)
        if (!CHANGE_SURFACES.has(surface))
            throw new ProtocolError("analysis.change_surfaces", "unsupported change surface", surface);
    const requirements = array(source.requirements, "analysis.requirements").map((raw, index) => {
        const field = `analysis.requirements[${index}]`;
        const item = record(raw, field);
        exactFields(item, ["id", "text", "stage", "acceptance", "scenarios"], field);
        return { id: identifier(item.id, "REQ", `${field}.id`), text: text(item.text, `${field}.text`), stage: stageId(item.stage, `${field}.stage`), acceptance: strings(item.acceptance, `${field}.acceptance`, false), scenarios: strings(item.scenarios, `${field}.scenarios`, false) };
    });
    sequential(requirements, "REQ", "analysis.requirements");
    const nfrs = array(source.nfrs, "analysis.nfrs").map((raw, index) => {
        const field = `analysis.nfrs[${index}]`;
        const item = record(raw, field);
        exactFields(item, ["id", "text", "category", "stage", "acceptance", "scenarios"], field);
        const category = text(item.category, `${field}.category`);
        if (!NFR_CATEGORIES.has(category))
            throw new ProtocolError(`${field}.category`, "unsupported NFR category", category);
        return { id: identifier(item.id, "NFR", `${field}.id`), text: text(item.text, `${field}.text`), category, stage: stageId(item.stage, `${field}.stage`), acceptance: strings(item.acceptance, `${field}.acceptance`, false), scenarios: strings(item.scenarios, `${field}.scenarios`, false) };
    });
    sequential(nfrs, "NFR", "analysis.nfrs");
    const decisions = array(source.decisions, "analysis.decisions").map((raw, index) => {
        const field = `analysis.decisions[${index}]`;
        const item = record(raw, field);
        exactFields(item, ["id", "text"], field);
        return { id: identifier(item.id, "DEC", `${field}.id`), text: text(item.text, `${field}.text`) };
    });
    sequential(decisions, "DEC", "analysis.decisions");
    const contracts = array(source.contracts, "analysis.contracts").map((raw, index) => {
        const field = `analysis.contracts[${index}]`;
        const item = record(raw, field);
        exactFields(item, ["id", "text", "producer", "consumers", "external", "terminal"], field);
        return {
            id: identifier(item.id, "CTR", `${field}.id`),
            text: text(item.text, `${field}.text`),
            producer: item.producer === null ? null : stageId(item.producer, `${field}.producer`),
            consumers: strings(item.consumers, `${field}.consumers`).map((value) => stageId(value, `${field}.consumers`)),
            external: boolean(item.external, `${field}.external`),
            terminal: boolean(item.terminal, `${field}.terminal`),
        };
    });
    sequential(contracts, "CTR", "analysis.contracts");
    const acceptance = array(source.acceptance, "analysis.acceptance").map((raw, index) => {
        const field = `analysis.acceptance[${index}]`;
        const item = record(raw, field);
        exactFields(item, ["id", "text", "stage", "verification"], field);
        return { id: identifier(item.id, "AC", `${field}.id`), text: text(item.text, `${field}.text`), stage: stageId(item.stage, `${field}.stage`), verification: text(item.verification, `${field}.verification`) };
    });
    sequential(acceptance, "AC", "analysis.acceptance");
    const scenarios = array(source.scenarios, "analysis.scenarios").map((raw, index) => {
        const field = `analysis.scenarios[${index}]`;
        const item = record(raw, field);
        exactFields(item, ["id", "text", "stage", "requirements", "expected"], field);
        return { id: identifier(item.id, "SCN", `${field}.id`), text: text(item.text, `${field}.text`), stage: stageId(item.stage, `${field}.stage`), requirements: strings(item.requirements, `${field}.requirements`, false), expected: text(item.expected, `${field}.expected`) };
    });
    sequential(scenarios, "SCN", "analysis.scenarios");
    const applicability = array(source.nfr_applicability, "analysis.nfr_applicability").map((raw, index) => {
        const field = `analysis.nfr_applicability[${index}]`;
        const item = record(raw, field);
        exactFields(item, ["category", "status", "evidence", "owner", "acceptance"], field);
        const category = text(item.category, `${field}.category`);
        if (!NFR_CATEGORIES.has(category))
            throw new ProtocolError(`${field}.category`, "unsupported NFR category", category);
        const status = text(item.status, `${field}.status`);
        if (!new Set(["required", "not_applicable", "deferred"]).has(status))
            throw new ProtocolError(`${field}.status`, "unsupported applicability status", status);
        return { category, status: status, evidence: text(item.evidence, `${field}.evidence`), owner: item.owner === null ? null : stageId(item.owner, `${field}.owner`), acceptance: strings(item.acceptance, `${field}.acceptance`) };
    });
    const stages = array(source.stages, "analysis.stages").map((raw, index) => {
        const field = `analysis.stages[${index}]`;
        const item = record(raw, field);
        exactFields(item, ["id", "title", "slug", "depends_on", "requirements", "nfrs", "contracts_consumed", "contracts_produced", "affected_area", "risks"], field);
        const id = stageId(item.id, `${field}.id`);
        const expected = `S${String(index + 1).padStart(2, "0")}`;
        if (id !== expected)
            throw new ProtocolError(`${field}.id`, "stages must be contiguous and ordered", { expected, actual: id });
        const slug = text(item.slug, `${field}.slug`);
        if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug))
            throw new ProtocolError(`${field}.slug`, "must be lower kebab-case", slug);
        const dependsOn = strings(item.depends_on, `${field}.depends_on`);
        for (const dependency of dependsOn) {
            const ordinal = Number(dependency.slice(1));
            if (!/^S\d{2}$/.test(dependency) || ordinal >= index + 1)
                throw new ProtocolError(`${field}.depends_on`, "must reference an earlier stage", dependency);
        }
        return {
            id,
            title: text(item.title, `${field}.title`),
            slug,
            depends_on: dependsOn,
            requirements: strings(item.requirements, `${field}.requirements`),
            nfrs: strings(item.nfrs, `${field}.nfrs`),
            contracts_consumed: strings(item.contracts_consumed, `${field}.contracts_consumed`),
            contracts_produced: strings(item.contracts_produced, `${field}.contracts_produced`),
            affected_area: text(item.affected_area, `${field}.affected_area`),
            risks: strings(item.risks, `${field}.risks`, false),
        };
    });
    const assumptions = strings(source.assumptions, "analysis.assumptions");
    const nonGoals = strings(source.non_goals, "analysis.non_goals");
    const analysis = {
        schema_version: ANALYSIS_SCHEMA_VERSION,
        request: requestValue,
        change_surfaces: changeSurfaces,
        requirements,
        nfrs,
        decisions,
        contracts,
        acceptance,
        scenarios,
        nfr_applicability: applicability,
        stages,
        assumptions,
        non_goals: nonGoals,
    };
    const stageById = new Map(stages.map((stage) => [stage.id, stage]));
    const requirementById = new Map(requirements.map((item) => [item.id, item]));
    const nfrById = new Map(nfrs.map((item) => [item.id, item]));
    const acceptanceById = new Map(acceptance.map((item) => [item.id, item]));
    const scenarioById = new Map(scenarios.map((item) => [item.id, item]));
    const contractById = new Map(contracts.map((item) => [item.id, item]));
    for (const item of requirements) {
        if (!stageById.has(item.stage))
            throw new ProtocolError(`analysis.requirements.${item.id}.stage`, "unknown stage", item.stage);
        for (const id of item.acceptance) {
            const linked = acceptanceById.get(id);
            if (!linked || linked.stage !== item.stage)
                throw new ProtocolError(`analysis.requirements.${item.id}.acceptance`, "acceptance must exist in the same stage", id);
        }
        for (const id of item.scenarios) {
            const linked = scenarioById.get(id);
            if (!linked || linked.stage !== item.stage || !linked.requirements.includes(item.id))
                throw new ProtocolError(`analysis.requirements.${item.id}.scenarios`, "scenario must trace back to the requirement in the same stage", id);
        }
    }
    for (const item of nfrs) {
        if (!stageById.has(item.stage))
            throw new ProtocolError(`analysis.nfrs.${item.id}.stage`, "unknown stage", item.stage);
        for (const id of item.acceptance) {
            const linked = acceptanceById.get(id);
            if (!linked || linked.stage !== item.stage)
                throw new ProtocolError(`analysis.nfrs.${item.id}.acceptance`, "acceptance must exist in the same stage", id);
        }
        for (const id of item.scenarios)
            if (!scenarioById.has(id) || scenarioById.get(id).stage !== item.stage)
                throw new ProtocolError(`analysis.nfrs.${item.id}.scenarios`, "scenario must exist in the same stage", id);
    }
    for (const item of acceptance)
        if (!stageById.has(item.stage))
            throw new ProtocolError(`analysis.acceptance.${item.id}.stage`, "unknown stage", item.stage);
    for (const item of scenarios) {
        if (!stageById.has(item.stage))
            throw new ProtocolError(`analysis.scenarios.${item.id}.stage`, "unknown stage", item.stage);
        for (const requirement of item.requirements)
            if (!requirementById.has(requirement) || requirementById.get(requirement).stage !== item.stage)
                throw new ProtocolError(`analysis.scenarios.${item.id}.requirements`, "unknown or cross-stage requirement", requirement);
    }
    for (const stage of stages) {
        sameMembers(stage.requirements, requirements.filter((item) => item.stage === stage.id).map((item) => item.id), `analysis.stages.${stage.id}.requirements`);
        sameMembers(stage.nfrs, nfrs.filter((item) => item.stage === stage.id).map((item) => item.id), `analysis.stages.${stage.id}.nfrs`);
        for (const id of stage.requirements)
            if (!requirementById.has(id))
                throw new ProtocolError(`analysis.stages.${stage.id}.requirements`, "unknown requirement", id);
        for (const id of stage.nfrs)
            if (!nfrById.has(id))
                throw new ProtocolError(`analysis.stages.${stage.id}.nfrs`, "unknown NFR", id);
    }
    const closure = dependencyClosure(stages);
    for (const contract of contracts) {
        if (contract.producer !== null && !stageById.has(contract.producer))
            throw new ProtocolError(`analysis.contracts.${contract.id}.producer`, "unknown stage", contract.producer);
        for (const consumer of contract.consumers)
            if (!stageById.has(consumer))
                throw new ProtocolError(`analysis.contracts.${contract.id}.consumers`, "unknown stage", consumer);
        if (!contract.external && contract.producer === null)
            throw new ProtocolError(`analysis.contracts.${contract.id}.producer`, "internal contract requires a producer");
        if (contract.terminal && contract.consumers.length)
            throw new ProtocolError(`analysis.contracts.${contract.id}.consumers`, "terminal contract cannot have consumers");
        if (!contract.terminal && !contract.consumers.length)
            throw new ProtocolError(`analysis.contracts.${contract.id}.consumers`, "non-terminal contract requires consumers");
        if (contract.producer && !stageById.get(contract.producer).contracts_produced.includes(contract.id))
            throw new ProtocolError(`analysis.contracts.${contract.id}`, "producer stage must list the contract");
        for (const consumer of contract.consumers) {
            if (!stageById.get(consumer).contracts_consumed.includes(contract.id))
                throw new ProtocolError(`analysis.contracts.${contract.id}`, "consumer stage must list the contract", consumer);
            if (contract.producer && contract.producer !== consumer && !(closure.get(consumer)?.has(contract.producer)))
                throw new ProtocolError(`analysis.contracts.${contract.id}`, "consumer must depend on producer", { producer: contract.producer, consumer });
        }
    }
    for (const stage of stages) {
        for (const id of stage.contracts_produced) {
            const contract = contractById.get(id);
            if (!contract || contract.producer !== stage.id)
                throw new ProtocolError(`analysis.stages.${stage.id}.contracts_produced`, "contract producer mismatch", id);
        }
        for (const id of stage.contracts_consumed) {
            const contract = contractById.get(id);
            if (!contract || !contract.consumers.includes(stage.id))
                throw new ProtocolError(`analysis.stages.${stage.id}.contracts_consumed`, "contract consumer mismatch", id);
        }
    }
    const requiredSurfaceCategories = new Set(changeSurfaces.flatMap((surface) => SURFACE_NFR[surface] ?? []));
    const seenApplicability = new Map();
    for (const [index, item] of applicability.entries()) {
        const previous = seenApplicability.get(item.category);
        if (previous !== undefined)
            throw new ProtocolError(`analysis.nfr_applicability[${index}].category`, previous === item.status ? "duplicate applicability category" : "contradictory applicability category", { category: item.category, first_status: previous, duplicate_status: item.status });
        seenApplicability.set(item.category, item.status);
        if (item.status === "not_applicable" && (item.owner !== null || item.acceptance.length))
            throw new ProtocolError(`analysis.nfr_applicability[${index}]`, "not_applicable category must not claim an owner or acceptance");
        if (item.status === "required") {
            if (!item.owner || !stageById.has(item.owner))
                throw new ProtocolError(`analysis.nfr_applicability[${index}].owner`, "required category must have a real owner stage");
            const matching = nfrs.filter((nfr) => nfr.category === item.category && nfr.stage === item.owner);
            if (!matching.length)
                throw new ProtocolError(`analysis.nfr_applicability[${index}]`, "required category must have a real NFR with the same category and owner stage");
            const linkedAcceptance = new Set(matching.flatMap((nfr) => nfr.acceptance));
            if (!item.acceptance.length)
                throw new ProtocolError(`analysis.nfr_applicability[${index}].acceptance`, "required category must have linked acceptance");
            for (const acceptanceId of item.acceptance) {
                const linked = acceptanceById.get(acceptanceId);
                if (!linkedAcceptance.has(acceptanceId))
                    throw new ProtocolError(`analysis.nfr_applicability[${index}].acceptance`, "acceptance must be linked by an NFR of this category and owner", acceptanceId);
                if (!linked || linked.stage !== item.owner)
                    throw new ProtocolError(`analysis.nfr_applicability[${index}].acceptance`, "acceptance must belong to owner stage", acceptanceId);
            }
        }
    }
    for (const category of requiredSurfaceCategories)
        if (!seenApplicability.has(category))
            throw new ProtocolError("analysis.nfr_applicability", "change surface requires an explicit applicability decision", category);
    return analysis;
}
function canonicalFingerprintJson(value) {
    if (value === null || typeof value !== "object")
        return JSON.stringify(value);
    if (Array.isArray(value))
        return `[${value.map(canonicalFingerprintJson).join(",")}]`;
    return `{${Object.entries(value).sort(([left], [right]) => left.localeCompare(right)).map(([key, item]) => `${JSON.stringify(key)}:${canonicalFingerprintJson(item)}`).join(",")}}`;
}
export function semanticStageFingerprint(analysisInput, stageIdValue) {
    const analysis = validateAnalysis(analysisInput);
    const stage = analysis.stages.find((item) => item.id === stageIdValue);
    if (!stage)
        throw new ProtocolError("stage", "unknown stage for semantic fingerprint", stageIdValue);
    const requirements = analysis.requirements.filter((item) => item.stage === stage.id);
    const nfrs = analysis.nfrs.filter((item) => item.stage === stage.id);
    const contracts = analysis.contracts.filter((item) => item.producer === stage.id || item.consumers.includes(stage.id) || stage.contracts_consumed.includes(item.id) || stage.contracts_produced.includes(item.id));
    const acceptanceIds = new Set([...requirements.flatMap((item) => item.acceptance), ...nfrs.flatMap((item) => item.acceptance)]);
    const scenarioIds = new Set([...requirements.flatMap((item) => item.scenarios), ...nfrs.flatMap((item) => item.scenarios)]);
    const semantic = {
        stage: { id: stage.id, title: stage.title, slug: stage.slug, depends_on: stage.depends_on, affected_area: stage.affected_area, risks: stage.risks },
        requirements,
        nfrs,
        contracts,
        acceptance: analysis.acceptance.filter((item) => item.stage === stage.id || acceptanceIds.has(item.id)),
        scenarios: analysis.scenarios.filter((item) => item.stage === stage.id || scenarioIds.has(item.id)),
        applicability: analysis.nfr_applicability.filter((item) => item.owner === stage.id || nfrs.some((nfr) => nfr.category === item.category)),
        decisions: analysis.decisions,
    };
    return createHash("sha256").update(canonicalFingerprintJson(semantic)).digest("hex");
}
