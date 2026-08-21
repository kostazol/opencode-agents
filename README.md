# OpenCode Agents 6.0

Набор из четырёх planning-only агентов и нативного TypeScript controller для OpenCode. Он предназначен для сложных изменений в незнакомом репозитории: исследует фактические связи, находит скрытые contracts и NFR, задаёт только material questions и выпускает проверенный реализационный план.

Это не исполнитель продукта и не генератор большого документа ради документа. Результат workflow — план, достаточный для реализации без повторного исследования senior-разработчиком.

## Состав

- `orchestrator-analyst` — единственный primary; общается с пользователем и исполняет controller-selected actions.
- `orchestrator-discovery` — исследует код, Git history, tests, configuration, schemas, integrations и operations.
- `orchestrator-stage-planner` — детализирует один технический этап или его понятную пользователю версию.
- `orchestrator-stage-reviewer` — независимо проверяет discovery, технический этап и human-review artifact.
- `tools/orchestrator.ts` — нативно экспортирует `orchestrator_next`, `orchestrator_apply` и `orchestrator_validate`.
- `src/*.ts` — единственный production source of truth для workflow-механики; `runtime/orchestrator.js` — generated public entrypoint.

Python используется только одноразовым installer и внешним E2E harness; controller не запускает Python subprocess.

## Архитектура

```text
OpenCode
  └─ tools/orchestrator.ts
       ├─ orchestrator_next
       ├─ orchestrator_apply
       └─ orchestrator_validate
            └─ runtime/orchestrator.js + compiled modules
                 ├─ protocol + traceability
                 ├─ deterministic next/apply reducer
                 ├─ revisions + idempotency
                 ├─ convergence + reopening
                 └─ atomic store + journal + recovery
```

LLM выполняет смысловую работу. Controller выполняет только механику, которую модель не должна вспоминать заново в каждом turn.

Primary loop:

```text
orchestrator_validate
  → orchestrator_next
  → semantic subagent или user decision
  → orchestrator_apply
  → repeat
```

## Что проверяет discovery

`analysis.json` использует стабильные IDs:

- `REQ-NNN` — функциональное требование;
- `NFR-NNN` — quality constraint;
- `DEC-NNN` — решение;
- `CON-NNN` — material producer/consumer contract;
- `AC-NNN` — observable acceptance;
- `SCN-NNN` — обязательный сценарий;
- `SNN` — coherent implementation stage.

Validator требует полный путь:

```text
REQ/NFR → owning stage → reciprocal scenario → acceptance
```

Для contracts проверяются producer, consumers, reciprocal stage declarations и dependency order. Change surfaces требуют явной проверки применимых NFR; важную категорию нельзя молча пропустить.

## Workflow

```text
discovery
  → independent discovery review
  → user approval of reviewed stage map
  → plan/review S01 until PASS
  → plan/review S02 until PASS
  → ...
  → human-review plan/review for every stage
  → APPROVE PLAN or feedback
  → READY
```

`PASS` означает достаточность плана будущей реализации, а не наличие реализованного продукта.

## Durable artifacts

```text
1_orchestrator/<request>/
├── plan.md
├── discovery.md
├── analysis.json
├── questions.md
├── feedback.md
├── stages/
│   ├── <NN>-<slug>.md
│   └── <NN>-<slug>.human-review.md
├── reviews/
│   ├── discovery.md
│   ├── <NN>.md
│   └── <NN>-human-review.md
└── .orchestrator/
    ├── state.json
    ├── journal.jsonl
    └── transaction.json
```

`plan.md` генерируется controller и служит читаемым индексом. Authoritative routing state находится в `.orchestrator/state.json`.

## Устойчивость

Controller обеспечивает:

- schema-versioned analysis и state;
- strict artifact identity и canonical paths;
- один pending transition;
- monotonic state/stage/human-review revisions;
- optimistic concurrency;
- idempotent replay и conflicting-replay rejection;
- request lock;
- atomic state/plan transaction;
- crash recovery и append-only journal;
- bounded `REVISE` convergence по реальному содержимому evidence-файлов;
- controlled reopening минимального dependency/contract subgraph;
- strict legacy `plan.md` migration.

## Permissions

Default profile предназначен для доверенного репозитория в чистом disposable checkout:

```yaml
permission:
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

Агент может запускать пропорциональные build/tests/scripts и временно менять checkout для проверки гипотезы. Неизвестные отдельные capabilities наследуют `ask`. `bash: allow` не является sandbox; подробности — в [SECURITY.md](SECURITY.md).

## Установка

Локально из checkout:

```bash
python3 opencode-agents.py install --source .
python3 opencode-agents.py status --source .
python3 opencode-agents.py update --source .
```

Из конкретного опубликованного commit/tag:

```bash
curl -fsSL https://raw.githubusercontent.com/kostazol/opencode-agents/62b370be2456515f42e43555581bd7101ffaeeb2/opencode-agents.py \
  | python3 - install --repository kostazol/opencode-agents --ref <commit-or-tag>
```

Installer копирует:

```text
agents/*.md
tools/*.ts
runtime/**/*.js
```

После install/update полностью перезапустите OpenCode.

## Разработка

Production controller написан на Node-compatible TypeScript и не использует Bun-only APIs.

```bash
npm test
python3 -m py_compile opencode-agents.py
python3 tests/test_cli.py
python3 tests/test_routing.py
bash tests/test-cli.sh
```

`npm test` выполняет TypeScript build, typecheck custom tool и deterministic runtime tests. Live provider journey запускается отдельно через E2E harness, потому что требует установленный OpenCode, пользовательскую авторизацию и provider quota.


## Immutable remote install

Remote installation resolves one `--ref` to a commit SHA and fetches the package tree and every blob from that same SHA. Pin the raw installer and pass the same immutable ref; do not use moving `main`.

```bash
python opencode-agents.py install --repo kostazol/opencode-agents --ref v6.0.1 --target ~/.config/opencode
```

<!-- 6.0.1-install:start -->
## Stable 6.0.1 immutable install

The controller remains four semantic agents, one TypeScript controller, and three native OpenCode tools. The installer and package tree below are both pinned to the same immutable Git commit; `main` is deliberately not used.

```bash
curl -fsSLO https://raw.githubusercontent.com/kostazol/opencode-agents/62b370be2456515f42e43555581bd7101ffaeeb2/opencode-agents.py
python opencode-agents.py install \
  --repo kostazol/opencode-agents \
  --ref 62b370be2456515f42e43555581bd7101ffaeeb2 \
  --target ~/.config/opencode
python opencode-agents.py status --target ~/.config/opencode
```

For an update, use the same immutable source and an explicit backup location:

```bash
python opencode-agents.py update \
  --repo kostazol/opencode-agents \
  --ref 62b370be2456515f42e43555581bd7101ffaeeb2 \
  --target ~/.config/opencode \
  --backup ~/.config/opencode.backup-6.0.1
```
<!-- 6.0.1-install:end -->
