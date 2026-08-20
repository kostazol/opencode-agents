import path from "node:path";
import { ANALYSIS_SCHEMA_VERSION, CHANGE_SURFACES, NFR_CATEGORIES, SURFACE_NFR, ProtocolError, array, boolean, clone, exactFields, identifier, record, stageId, strings, text } from "./schema.js";
function mapById(items, field) {
    const result = new Map();
    for (const item of items) {
        if (result.has(item.id))
            throw new ProtocolError(field, "duplicate identifier", item.id);
        result.set(item.id, item);
    }
    return result;
}
function ensureContiguous(items, family, field) {
    items.forEach((item, index) => {
        const expected = `${family}-${String(index + 1).padStart(3, "0")}`;
        if (item.id !== expected)
            throw new ProtocolError(`${field}[${index}].id`, `${family} identifiers must be contiguous and ordered`, item.id);
    });
}
export function requiredNfrCategories(surfaces) {
    const result = new Set();
    for (const surface of surfaces)
        for (const category of SURFACE_NFR[surface] ?? [])
            result.add(category);
    return result;
}
export function hasDependency(stages, consumer, producer) {
    const seen = new Set();
    const queue = [...(stages.get(consumer)?.depends_on ?? [])];
    while (queue.length) {
        const current = queue.shift();
        if (current === producer)
            return true;
        if (seen.has(current))
            continue;
        seen.add(current);
        queue.push(...(stages.get(current)?.depends_on ?? []));
    }
    return false;
}
export function validateAnalysis(input) {
    const root = clone(record(input, "analysis"));
    exactFields(root, [
        "schema_version", "request", "change_surfaces", "requirements", "nfrs", "decisions", "contracts",
        "acceptance", "scenarios", "nfr_applicability", "stages", "assumptions", "non_goals",
    ], "analysis");
    if (root.schema_version !== ANALYSIS_SCHEMA_VERSION)
        throw new ProtocolError("schema_version", `must be ${ANALYSIS_SCHEMA_VERSION}`, root.schema_version);
    const request = record(root.request, "request");
    exactFields(request, ["summary", "outcomes"], "request");
    const normalizedRequest = { summary: text(request.summary, "request.summary"), outcomes: strings(request.outcomes, "request.outcomes", false) };
    const surfaces = strings(root.change_surfaces, "change_surfaces");
    for (const surface of surfaces)
        if (!CHANGE_SURFACES.has(surface))
            throw new ProtocolError("change_surfaces", "unsupported value", surface);
    const acceptance = array(root.acceptance, "acceptance").map((raw, index) => {
        const item = record(raw, `acceptance[${index}]`);
        exactFields(item, ["id", "text", "stage", "verification"], `acceptance[${index}]`);
        return { id: identifier(item.id, "AC", `acceptance[${index}].id`), text: text(item.text, `acceptance[${index}].text`), stage: stageId(item.stage, `acceptance[${index}].stage`), verification: text(item.verification, `acceptance[${index}].verification`) };
    });
    const scenarios = array(root.scenarios, "scenarios").map((raw, index) => {
        const item = record(raw, `scenarios[${index}]`);
        exactFields(item, ["id", "text", "stage", "requirements", "expected"], `scenarios[${index}]`);
        return { id: identifier(item.id, "SCN", `scenarios[${index}].id`), text: text(item.text, `scenarios[${index}].text`), stage: stageId(item.stage, `scenarios[${index}].stage`), requirements: strings(item.requirements, `scenarios[${index}].requirements`, false), expected: text(item.expected, `scenarios[${index}].expected`) };
    });
    const contracts = array(root.contracts, "contracts").map((raw, index) => {
        const item = record(raw, `contracts[${index}]`);
        exactFields(item, ["id", "text", "producer", "consumers", "external", "terminal"], `contracts[${index}]`);
        return {
            id: identifier(item.id, "CON", `contracts[${index}].id`),
            text: text(item.text, `contracts[${index}].text`),
            producer: item.producer === null ? null : stageId(item.producer, `contracts[${index}].producer`),
            consumers: strings(item.consumers, `contracts[${index}].consumers`),
            external: boolean(item.external, `contracts[${index}].external`),
            terminal: boolean(item.terminal, `contracts[${index}].terminal`),
        };
    });
    const stages = array(root.stages, "stages").map((raw, index) => {
        const item = record(raw, `stages[${index}]`);
        exactFields(item, ["id", "title", "slug", "depends_on", "requirements", "nfrs", "contracts_consumed", "contracts_produced", "affected_area", "risks"], `stages[${index}]`);
        const id = stageId(item.id, `stages[${index}].id`);
        if (id !== `S${String(index + 1).padStart(2, "0")}`)
            throw new ProtocolError(`stages[${index}].id`, "stages must be contiguous and ordered", id);
        const slug = text(item.slug, `stages[${index}].slug`);
        if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug))
            throw new ProtocolError(`stages[${index}].slug`, "must be lower kebab-case", slug);
        const depends = strings(item.depends_on, `stages[${index}].depends_on`);
        const earlier = new Set(Array.from({ length: index }, (_, itemIndex) => `S${String(itemIndex + 1).padStart(2, "0")}`));
        for (const dependency of depends)
            if (!earlier.has(dependency))
                throw new ProtocolError(`stages[${index}].depends_on`, "must reference earlier stages", dependency);
        return {
            id,
            title: text(item.title, `stages[${index}].title`),
            slug,
            depends_on: depends,
            requirements: strings(item.requirements, `stages[${index}].requirements`),
            nfrs: strings(item.nfrs, `stages[${index}].nfrs`),
            contracts_consumed: strings(item.contracts_consumed, `stages[${index}].contracts_consumed`),
            contracts_produced: strings(item.contracts_produced, `stages[${index}].contracts_produced`),
            affected_area: text(item.affected_area, `stages[${index}].affected_area`),
            risks: strings(item.risks, `stages[${index}].risks`),
        };
    });
    if (!stages.length)
        throw new ProtocolError("stages", "must not be empty");
    const stageMap = mapById(stages, "stages");
    const requirements = array(root.requirements, "requirements").map((raw, index) => {
        const item = record(raw, `requirements[${index}]`);
        exactFields(item, ["id", "text", "stage", "acceptance", "scenarios"], `requirements[${index}]`);
        return { id: identifier(item.id, "REQ", `requirements[${index}].id`), text: text(item.text, `requirements[${index}].text`), stage: stageId(item.stage, `requirements[${index}].stage`), acceptance: strings(item.acceptance, `requirements[${index}].acceptance`, false), scenarios: strings(item.scenarios, `requirements[${index}].scenarios`, false) };
    });
    const nfrs = array(root.nfrs, "nfrs").map((raw, index) => {
        const item = record(raw, `nfrs[${index}]`);
        exactFields(item, ["id", "text", "category", "stage", "acceptance", "scenarios"], `nfrs[${index}]`);
        const category = text(item.category, `nfrs[${index}].category`);
        if (!NFR_CATEGORIES.has(category))
            throw new ProtocolError(`nfrs[${index}].category`, "unsupported category", category);
        return { id: identifier(item.id, "NFR", `nfrs[${index}].id`), text: text(item.text, `nfrs[${index}].text`), category, stage: stageId(item.stage, `nfrs[${index}].stage`), acceptance: strings(item.acceptance, `nfrs[${index}].acceptance`, false), scenarios: strings(item.scenarios, `nfrs[${index}].scenarios`, false) };
    });
    const decisions = array(root.decisions, "decisions").map((raw, index) => {
        const item = record(raw, `decisions[${index}]`);
        exactFields(item, ["id", "text"], `decisions[${index}]`);
        return { id: identifier(item.id, "DEC", `decisions[${index}].id`), text: text(item.text, `decisions[${index}].text`) };
    });
    const acMap = mapById(acceptance, "acceptance");
    const scenarioMap = mapById(scenarios, "scenarios");
    const requirementMap = mapById(requirements, "requirements");
    const nfrMap = mapById(nfrs, "nfrs");
    const contractMap = mapById(contracts, "contracts");
    mapById(decisions, "decisions");
    ensureContiguous(requirements, "REQ", "requirements");
    ensureContiguous(nfrs, "NFR", "nfrs");
    ensureContiguous(decisions, "DEC", "decisions");
    ensureContiguous(contracts, "CON", "contracts");
    ensureContiguous(acceptance, "AC", "acceptance");
    ensureContiguous(scenarios, "SCN", "scenarios");
    for (const item of [...requirements, ...nfrs]) {
        const owner = stageMap.get(item.stage);
        if (!owner)
            throw new ProtocolError(`${item.id}.stage`, "unknown stage", item.stage);
        const ownerList = item.id.startsWith("REQ-") ? owner.requirements : owner.nfrs;
        if (!ownerList.includes(item.id))
            throw new ProtocolError(item.id, "owning stage does not list item", item.stage);
        for (const ac of item.acceptance) {
            const target = acMap.get(ac);
            if (!target || target.stage !== item.stage)
                throw new ProtocolError(`${item.id}.acceptance`, "acceptance must exist in owning stage", ac);
        }
        for (const scenario of item.scenarios) {
            const target = scenarioMap.get(scenario);
            if (!target || target.stage !== item.stage || !target.requirements.includes(item.id))
                throw new ProtocolError(`${item.id}.scenarios`, "scenario link must be reciprocal in owning stage", scenario);
        }
    }
    const referencedAcceptance = new Set();
    for (const item of [...requirements, ...nfrs])
        for (const id of item.acceptance)
            referencedAcceptance.add(id);
    for (const criterion of acceptance) {
        if (!stageMap.has(criterion.stage))
            throw new ProtocolError(`${criterion.id}.stage`, "unknown stage", criterion.stage);
        if (!referencedAcceptance.has(criterion.id))
            throw new ProtocolError(criterion.id, "acceptance criterion is not linked from any requirement");
    }
    for (const scenario of scenarios) {
        if (!stageMap.has(scenario.stage))
            throw new ProtocolError(`${scenario.id}.stage`, "unknown stage", scenario.stage);
        for (const linked of scenario.requirements) {
            const requirement = requirementMap.get(linked) ?? nfrMap.get(linked);
            if (!requirement)
                throw new ProtocolError(`${scenario.id}.requirements`, "unknown requirement", linked);
            if (requirement.stage !== scenario.stage || !requirement.scenarios.includes(scenario.id)) {
                throw new ProtocolError(`${scenario.id}.requirements`, "scenario link must be reciprocal in owning stage", linked);
            }
        }
    }
    for (const contract of contracts) {
        if (contract.external && contract.producer !== null)
            throw new ProtocolError(contract.id, "external contract cannot have an internal producer");
        if (!contract.external && contract.producer === null)
            throw new ProtocolError(contract.id, "internal contract requires a producer");
        if (!contract.consumers.length && !contract.terminal)
            throw new ProtocolError(contract.id, "contract without consumers must be terminal");
        if (contract.producer) {
            const producer = stageMap.get(contract.producer);
            if (!producer?.contracts_produced.includes(contract.id))
                throw new ProtocolError(contract.id, "producer stage does not list contract");
        }
        for (const consumerId of contract.consumers) {
            const consumer = stageMap.get(consumerId);
            if (!consumer?.contracts_consumed.includes(contract.id))
                throw new ProtocolError(contract.id, "consumer stage does not list contract", consumerId);
            if (contract.producer && !hasDependency(stageMap, consumerId, contract.producer))
                throw new ProtocolError(contract.id, "consumer dependency graph omits producer", { producer: contract.producer, consumer: consumerId });
        }
    }
    for (const stage of stages) {
        for (const id of stage.requirements) {
            const item = requirementMap.get(id);
            if (!item)
                throw new ProtocolError(stage.id, "unknown requirement", id);
            if (item.stage !== stage.id)
                throw new ProtocolError(stage.id, "stage lists a requirement owned by another stage", id);
        }
        for (const id of stage.nfrs) {
            const item = nfrMap.get(id);
            if (!item)
                throw new ProtocolError(stage.id, "unknown NFR", id);
            if (item.stage !== stage.id)
                throw new ProtocolError(stage.id, "stage lists an NFR owned by another stage", id);
        }
        for (const id of [...stage.contracts_consumed, ...stage.contracts_produced])
            if (!contractMap.has(id))
                throw new ProtocolError(stage.id, "unknown contract", id);
    }
    const applicability = array(root.nfr_applicability, "nfr_applicability").map((raw, index) => {
        const item = record(raw, `nfr_applicability[${index}]`);
        exactFields(item, ["category", "status", "evidence", "owner", "acceptance"], `nfr_applicability[${index}]`);
        const category = text(item.category, `nfr_applicability[${index}].category`);
        if (!NFR_CATEGORIES.has(category))
            throw new ProtocolError(`nfr_applicability[${index}].category`, "unsupported category", category);
        const status = text(item.status, `nfr_applicability[${index}].status`);
        if (!new Set(["required", "not_applicable", "deferred"]).has(status))
            throw new ProtocolError(`nfr_applicability[${index}].status`, "unsupported status", status);
        const owner = item.owner === null ? null : stageId(item.owner, `nfr_applicability[${index}].owner`);
        const acceptanceIds = strings(item.acceptance, `nfr_applicability[${index}].acceptance`);
        if (status === "required" && (!owner || !acceptanceIds.length))
            throw new ProtocolError(`nfr_applicability[${index}]`, "required category needs owner and acceptance");
        if (status !== "required" && acceptanceIds.length)
            throw new ProtocolError(`nfr_applicability[${index}]`, "non-required category cannot claim acceptance");
        if (owner && !stageMap.has(owner))
            throw new ProtocolError(`nfr_applicability[${index}].owner`, "unknown stage", owner);
        for (const id of acceptanceIds) {
            const criterion = acMap.get(id);
            if (!criterion)
                throw new ProtocolError(`nfr_applicability[${index}].acceptance`, "unknown acceptance", id);
            if (owner && criterion.stage !== owner)
                throw new ProtocolError(`nfr_applicability[${index}].acceptance`, "acceptance must belong to owner stage", id);
        }
        return { category, status: status, evidence: text(item.evidence, `nfr_applicability[${index}].evidence`), owner, acceptance: acceptanceIds };
    });
    const categories = new Set(applicability.map((item) => item.category));
    for (const required of requiredNfrCategories(surfaces))
        if (!categories.has(required))
            throw new ProtocolError("nfr_applicability", "missing category implied by change surfaces", required);
    return {
        schema_version: ANALYSIS_SCHEMA_VERSION,
        request: normalizedRequest,
        change_surfaces: surfaces,
        requirements,
        nfrs,
        decisions,
        contracts,
        acceptance,
        scenarios,
        nfr_applicability: applicability,
        stages,
        assumptions: strings(root.assumptions, "assumptions"),
        non_goals: strings(root.non_goals, "non_goals"),
    };
}
export function canonicalRelative(value, field, prefix) {
    const result = text(value, field);
    if (result.includes("\\") || path.posix.isAbsolute(result) || result.split("/").some((part) => !part || part === "." || part === ".."))
        throw new ProtocolError(field, "must be a canonical relative POSIX path", result);
    if (prefix && !result.startsWith(prefix))
        throw new ProtocolError(field, `must start with ${prefix}`, result);
    return result;
}
export function affectedStageClosure(analysisInput, seedsInput) {
    const analysis = validateAnalysis(analysisInput);
    const stages = new Map(analysis.stages.map((item) => [item.id, item]));
    const seeds = new Set(seedsInput);
    for (const seed of seeds)
        if (!stages.has(seed))
            throw new ProtocolError("affected_stages", "unknown seed", seed);
    const contracts = new Map(analysis.contracts.map((item) => [item.id, item]));
    const affected = new Set(seeds);
    let changed = true;
    while (changed) {
        changed = false;
        const produced = new Set(Array.from(affected).flatMap((stage) => stages.get(stage).contracts_produced));
        const consumers = new Set(Array.from(produced).flatMap((contract) => contracts.get(contract)?.consumers ?? []));
        for (const stage of analysis.stages) {
            if (affected.has(stage.id))
                continue;
            if (stage.depends_on.some((dependency) => affected.has(dependency)) || consumers.has(stage.id)) {
                affected.add(stage.id);
                changed = true;
            }
        }
    }
    return analysis.stages.filter((item) => affected.has(item.id)).map((item) => item.id);
}
