# OpenCode Agents

Четыре autonomous primary workflow для staged-аналитики и выполнения задач в OpenCode. Analyst сначала согласует этапы с пользователем, затем планирует каждый этап, проверяет соседние этапы и выпускает self-contained task files. Runtime guard безопасно продолжает только незавершённую внутреннюю работу.

## Архитектура

```text
orchestrator-analyst (рекомендуется: Terra)
  fresh INITIAL decomposition
  independent exhaustive question review
  fresh RESTAGE decomposition
  explicit user approval
  stage planning/review loops
  adjacent-pair consistency loops
  Sol backtrack authority and final review

orchestrator-analyst-single-model
  тот же staged workflow на caller model
  substantive backtrack требует решения пользователя
  no Sol review

orchestrator-executor <one-task.md> (рекомендуется: Luna)
  implementation/review/adjustment/final review

orchestrator-executor-single-model <one-task.md>
  implementation/review на caller model
```

Других primary agents и aliases нет. Analyst не меняет product code и Git. Executor принимает ровно один executable task file, не переключает ветки, не stage и не commit изменения.

## Analyst: полный цикл

### 1. Исследование и вопросы

Выберите `orchestrator-analyst` или `orchestrator-analyst-single-model` и отправьте полный запрос.

Fresh decomposer исследует repository и создаёт предварительную последовательность этапов. Другой fresh reviewer независимо проверяет скрытые material user-visible решения. Если нужны ответы:

```text
Итог: НУЖНЫ_ОТВЕТЫ
Target: 1_orchestrator/avatar-upload/
Этапы: 3
Вопросы:
- Q01: постоянный или временный URL? ...
Действие: ответьте на все вопросы одним сообщением
```

Вопросы приходят одним вызовом native OpenCode `question`: отдельные карточки, нормальный русский, подробные варианты и последствия, рекомендация при наличии evidence, custom answer. Caveman compression к вопросам не применяется. Решения сохраняются отдельно по каждой карточке; просьба пояснить открывает повторно только нерешённые карточки. После всех решений новый subagent заново исследует задачу и формирует этапы. Даже когда вопросов нет, запускается fresh RESTAGE-анализ: INITIAL proposal никогда не принимается автоматически.

### 2. Согласование этапов

Analyst показывает полную последовательность: outcome, boundaries, dependencies, expected path areas, contracts, tests, ordering, approvals и non-goals.

```text
Итог: НУЖНО_ОДОБРЕНИЕ
Target: 1_orchestrator/avatar-upload/
Approval ID: avatar-upload-g0-a7c2
Этапы:
- S01: storage contract and implementation
- S02: upload endpoint and validation
- S03: integration coverage and documentation
Действие: отправьте `APPROVE avatar-upload-g0-a7c2`
```

Только точная команда `APPROVE <approval-id>` запускает запись task files. Обычное «ок», другой ID или изменение требований не считается approval. До approval target tasks и journal не создаются.

### 3. Планирование каждого этапа

После approval analyst автономно выполняет для S01, затем S02 и далее:

```text
планирование одного этапа
fresh stage review
корректировка текущего этапа при findings
fresh stage review
```

Цикл продолжается до `PASS`. Planner пишет только текущий этап. Каждый task остаётся working vertical slice и содержит stage metadata, acceptance, prerequisites, expected product paths, implementation, tests и validation.

### 4. Согласованность соседних этапов

Когда все этапы отдельно прошли review, analyst проверяет пары строго по порядку:

```text
S01 + S02
S02 + S03
S03 + S04
```

Проверяются границы, зависимости, contracts, migrations/configuration, expected paths, execution order и test ownership. Исправление справа предпочтительно.

Левый этап можно менять как `MINOR`, только если неизменны:

- user-visible behavior;
- stage boundaries и dependencies;
- expected paths и contracts;
- test ownership и cases;
- execution ordering;
- approvals и non-goals.

После minor edit повторяются stale stage и pair reviews. Любое другое изменение — substantive.

Standard workflow передаёт substantive finding fresh Sol reviewer. Только Sol может разрешить exact corrective amendments, создать replacement effective-contract ID и выбрать самый ранний invalidated stage. Active suffix tasks сначала возвращаются в `DRAFT/PENDING`, затем planning/review повторяются последовательно. Initial approval делегирует Sol только доказанные corrective amendments, не новый scope. Single-model workflow останавливается и показывает пользователю точные команды `RESTART <lineage-id> FROM <stage-id>` и `KEEP <lineage-id>`.

После всех pair PASS standard workflow выполняет Sol final review. Planner переводит tasks в `READY/PASS` только после полной текущей цепочки проверок.

### 5. Результат

```text
Итог: READY
Target: 1_orchestrator/avatar-upload/
Approval ID: avatar-upload-g0-a7c2
Этапы:
- S01 revision 1 — PASS
- S02 revision 2 — PASS
- S03 revision 1 — PASS
Задачи:
- 1_orchestrator/avatar-upload/tasks/01-add-storage-operation.md
- 1_orchestrator/avatar-upload/tasks/02-add-upload-endpoint.md
Действие: none
```

Artifacts:

```text
1_orchestrator/<request>/tasks/<NN>-<slug>.md
1_orchestrator/<request>/planning-issues.md
```

`1_orchestrator` всегда находится внутри working directory текущей OpenCode session. Git root не меняет расположение. Index, manifest, ledger и отдельный checkpoint artifact не создаются.

## Reassess после выполнения

После выполнения части задач снова выберите analyst и передайте exact target, authoritative request и exact completed paths:

