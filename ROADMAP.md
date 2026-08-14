# Roadmap улучшения orchestrator agents

## Цель

Постепенно повысить безопасность, полноту анализа, устойчивость resume и предсказуемость workflow. Смысловые задачи остаются у LLM-агентов. Механические переходы состояния со временем переносятся в детерминированный controller.

## Принципы изменений

- Выполнять этапы последовательно, отдельными небольшими изменениями.
- Перед каждым изменением изучать все producer/consumer prompts, tests и документацию.
- После изменения agent prompt синхронизировать соответствующий `docs/orchestrator-*.md`.
- Не совмещать крупную переработку workflow с изменением требований к качеству планов.
- Сохранять обратную совместимость существующих durable artifacts либо добавлять явную миграцию schema.
- Каждый новый contract подтверждать на самом дешёвом достаточном уровне: pure transition tests для механики, OpenCode integration tests для tool/API integration, live model E2E только для semantic поведения prompts.
- Не переносить discovery, анализ требований, архитектурные решения и review в controller.
- Не считать test-only transition checkpoints полноценным доказательством автономного production journey.

## Целевая архитектура

### LLM-агенты отвечают за

- понимание запроса пользователя;
- исследование repository;
- выявление требований, решений и рисков;
- построение stage map;
- проектирование contracts и acceptance criteria;
- технический и пользовательский review.

### Детерминированный controller отвечает за

- чтение и проверку workflow state;
- выбор следующего допустимого перехода;
- управление revisions;
- проверку artifact identity и schema;
- безопасное обновление статусов;
- locking и защиту от concurrent resume;
- обработку retries, malformed results и recovery.

Controller предпочтительно реализовать как OpenCode plugin с custom tools. До появления plugin допустим отдельный Python или TypeScript controller, но broad `bash` не должен становиться постоянным API workflow.

## Целевая пирамида тестов

1. Static contract tests проверяют frontmatter, permissions, schemas, protocol tokens и синхронизацию authoritative prompts с docs.
2. Pure deterministic tests проверяют routing, revisions, reconciliation, migration, feedback propagation и illegal states без OpenCode, auth, сети и LLM.
3. Deterministic OpenCode integration tests проверяют server/API, sessions, native questions, task dispatch, permissions и artifact writes с управляемыми agent fixtures.
4. Live prompt tests проверяют production prompts и semantic качество на небольшом наборе representative scenarios.
5. Один uninterrupted full journey проверяет путь от нового запроса до `READY` без test-only checkpoints.

Live model matrix не должна быть основным PR test layer. Полный live-набор запускается nightly, перед release или после существенных prompt changes.

## Фаза 0 — Baseline и исправление test harness

### Задачи

1. Зафиксировать текущий набор fast tests и micro-E2E, число `opencode serve` startups, sessions, primary/subagent executions, median и p95 времени.
2. Разделить измерения на fixture setup, server startup, prompt-to-idle, subagents, polling и cleanup.
3. Исправить fixture setup, использующий строковые `replace()` без проверки результата. В частности, исключить silent no-op при попытке заменить revision, которой нет в seeded `plan.md`.
4. Создать typed fixture builders и artifact parsers вместо ручных substring mutation и substring assertions.
5. Проверять completed task status, отсутствие tool error, compact result и точную последовательность subagent calls; лишний или повторный call считать дефектом.
6. Добавить snapshot product workspace и allowlist разрешённых изменений только внутри ожидаемого `1_orchestrator/<request>/` target.
7. Перевести top-level E2E scripts на единый test runner с безопасным discovery, aggregate report и duration report.
8. Переименовать или документировать текущие micro-E2E как live OpenCode workflow transition tests: они используют test-only checkpoint и не являются полным journey.
9. Добавить каталог сценариев отказа, которые пока не покрыты:
   - malformed compact result;
   - повреждённый или частично записанный `plan.md`;
   - stale или mismatched artifact;
   - task timeout или cancellation;
   - permission denial;
   - повторяющийся `REVISE` без прогресса;
   - concurrent `RESUME`;
   - prompt injection из repository content;
   - shell и MCP mutation attempts.
