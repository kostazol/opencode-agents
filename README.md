# OpenCode Agents

Набор из четырёх OpenCode-агентов для технического анализа сложных изменений. Цель — не заменить разработчика и не генерировать объёмный документ ради документа, а раскопать фактические зависимости репозитория, проверить скрытые contracts и NFR, затем выдать реализационный план, по которому senior-разработчику не придётся повторять всё исследование.

## Состав

- `orchestrator-analyst` — единственный primary; общается с пользователем и исполняет action детерминированного controller.
- `orchestrator-discovery` — исследует код, Git history, tests, configuration, schemas, integrations и operations.
- `orchestrator-stage-planner` — детализирует один технический этап или его понятную пользователю версию.
- `orchestrator-stage-reviewer` — независимо проверяет discovery, технический этап и human-review artifact.

Product implementation не является результатом workflow. Агенты могут временно менять код для проверки гипотезы в disposable checkout, запускать build/tests/scripts и изучать локальные logs.

## Архитектура 6.0

Механика workflow вынесена из prompt в один Python runtime с тонким native TypeScript adapter:

```text
OpenCode
  └─ tools/orchestrator.ts
       ├─ orchestrator_next
       ├─ orchestrator_apply
       └─ orchestrator_validate
            ├─ tools/orchestrator.ts
            └─ runtime/orchestrator.py + runtime/orchestrator_core/
```

Python является единственным production controller; TypeScript-файл в `tools/` только передаёт typed вызов без shell interpolation. Python также используется installer и black-box E2E harness.

Controller отвечает за:

- versioned `analysis.json` и state;
- traceability `REQ/NFR → stage → SCN → AC`;
- producer/consumer contracts;
- выбор одного следующего action;
- monotonic revisions и optimistic concurrency;
- idempotent event replay;
- atomic state/plan transaction, request lock и crash recovery;
- bounded convergence по реальному содержимому evidence-файлов;
- controlled reopening минимального affected subgraph;
- generated `plan.md` и append-only journal.

Агенты отвечают только за смысловую работу: исследование, проектирование, вопросы и независимый review.

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

Один pending transition существует одновременно. Primary использует только цикл:

```text
orchestrator_validate
  → orchestrator_next
  → semantic agent или user decision
  → orchestrator_apply
  → repeat
```

`PASS` означает достаточность плана, а не наличие реализованного продукта.

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

`plan.md` — generated читаемый индекс. Источником истины для routing является `.orchestrator/state.json`; semantic evidence хранится в остальных artifacts.

## Полнота анализа

`analysis.json` использует стабильные IDs:

- `REQ-NNN` — functional/business requirement;
- `NFR-NNN` — quality constraint;
- `DEC-NNN` — принятое решение;
- `CON-NNN` — material contract;
- `AC-NNN` — observable acceptance;
- `SCN-NNN` — обязательный сценарий;
- `SNN` — coherent implementation stage.

Validator отклоняет orphan requirements, неверных owners, односторонние scenario links, contract без producer/consumer, consumer без dependency на producer и пропущенную NFR applicability, вытекающую из change surfaces.

## Permissions

Default profile предназначен для доверенного repository в чистом disposable checkout:

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

Поиск, build, tests, Git diagnostics, .NET/Python/Node scripts и другие локальные доказательства не требуют command-by-command allowlist. Всё неизвестное наследует `ask`. `bash: allow` не является sandbox: remote/shared mutation, выход за checkout и раскрытие непубличных данных требуют отдельного согласия и безопасного окружения. Подробнее: [SECURITY.md](SECURITY.md).

## Установка

Из опубликованного release/ref:

```bash
curl -fsSL https://raw.githubusercontent.com/kostazol/opencode-agents/main/opencode-agents.py \
  | python3 - install --repository kostazol/opencode-agents --ref <release-tag-or-commit>
```

Локальная установка из checkout:

```bash
python3 opencode-agents.py install --source .
python3 opencode-agents.py status --source .
python3 opencode-agents.py update --source .
```

Installer копирует:

```text
agents/*.md
runtime/orchestrator.py
runtime/orchestrator_core/*.py
tools/*.ts
```

После install/update полностью перезапустите OpenCode.

## Разработка и проверки

Production runtime написан на Python 3.11+; OpenCode вызывает его через один тонкий TypeScript custom tool по JSON stdin/stdout protocol без shell interpolation.

```bash
npm install
npm run build
npm run test:ts
python3 tests/test-cli.py
python3 tests/test-routing.py
python3 tests/test-security.py
python3 tests/run_fast.py
bash tests/test-cli.sh
```

`npm run test:ts` проверяет protocol, traceability, routing, idempotency, revisions, convergence, reopening, store/recovery и реальный импорт/вызов custom-tool module через stub контракта `@opencode-ai/plugin`.

Live OpenCode scenarios запускаются отдельно, потому что требуют установленный `opencode`, пользовательскую авторизацию и provider access:

```bash
python3 tests/e2e_system/run_e2e.py
```

Отсутствие runtime/provider должно отмечаться как environment-blocked, а не подменяться утверждением об успешном live journey.
