# Agent Maintenance Guide

## Product contract

Репозиторий поставляет четыре planning-only OpenCode agents и один Python controller с thin TypeScript adapter:

- `orchestrator-analyst` — sole primary и клиент controller loop;
- `orchestrator-discovery` — repository evidence, traceability, material questions и stage map;
- `orchestrator-stage-planner` — один technical/human-review stage;
- `orchestrator-stage-reviewer` — independent discovery/stage/human-review gate;
- `runtime/orchestrator_core/` — единственный production source of workflow mechanics; `tools/orchestrator.ts` только adapter.

Python является production controller; TypeScript adapter не содержит второй state machine.

## Architecture rules

1. Prompts не вычисляют routing, revisions, convergence или reopening closure.
2. Custom tools остаются тонкими wrappers над одним runtime; не добавляйте вторую state machine в `tools/`.
3. `plan.md` генерируется controller и не является authoritative machine state.
4. Semantic agents пишут только controller-selected output и возвращают typed payload.
5. Каждый material REQ/NFR связан с owning stage, reciprocal scenario и acceptance.
6. Каждый internal contract имеет producer; каждый non-terminal contract имеет consumer и dependency path.
7. Convergence использует содержимое существующих evidence paths, а не hash от модели.
8. Reopening затрагивает минимальный transitive dependency/contract subgraph и требует user approval для уже принятого upstream defect.
9. Не добавляйте artifact/status/tool, если существующий typed contract выражает тот же инвариант.

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

Сохраняйте компактную capability-first policy:

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

Не возвращайте command/path catalogs в frontmatter. `bash` — доверенная whole-tool capability и не sandbox; remote/shared effects контролируются user approval и окружением.

## Source and release layout

- `orchestrator_core/` — authoritative Python source for repository tests.
- `runtime/orchestrator_core/` — installable copy of the same package.
- `runtime/orchestrator.py` — JSON CLI entrypoint used by the adapter.
- `tools/orchestrator.ts` — exports `next`, `apply`, `validate`; OpenCode exposes them as `orchestrator_next`, `orchestrator_apply`, `orchestrator_validate`.
- `opencode-agents.py` installs `agents/*.md`, `tools/*.ts`, `runtime/**/*.py` plus managed AGENTS guidance.

Generated runtime must be rebuilt before commit and match source exactly.

## Change process

1. Read README, SECURITY, ROADMAP and all affected producers/consumers.
2. Change pure runtime before tools/prompts when semantics change.
3. Add deterministic tests for every new legal/illegal transition and migration.
4. Keep `agents/orchestrator-*.md` and `docs/orchestrator-*.md` byte-identical.
5. Preserve unknown/customized installed files during update.
6. For a release update `VERSION`, installer version, every agent marker, package version and CHANGELOG together.
7. Do not announce release completion before fresh install/status and archive verification.

## Required checks

```bash
npm install
npm run test:ts
python3 tests/test-cli.py
python3 tests/test-routing.py
python3 tests/test-security.py
python3 tests/run_fast.py
bash tests/test-cli.sh
python3 -m py_compile opencode-agents.py tests/e2e_system/harness.py tests/e2e_system/run_e2e.py
git diff --check
```

Run `opencode debug config` and live E2E when binary/auth/provider are available. Otherwise record the exact environment blocker; do not claim a live provider journey.

## Repository exclusions

Do not commit credentials, provider auth, session databases, MCP tokens, `.env`, user source, generated target-repository `1_orchestrator/`, `.tmp`, `node_modules`, logs or test workspaces.