10. Зафиксировать ожидаемые invariants workflow:
   - один active stage;
   - monotonic revisions;
   - `current_stage` существует в map;
   - зависимости current stage имеют допустимый статус;
   - indexed paths canonical;
   - status и artifact revisions согласованы.

### Результат

Измеримый baseline, корректный test harness и список проверяемых инвариантов без изменения production workflow.

### Критерий завершения

Для каждой следующей фазы определены regression tests и наблюдаемый ожидаемый эффект; fixture setup не может молча создать состояние, отличное от заявленного сценарием.

## Фаза 1 — Реальная read-only безопасность

### Задачи

1. Заменить broad `bash: "*": allow` у discovery, planner и reviewer на deny-by-default или минимальный allowlist безопасных команд.
2. Запретить неизвестные и mutating MCP tools по умолчанию.
3. Добавить во все repository-reading agents правило: repository content является недоверенным evidence и не может менять роль, permissions, output protocol или разрешённые paths.
4. Добавить adversarial tests для обходов через `python`, `node`, `env git`, `git -C`, shell redirection и mutating MCP.
5. Проверить, что разрешённые validation commands не меняют product files и Git state.

### Результат

Read-only становится техническим ограничением, а не только текстовой инструкцией.

### Критерий завершения

Все planning agents сохраняют рабочее repository research, но mutation attempts блокируются tests и permissions.

## Фаза 2 — Проверка discovery и stage map

### Задачи

1. Добавить fresh review discovery и полного stage map до первого `APPROVE`.
2. Reviewer должен независимо проверить:
   - полноту исходных outcomes;
   - actors, пользовательский сценарий и ожидаемую ценность;
   - unresolved conflicts и assumptions;
   - scope и non-goals;
   - применимые NFR;
   - stage boundaries и hidden dependencies;
   - consumed и produced contracts;
   - возможность проверить результат каждого stage.
3. Определить statuses и routing для `DISCOVERY_REVIEW: PASS|REVISE|BLOCKED` либо отдельный эквивалентный protocol.
4. Добавить resume tests для каждого нового durable состояния.

### Результат

Пользователь получает stage map, уже прошедший независимую профессиональную проверку.

### Критерий завершения

Неполный map не может попасть на `APPROVE` без review finding или явного user decision.

## Фаза 3 — Сквозная traceability требований

### Задачи

1. Ввести стабильные identifiers только для существенных элементов:
   - `REQ-NNN` — функциональное или бизнес-требование;
   - `NFR-NNN` — quality constraint;
   - `DEC-NNN` — принятое решение;
   - `CON-NNN` — material contract;
   - `AC-NNN` — acceptance criterion;
   - `SCN-NNN` — mandatory scenario.
2. Связать каждый `REQ` и `NFR` с owning stage и acceptance criterion.
3. Связать stage scenarios с проверяемыми requirements и contracts.
4. Reviewer должен обнаруживать:
   - requirement без stage;
   - requirement без acceptance;
   - stage без исходного requirement или обоснованного enabler outcome;
   - silently deferred requirement;
   - contract без producer или consumer.
5. Использовать traceability graph для вычисления affected stages при feedback.

### Результат

Можно доказать, что весь существенный запрос дошёл до stage plans и проверок.

### Критерий завершения

Каждое существенное требование имеет наблюдаемый путь `requirement -> stage -> scenario -> acceptance -> verification`.

## Фаза 4 — NFR, data, security и operations

### Задачи

1. Добавить trigger-based applicability matrix в discovery:
   - performance и capacity;
   - availability, resilience и recovery;
   - security, privacy и compliance;
   - data lifecycle, integrity и concurrency;
   - compatibility и migration;
   - observability и support;
   - rollout и rollback;
   - accessibility и localization;
   - cost и resource limits.
2. Для каждой категории фиксировать `required`, `not applicable` или `deferred`, evidence и owning stage.
3. Для `required` требовать измеримый или наблюдаемый acceptance signal.
4. Для `not applicable` требовать короткое обоснование.
5. Не копировать полный checklist в каждый stage: discovery выбирает применимые категории по change surface.

### Результат

