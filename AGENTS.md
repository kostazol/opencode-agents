# Agent Maintenance Guide

## Product contract

Репозиторий поставляет четыре planning-only OpenCode agents и один нативный TypeScript controller:

- `orchestrator-analyst` — sole primary и клиент controller loop;
- `orchestrator-discovery` — repository evidence, traceability, material questions и stage map;
- `orchestrator-stage-planner` — один technical/human-review stage;
- `orchestrator-stage-reviewer` — independent discovery/stage/human-review gate;
- `src/*.ts` — единственный production source of workflow mechanics;
- `runtime/*.js` — compiled installable modules;
- `tools/orchestrator.ts` — thin native OpenCode adapter.

Python не является production controller. Он остаётся только у installer и black-box E2E harness.

## Architecture rules

1. Prompts не вычисляют routing, revisions, convergence или reopening closure.
2. `tools/orchestrator.ts` остаётся тонким adapter; не добавляйте вторую state machine.
3. `plan.md` генерируется controller и не является authoritative machine state.
4. Semantic agents пишут только controller-selected output и возвращают typed payload.
5. Каждый material REQ/NFR связан с owning stage, reciprocal scenario и acceptance.
6. Каждый internal contract имеет producer; каждый non-terminal contract имеет consumer и dependency path.
7. Convergence использует содержимое существующих evidence paths, а не hash от модели.
8. Reopening затрагивает минимальный transitive dependency/contract subgraph.
9. Не добавляйте artifact/status/tool, когда существующий typed contract выражает тот же инвариант.
10. Используйте Node-compatible standard APIs; Bun-only APIs в controller не допускаются.

## Durable artifacts

```text
1_orchestrator/<request>/
├── plan.md
├── discovery.md
├── analysis.json
├── questions.md
├── feedback.md
├── stages/*.md
├── reviews/*.md
└── .orchestrator/{state.json,journal.jsonl,transaction.json}
```

`PASS` сертифицирует план будущей реализации, а не выполненную реализацию.

## Permission profile

Сохраняйте compact capability-first policy:

```yaml
"*": ask
read: allow
edit: allow
glob: allow
grep: allow
list: allow
lsp: allow
bash: allow
todowrite: allow
"context7_*": allow
```

Не возвращайте command/path catalogs. `bash` — доверенная whole-tool capability, а не sandbox; remote/shared effects контролируются user approval и окружением.

## Source and release layout

- `src/*.ts` — authoritative TypeScript source modules; `src/orchestrator.ts` is the public barrel.
- `runtime/*.js` и `.d.ts` — generated release modules; `runtime/orchestrator.js` is the public entrypoint.
- `tools/orchestrator.ts` — exports `next`, `apply`, `validate`; OpenCode exposes them как `orchestrator_next`, `orchestrator_apply`, `orchestrator_validate`.
- `opencode-agents.py` installs agents, tools и runtime.
- `tests-ts/` — deterministic controller tests.
- `tests/e2e_system/` — black-box OpenCode harness.

Generated runtime должен быть rebuilt перед commit и совпадать с source.

## Change process

1. Прочитайте README, SECURITY, ROADMAP и всех affected producers/consumers.
2. Меняйте pure controller до tools/prompts, когда изменяется семантика.
3. Добавляйте deterministic tests для каждого legal/illegal transition и migration.
4. Держите `agents/orchestrator-*.md` и `docs/orchestrator-*.md` byte-identical.
5. Сохраняйте unknown/customized installed files при update.
6. Для release обновляйте `VERSION`, package version, installer version, agent markers и CHANGELOG вместе.
7. Не объявляйте release завершённым до fresh install/status и archive verification.

## Required checks

```bash
npm test
python3 -m py_compile opencode-agents.py
python3 tests/test_cli.py
python3 tests/test_routing.py
bash tests/test-cli.sh
git diff --check
```

Run `opencode debug config` и live E2E, когда binary/auth/provider доступны. Иначе укажите точный environment blocker; не выдавайте static tests за live provider journey.

## Repository exclusions

Не коммитьте credentials, provider auth, session databases, MCP tokens, `.env`, пользовательский source, generated target-repository `1_orchestrator/`, `.tmp`, `node_modules`, logs или test workspaces.
