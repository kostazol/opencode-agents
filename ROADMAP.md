# Roadmap 6.0 — stable Python planning orchestrator

## Статус

**DONE.** Этот commit фиксирует завершённую Python-реализацию перед переходом production runtime на TypeScript.

## Реализовано

- versioned `analysis.json` protocol с `REQ/NFR/DEC/CON/AC/SCN`;
- reciprocal traceability и producer/consumer dependency validation;
- pure next/apply controller, monotonic revisions и one-pending-action invariant;
- expected revision checks и idempotent transition replay;
- atomic state/plan transaction, request lock, journal и crash recovery;
- bounded convergence по structured findings;
- controlled reopening минимального dependency/contract subgraph;
- strict legacy `plan.md` migration;
- `orchestrator_next`, `orchestrator_apply`, `orchestrator_validate`;
- controller-driven prompts и capability-first permissions.

## Архитектура

```text
OpenCode custom tool (TypeScript adapter)
  -> JSON stdin/stdout, argv without shell interpolation
Python 3.11+ controller
  -> state.json / journal.jsonl / generated plan.md
```

TypeScript adapter не вычисляет routing, revisions, convergence или reopening. Единственный production source of workflow mechanics находится в Python package.

## Release gates

- protocol, routing, convergence, reopening and store tests;
- installer install/update/status tests;
- adapter contract and safe process invocation;
- prompt contract checks;
- clean install containing agents, tools and Python runtime.

## Следующий changeset

Перенести единственный production controller в Node-compatible TypeScript без изменения durable protocol и semantic agent contracts. После parity удалить Python production package, сохранив Python только для installer и black-box E2E harness.