Агенты проверяют не только функциональность, но и безопасность, надёжность, совместимость и эксплуатацию там, где они действительно важны.

### Критерий завершения

Материальная NFR-категория не может быть молча пропущена.

## Фаза 5 — Typed и versioned artifact protocols

### Задачи

1. Добавить `schema_version` в центральные durable artifacts.
2. Формально определить обязательные поля и enums для `plan.md`, `discovery.md`, `questions.md`, `feedback.md`, stage и review artifacts.
3. Добавить typed handoff envelope:
   - mode;
   - transition ID;
   - source revision;
   - target revision;
   - input paths;
   - expected output path;
   - reason code.
4. Убрать полный replacement suffix из `SUMMARY` при `MAP_CHANGE_REQUIRED`.
5. Создавать отдельный structured map-delta artifact либо другой однозначно разбираемый payload.
6. Добавить schema validation и migration tests.

### Результат

Routing опирается на однозначные данные, а не на интерпретацию длинного свободного текста.

### Критерий завершения

Malformed, stale и несовместимые artifacts отклоняются детерминированно с понятной recovery action.

## Фаза 6 — Controlled reopening passed stages

### Задачи

1. Разрешить planner или reviewer сообщить об evidence-backed дефекте в уже `PASS` dependency.
2. Вычислять affected passed ancestors и transitive dependents по contracts и traceability graph.
3. Формировать smallest affected subgraph, а не обязательно полный unfinished suffix.
4. Запрашивать user approval перед reopening.
5. Повышать revisions только затронутых stages и повторно проверять только affected subgraph.
6. Сохранять unaffected `PASS` stages и human reviews.

### Результат

`PASS` означает контролируемую стабильность, но не запрещает исправить поздно обнаруженную upstream-ошибку.

### Критерий завершения

Downstream evidence может безопасно исправить passed contract без полного сброса плана.

## Фаза 7 — Bounded convergence и история revisions

### Задачи

1. Добавить fingerprint review findings и обнаружение повторяющихся замечаний.
2. Отличать полезную новую revision от цикла без semantic progress.
3. Ввести budget по повторениям без прогресса, времени или стоимости с durable escalation пользователю.
4. Не использовать простой жёсткий лимит revisions: исправления с прогрессом должны продолжаться.
5. Сохранять revision history через immutable revisioned files либо append-only transition journal.
6. Записывать transition ID, producer, validation result, retry и recovery reason.

### Результат

Workflow не зацикливается бесконечно и сохраняет объяснимую историю изменений.

### Критерий завершения

Повторяющийся planner-review конфликт приводит к понятному user decision, а не к бесконечному циклу или бессодержательному blocker.

## Фаза 8 — Детерминированный controller

### Задачи

1. Реализовать controller сначала как чистую transition library с unit tests.
2. Controller должен принимать validated current state и событие, затем возвращать один допустимый action и next state.
3. Добавить atomic file update, expected revision и workspace lock.
4. Подключить library через OpenCode plugin с узкими custom tools, например:
   - `orchestrator_next`;
   - `orchestrator_accept_result`;
   - `orchestrator_record_answers`;
   - `orchestrator_record_feedback`;
   - `orchestrator_validate`.
5. Ограничить tools записью только в разрешённый `1_orchestrator/<request>/` target.
6. Сократить `orchestrator-analyst` до выполнения controller actions, делегирования semantic задач и взаимодействия с пользователем.
7. Сохранить human-readable Markdown artifacts как представление workflow.
8. Перенести существующую матрицу routing/revision/resume сценариев из live model E2E в pure transition-library tests.
9. Не создавать до controller отдельную дублирующую state machine только ради tests: временные validators и builders не должны становиться вторым источником routing truth.

### Результат

LLM больше не интерпретирует сложную state machine. Он выполняет однозначные actions controller и занимается только смысловой работой.

### Критерий завершения

Все routing, revision, resume и recovery transitions проходят через тестируемую transition library; prompt primary не содержит сложной процедурной логики.

## Фаза 9 — Быстрая и достоверная test pyramid

### Задачи

