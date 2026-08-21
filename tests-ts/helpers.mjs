import assert from "node:assert/strict"
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import os from "node:os"
import path from "node:path"

import {
  ProtocolError,
  WorkflowStore,
  affectedStageClosure,
  applyEvent,
  newState,
  parseJsonStrict,
  reserveNext,
  validateAnalysis,
} from "../runtime/orchestrator.js"


export function analysisFixture() {
  return {
    schema_version: 1,
    request: { summary: "Добавить обработку событий", outcomes: ["События принимаются и обрабатываются"] },
    change_surfaces: ["library"],
    requirements: [
      { id: "REQ-001", text: "Принять событие", stage: "S01", acceptance: ["AC-001"], scenarios: ["SCN-001"] },
      { id: "REQ-002", text: "Обработать событие", stage: "S02", acceptance: ["AC-002"], scenarios: ["SCN-002"] },
    ],
    nfrs: [
      { id: "NFR-001", text: "Сохранить совместимость", category: "compatibility-migration", stage: "S02", acceptance: ["AC-003"], scenarios: ["SCN-003"] },
    ],
    decisions: [{ id: "DEC-001", text: "Использовать идемпотентность" }],
    contracts: [
      { id: "CON-001", text: "Вход", producer: null, consumers: ["S01"], external: true, terminal: false },
      { id: "CON-002", text: "Нормализованное событие", producer: "S01", consumers: ["S02"], external: false, terminal: false },
      { id: "CON-003", text: "Результат", producer: "S02", consumers: [], external: false, terminal: true },
    ],
    acceptance: [
      { id: "AC-001", text: "Приём работает", stage: "S01", verification: "unit" },
      { id: "AC-002", text: "Обработка работает", stage: "S02", verification: "integration" },
      { id: "AC-003", text: "Старый вызов работает", stage: "S02", verification: "compatibility" },
    ],
    scenarios: [
      { id: "SCN-001", text: "Приём", stage: "S01", requirements: ["REQ-001"], expected: "Сохранено" },
      { id: "SCN-002", text: "Обработка", stage: "S02", requirements: ["REQ-002"], expected: "Обработано" },
      { id: "SCN-003", text: "Совместимость", stage: "S02", requirements: ["NFR-001"], expected: "Без регрессии" },
    ],
    nfr_applicability: [
      { category: "compatibility-migration", status: "required", evidence: "Library surface", owner: "S02", acceptance: ["AC-003"] },
    ],
    stages: [
      { id: "S01", title: "Приём", slug: "accept-event", depends_on: [], requirements: ["REQ-001"], nfrs: [], contracts_consumed: ["CON-001"], contracts_produced: ["CON-002"], affected_area: "API", risks: ["validation"] },
      { id: "S02", title: "Обработка", slug: "process-event", depends_on: ["S01"], requirements: ["REQ-002"], nfrs: ["NFR-001"], contracts_consumed: ["CON-002"], contracts_produced: ["CON-003"], affected_area: "Worker", risks: ["duplicates"] },
    ],
    assumptions: [],
    non_goals: [],
  }
}

export function event(action, type, payload) {
  return { transition_id: action.transition_id, type, payload }
}

export async function advanceToPlanning(base) {
  const analysis = analysisFixture()
  let state = newState("sample")
  let reserved = reserveNext(state)
  state = (await applyEvent(base, reserved.state, event(reserved.action, "discovery_result", { revision: 1, status: "READY_FOR_REVIEW" }), analysis)).state
  reserved = reserveNext(state, analysis)
  state = (await applyEvent(base, reserved.state, event(reserved.action, "discovery_review_result", { revision: 1, status: "PASS" }), analysis)).state
  reserved = reserveNext(state, analysis)
  state = (await applyEvent(base, reserved.state, event(reserved.action, "map_decision", { decision: "APPROVE" }), analysis)).state
  return { state, analysis }
}

