
import { mkdir, writeFile } from "node:fs/promises"
import path from "node:path"

export function analysisFixture() {
  return {
    schema_version: 1,
    request: { summary: "Ship a deterministic two-stage controller change", outcomes: ["Executable stage graph", "Verified release"] },
    change_surfaces: ["library"],
    requirements: [
      { id: "REQ-001", text: "Implement the controller contract", stage: "S01", acceptance: ["AC-001"], scenarios: ["SCN-001"] },
      { id: "REQ-002", text: "Integrate and release the contract", stage: "S02", acceptance: ["AC-003"], scenarios: ["SCN-002"] },
    ],
    nfrs: [
      { id: "NFR-001", text: "Preserve compatibility through explicit versioned contracts", category: "compatibility-migration", stage: "S01", acceptance: ["AC-002"], scenarios: ["SCN-001"] },
    ],
    decisions: [{ id: "DEC-001", text: "Use one TypeScript controller and immutable artifacts" }],
    contracts: [
      { id: "CTR-001", text: "S01 produces the controller contract consumed by S02", producer: "S01", consumers: ["S02"], external: false, terminal: false },
      { id: "CTR-002", text: "S02 produces the terminal release package", producer: "S02", consumers: [], external: false, terminal: true },
    ],
    acceptance: [
      { id: "AC-001", text: "Controller contract tests pass", stage: "S01", verification: "node test" },
      { id: "AC-002", text: "Compatibility migration test passes", stage: "S01", verification: "migration test" },
      { id: "AC-003", text: "Release journey reaches COMPLETE", stage: "S02", verification: "journey test" },
    ],
    scenarios: [
      { id: "SCN-001", text: "Validate and migrate controller state", stage: "S01", requirements: ["REQ-001"], expected: "State is valid and resumable" },
      { id: "SCN-002", text: "Execute a complete store journey", stage: "S02", requirements: ["REQ-002"], expected: "All artifacts pass and COMPLETE is returned" },
    ],
    nfr_applicability: [
      { category: "compatibility-migration", status: "required", evidence: "The state and runtime are versioned", owner: "S01", acceptance: ["AC-002"] },
    ],
    stages: [
      { id: "S01", title: "Controller contracts", slug: "controller-contracts", depends_on: [], requirements: ["REQ-001"], nfrs: ["NFR-001"], contracts_consumed: [], contracts_produced: ["CTR-001"], affected_area: "src and runtime", risks: ["stale artifact acceptance"] },
      { id: "S02", title: "Release integration", slug: "release-integration", depends_on: ["S01"], requirements: ["REQ-002"], nfrs: [], contracts_consumed: ["CTR-001"], contracts_produced: ["CTR-002"], affected_area: "tests installer CI", risks: ["cross-platform drift"] },
    ],
    assumptions: ["OpenCode invokes native tools from one repository root"],
    non_goals: ["Generic workflow framework"],
  }
}

export function event(action, type, payload) {
  return { transition_id: action.transition_id, type, payload }
}

export async function writeArtifact(root, relative, metadata, body = "# Verified artifact\n") {
  const destination = path.join(root, ...relative.split("/"))
  await mkdir(path.dirname(destination), { recursive: true })
  await writeFile(destination, [
    "---",
    "schema_version: 1",
    `artifact: ${metadata.artifact}`,
    `stage: ${metadata.stage ?? "none"}`,
    `revision: ${metadata.revision}`,
    `source_revision: ${metadata.source_revision}`,
    `status: ${metadata.status}`,
    "---",
    body.trimEnd(),
    "",
  ].join("\n"), "utf8")
}
