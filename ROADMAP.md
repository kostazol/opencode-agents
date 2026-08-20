# Roadmap: стабильный planning orchestrator

## Цель

Сделать набор OpenCode-агентов практической заменой техническому аналитику: агент исследует незнакомый репозиторий, находит скрытые зависимости, задаёт только действительно необходимые вопросы и выпускает проверенный план реализации. Workflow должен восстанавливаться после прерываний и не тратить модельный контекст на механическое управление состояниями.

## Принципы

1. Смысловая работа остаётся у LLM: discovery, архитектурные решения, поиск зависимостей, проектирование сценариев и review.
2. Механика остаётся в одном deterministic core: state, revisions, routing, validation, locking, idempotency и recovery.
3. Локальные инструменты исследования доверены. Неизвестные и внешние capabilities используют `ask`; command-by-command allowlist не поддерживается.
4. Markdown остаётся основным читаемым результатом. Компактный JSON state и journal являются машинным контрактом, а не вторым пользовательским планом.
5. Один источник истины для переходов. Prompts, fixtures и plugin adapters не реализуют параллельные state machine.
6. Проверки выбираются по риску. Live-model matrix не подменяет быстрые deterministic tests.
7. Совместимость со старыми `plan.md` обеспечивается явной миграцией; silent reinterpretation запрещена.
8. Не добавлять сущность, статус или artifact, если то же свойство надёжно выражается существующим контрактом.

## Целевая архитектура

### Semantic agents

- `orchestrator-analyst` общается с пользователем и исполняет action, полученный от controller.
- `orchestrator-discovery` исследует требования, код, contracts, NFR и формирует stage map.
- `orchestrator-stage-planner` детализирует один stage или его human-review представление.
- `orchestrator-stage-reviewer` независимо проверяет discovery, stage plan или human review.

### Deterministic core

Один Python package отвечает за:

- schema-versioned state и legacy migration;
- canonical paths и artifact identity;
- traceability и NFR validation;
- next-action selection;
- monotonic revisions и expected-revision checks;
- atomic writes, request lock и crash recovery;
- idempotent transition IDs;
- finding fingerprints и no-progress escalation;
- controlled reopening минимального affected subgraph;
- append-only transition journal.

OpenCode integration состоит из трёх custom tools:

- `orchestrator_next` — вернуть или зарезервировать следующий typed handoff;
- `orchestrator_apply` — применить typed result/user event к ожидаемому transition;
- `orchestrator_validate` — проверить state, artifacts и workspace diagnostics.

Три tools предпочтительнее набора специализированных wrappers: меньше surface area, одна validation path и проще backward compatibility.

## Durable artifacts

```text
1_orchestrator/<request>/
├── plan.md                         # generated readable index
├── discovery.md                    # semantic evidence
├── analysis.json                   # typed discovery/traceability contract
├── questions.md                    # material user questions
├── feedback.md                     # readable feedback history
├── stages/
│   ├── <NN>-<slug>.md
│   └── <NN>-<slug>.human-review.md
├── reviews/
│   ├── discovery.md
│   ├── <NN>.md
│   └── <NN>-human-review.md
└── .orchestrator/
    ├── state.json                  # authoritative machine state
    ├── journal.jsonl               # explainable transition history
    └── transaction.json            # short-lived crash-recovery record
```

## Этапы реализации

### Этап 0 — Baseline

**Статус: DONE (`8d7d1cf`)**

Существующий harness, typed fixture validation, workflow invariants, failure catalog и telemetry сохраняются как regression baseline.

### Этап 1 — Исправить архитектурный план и release state

**Статус: IN PROGRESS**

- удалить преждевременное объявление `6.0.0`;
- зафиксировать capability-first permissions;
- заменить фазы с дублирующими механизмами на один core и три tools;
- определить реальные release gates.

**Gate:** roadmap не заявляет незавершённую функцию реализованной.

### Этап 2 — Versioned protocol, traceability и discovery quality

- реализовать `analysis.json` schema и validators;
- проверять `REQ/NFR/DEC/CON/AC/SCN`, stage ownership и contract producer/consumer;
- выводить применимые NFR из change surfaces и требовать evidence/acceptance;
- добавить independent discovery review до пользовательского approval;
- добавить legacy `plan.md` migration tests.

**Gate:** malformed/stale discovery не может перейти к approval; каждое material requirement имеет путь к stage, scenario и acceptance.

### Этап 3 — Transition core и durable store

- реализовать pure next/apply state machine;
- expected revision, idempotent transition IDs и one-pending-action invariant;
- monotonic stage/human-review revisions;
- atomic replace, request lock, recovery transaction и journal;
- deterministic handling timeout, cancellation, permission denial и malformed result.

**Gate:** legal/illegal transitions, repeated events, concurrent resume и crash recovery покрыты pure tests.

### Этап 4 — Convergence и controlled reopening

- fingerprint actionable findings;
- продолжать revisions при semantic progress;
- после повторения без изменения evidence эскалировать user decision;
- вычислять affected subgraph по dependencies и contracts;
- reopening только после user approval;
- сохранять unaffected `PASS` stages и reviews.

**Gate:** цикл без прогресса bounded; upstream defect исправляется без полного reset.

### Этап 5 — OpenCode adapter и installer

- добавить `orchestrator_next`, `orchestrator_apply`, `orchestrator_validate`;
- вызывать Python core через безопасный argv/stdin contract без shell interpolation;
- устанавливать tools и runtime cross-platform вместе с agents;
- использовать `context.directory` как workflow base и проверять containment;
- обновить status/update/retirement tests.

**Gate:** fresh temporary install содержит agents, tools и runtime; adapter contract проходит deterministic integration tests.

### Этап 6 — Prompt integration

- сократить primary prompt до controller action loop;
- добавить reviewer mode `DISCOVERY`;
- обязать discovery формировать `analysis.json` и trigger-based NFR applicability;
- обязать stage plan result покрывать owning requirements/contracts/scenarios;
- синхронизировать русские docs-копии;
- сохранить capability-first permissions: trusted local capabilities `allow`, остальное `ask`.

**Gate:** prompts не содержат ручную routing matrix; typed results принимаются только controller.

### Этап 7 — Test pyramid и release

PR tier:

- installer/static contracts;
- schema/traceability tests;
- transition/store/property tests;
- adapter integration tests;
- prompt contract tests.

Release tier:

- deterministic OpenCode integration;
- один uninterrupted workflow без test-only checkpoint;
- representative live scenarios для discovery, revise/pass, feedback и reopening;
- clean install/update/status check;
- `opencode debug config` при доступном runtime/provider.

**Gate:** все deterministic checks зелёные; live-зависимые проверки либо пройдены, либо явно отмечены как environment-blocked без ложного release claim.

## Definition of Done

- Все этапы 1–7 имеют отдельный commit.
- `VERSION`, prompts, installer, docs и tests согласованы.
- Legacy state либо мигрируется, либо отклоняется с actionable diagnostic.
- Primary не вычисляет revisions и routing самостоятельно.
- Product edits, сделанные для локальной проверки гипотезы, диагностируются через Git, но не считаются security failure и не входят в planning result.
- External effects и неизвестные tools требуют approval на уровне OpenCode/environment.
- Нет бесконечного `REVISE`, silent stale acceptance, concurrent double-advance или полного reset при локальном upstream defect.
- Финальный release manifest формируется только после выполнения gates.