```text
Режим: REASSESS
План: 1_orchestrator/avatar-upload/
Исходный запрос: ...
Завершённые задачи:
- 1_orchestrator/avatar-upload/tasks/01-add-storage-operation.md
```

`COMPLETE/PASS` tasks immutable. Gap завершённого результата становится новой corrective task. Obsolete unexecuted task может получить `SUPERSEDED`, но не удаляется и не переименовывается. `IN_PROGRESS` или `BLOCKED` execution сначала должен завершить executor lifecycle.

## Executor

Пользователь сам создаёт или выбирает execution branch. Product worktree должен быть clean; workflow-owned `WORKFLOW_BASE/1_orchestrator/**` может оставаться modified/untracked.

Передайте executor ровно один task path:

```text
1_orchestrator/avatar-upload/tasks/01-add-storage-operation.md
```

Standard executor проверит preconditions, запишет `START_COMMIT`, выполнит implementation, ordinary review, Terra adjustment и Terra final review. Single-model executor завершает после model-inheriting implementation/review loop. Product diff остаётся uncommitted.

Не передавайте executor весь каталог, несколько tasks или исходный запрос. Следующий dependent task запускайте только после присутствия prerequisite result в подготовленной ветке.

## Structured recovery harness

Guard plugin предоставляет внутренний `workflow_certificate` tool. Analyst записывает machine-validated JSON state после каждого принятого перехода. Пользователь сертификаты не видит и не заполняет.

Это заменяет хрупкий разбор строк вроде `PLANNING: PASS` из model prose. Guard читает completed certificate tool calls, а обычный ответ остаётся дружелюбным сообщением человеку.

На OpenCode root-session idle guard:

- игнорирует child, non-analyst, busy, errored и cancelled sessions;
- не продолжает `WAITING_ANSWERS`, `WAITING_APPROVAL`, `BLOCKED` и `COMPLETE`;
- продолжает только turn с текущим `RUNNING` certificate;
- ничего не делает при отсутствующем certificate: неизвестное состояние не должно мешать пользователю;
- сохраняет исходные agent, model и variant;
- слушает `session.status` idle и compatibility `session.idle`;
- использует deterministic message ID, persisted marker, locks и максимум две recovery-попытки на один explicit user turn.

Plugin — emergency recovery guard, не workflow engine и не основной scheduler. `RUNNING` обязывает primary немедленно вызвать следующий tool в том же turn; standalone progress вроде «действие пользователя: ничего» запрещён.

## Понятные статусы

Analyst сообщает смену phase по-русски:

```text
Этап: Исследование. Стадия: 0/? — изучаю задачу. Действие пользователя: ничего.
Этап: Планирование. Стадия: 2/4 — готовлю tasks. Действие пользователя: ничего.
Этап: Проверка связи. Пара: S02+S03 — проверяю contracts. Действие пользователя: ничего.
Этап: Ожидание approval — отправьте `APPROVE <id>`.
Этап: Возврат. Стадия: 2/4 — Sol разрешил substantive backtrack.
Готово: план проверен и tasks готовы.
Стоп: <почему остановлено и точное действие пользователя>.
```

Internal role names, prompts, retries, certificates, signatures и journals не показываются.

## Безопасность

- Standard build, test, restore и localhost checks в trusted repository выполняются автономно.
- Secrets, deploy, publish, release, destructive actions, unrelated external effects и user-owned overlap требуют решения пользователя.
- Git mutation запрещена: agents не выполняют branch creation, checkout, stage, commit, reset, restore, clean, stash, merge, rebase или push.
- Prompt permissions уменьшают accidental access, но не являются OS sandbox.

## Состав

- `orchestrator-analyst`, `orchestrator-analyst-single-model` — staged analyst primaries.
- `orchestrator-stage-decomposer` — INITIAL/RESTAGE evidence and decomposition.
- `orchestrator-stage-question-reviewer` — independent exhaustive question review.
- `orchestrator-task-planner` — sole task/journal writer, one stage per call.
- `orchestrator-plan-reviewer` — one-stage review.
- `orchestrator-stage-pair-reviewer` — adjacent-pair consistency review.
- `orchestrator-plan-ultra-reviewer` — Sol backtrack authority and final review.
- `orchestrator-executor`, `orchestrator-executor-single-model` и execution support roles — one-task execution.
- `analyst-workflow-guard.js` — structured-certificate idle recovery plugin.

## Установка

```bash
curl -fsSL https://raw.githubusercontent.com/kostazol/opencode-agents/main/opencode-agents.py | python3 - install
curl -fsSL https://raw.githubusercontent.com/kostazol/opencode-agents/main/opencode-agents.py | python3 - update
curl -fsSL https://raw.githubusercontent.com/kostazol/opencode-agents/main/opencode-agents.py | python3 - status
```

После install/update полностью перезапустите OpenCode. Agents, custom tool и plugin загружаются только при старте. Plugin устанавливается в `~/.config/opencode/plugins/analyst-workflow-guard.js`; запись в `opencode.json` не нужна.

## Проверка

```bash
python3 tests/test-cli.py
node --test tests/test-plugin.mjs
python3 -m py_compile opencode-agents.py
node --check plugins/analyst-workflow-guard.js
opencode debug config >/dev/null
```

## Источники OpenCode harness

- Plugin lifecycle: <https://opencode.ai/docs/plugins/>
- Custom tools: <https://opencode.ai/docs/custom-tools/>
- Server message API: <https://opencode.ai/docs/server/#messages>
- Agents and child sessions: <https://opencode.ai/docs/agents/#subagents>