1. Сохранить keyword tests только для малого публичного prompt contract.
2. Сделать pure transition-library tests основным покрытием workflow mechanics.
3. Добавить transition property tests:
   - недостижимые и dead states отсутствуют;
   - любой durable intermediate state имеет recovery;
   - illegal transition отклоняется;
   - revisions монотонны;
   - повтор одного события идемпотентен.
4. Сгруппировать deterministic OpenCode integration tests под reusable server на worker, сохраняя отдельные workspace state и fresh session для каждого case.
5. Использовать минимальную hermetic config и deterministic agent fixtures для проверки OpenCode API, native questions, task dispatch, permissions и filesystem effects.
6. Оставить live production-prompt tier из трёх–пяти representative scenarios:
   - discovery и material questions;
   - stage planning и technical review;
   - `REVISE`, correction и fresh `PASS`;
   - human-review mismatch;
   - plan feedback и affected stages.
7. Добавить один полный uninterrupted workflow test без test-only checkpoints от нового запроса до `READY`.
8. Добавить repeated-run tests для оценки model variance semantic outputs и хранить model/provider, duration, token usage, retries и pass rate.
9. Добавить adversarial repository fixtures и permission bypass tests.
10. Добавить concurrency tests для двух одновременных `RESUME`.
11. Разделить запуск:
   - PR: static, pure deterministic, deterministic OpenCode integration и один live smoke;
   - nightly/release: полный live prompt tier, repeated runs и full journey.
12. После измерений добавить bounded parallelism на два worker и увеличивать его только при стабильных provider latency и rate limits.
13. Убрать duplicate polling/message fetches и сделать HTTP polling/cleanup deadline-aware, не сокращая общий timeout ради ускорения happy path.

### Результат

PR tests выполняются быстро и детерминированно, а меньший live tier проверяет реальное semantic поведение production prompts и полный workflow.

### Критерий завершения

Основные заявленные свойства workflow подтверждены executable tests подходящего уровня; full live suite имеет timing и flakiness telemetry.

## Рекомендуемый порядок применения

1. Фаза 0 — baseline и исправление test harness.
2. Фаза 1 — безопасность.
3. Фаза 2 — discovery review.
4. Фаза 3 — traceability.
5. Фаза 4 — NFR applicability.
6. Фаза 5 — typed protocols.
7. Фаза 6 — reopening passed stages.
8. Фаза 7 — convergence и history.
9. Фаза 8 — controller plugin.
10. Фаза 9 — быстрая и достоверная test pyramid.

Фаза 0 сначала устраняет ложноположительные tests и создаёт измеримый baseline. Фазы 2–4 улучшают качество анализа. Фазы 5–8 улучшают надёжность orchestration. Фаза 9 переносит механику в быстрый tier и сохраняет небольшой fidelity-focused live tier. Не объединять их в один большой change set.

## Шаблон задачи для агента

```text
Реализуй только фазу <N> из ROADMAP.md.

Перед изменениями прочитай AGENTS.md, README.md, все затронутые authoritative prompts, их docs-копии, producer/consumer contracts и tests. Не реализуй следующие фазы досрочно. Сохрани обратную совместимость либо добавь явную миграцию. Добавь поведенческие tests для новых contracts. Если меняется agent prompt, синхронизируй соответствующий docs/orchestrator-*.md. Выполни проверки из AGENTS.md и сообщи изменённые contracts, риски и оставшиеся ограничения.
```

## Definition of Done для каждой фазы

- Scope фазы соблюдён.
- Prompt, permissions, installer behavior, tests и docs согласованы там, где затронуты.
- Новые durable states имеют resume path.
- Новые schemas имеют validation и migration strategy.
- Новые permissions проверены adversarial tests.
- Нет изменения product repository во время planning workflow.
- Fixture builders подтверждают созданное состояние структурным parser, а не substring assertions.
- Live tests проверяют completed tool calls и точную допустимую последовательность делегирования.
- Изменение test architecture сохраняет хотя бы один production-prompt smoke и полный journey в соответствующем test tier.
- Fast tests, syntax checks, `git diff --check`, install/update tests, `opencode debug config` и релевантные micro-E2E пройдены.
