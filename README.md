# OpenCode Agents

Два primary workflow для staged-аналитики и безопасного выполнения одной задачи в OpenCode. Analyst согласует этапы, планирует и проверяет их. Executor выполняет один готовый task. Единственный runtime harness — native OpenCode agentic task loop.

## Архитектура

```text
orchestrator-analyst (рекомендуется: Terra)
  fresh INITIAL decomposition
  iterative independent question review / native question / fresh DISCOVERY
  terminal PASS_NO_QUESTIONS
  fresh RESTAGE decomposition
  explicit user approval
  per-stage planning/review loops
  adjacent-pair consistency loops
  Sol only for substantive backtrack authority

orchestrator-executor <one-task.md> (рекомендуется: Luna)
  implementation/review/adjustment/final-review loop
```

Других primary agents и single-model variants нет. Analyst не меняет product code или Git. Executor принимает ровно один executable task, не переключает ветки, не stage и не commit изменения.

## Analyst

### 1. Исследование и вопросы

Выберите `orchestrator-analyst` и отправьте полный запрос. Fresh decomposer исследует repository и предлагает этапы. Другой fresh reviewer независимо ищет material user-visible решения, которые нельзя определить по evidence или reversible defaults.

Если ответы нужны, analyst вызывает native OpenCode `question` для полного текущего batch: отдельные карточки, нормальный русский, подробные варианты, последствия и custom answer. После полного ответа fresh decomposer дополнительно исследует repository в `DISCOVERY`, учитывает накопленные решения, затем fresh reviewer снова ищет material decisions. Ответы могут открыть новые факты и новые вопросы, поэтому фиксированного ограничения на число batches или вопросов нет. Clarification-only ответ повторно открывает только unresolved карточки текущего batch; новый discovery round начинается после их решения.

Цикл завершается только fresh `PASS_NO_QUESTIONS`, связанным с последним discovery и всеми накопленными решениями. Затем fresh RESTAGE обязателен; provisional INITIAL/DISCOVERY proposal автоматически не принимается. После accepted RESTAGE вопросы, question review и DISCOVERY запрещены для этой proposal lineage. Изменённый запрос инвалидирует proposal и начинает новый discovery workflow.

Для задач про OpenCode/runtime discovery роли читают project-owned `.opencode` source/config, определяют установленную версию через `opencode --version`, сверяются с актуальной официальной документацией и при необходимости official upstream source/types. Версия `@opencode-ai/plugin` не считается версией runtime. Отсутствие локального `node_modules`, checked-in tool catalog или direct-invocation fixture не переносится на пользователя: version-sensitive schema/dispatch проверяется bounded isolated `opencode serve --pure` localhost test на этапе реализации.

### 2. Approval

Analyst показывает complete RESTAGE proposal: outcome, boundaries, dependencies, expected path areas, contracts, tests, ordering, approvals и non-goals.

```text
Итог: НУЖНО_ОДОБРЕНИЕ
Target: 1_orchestrator/avatar-upload/
Approval ID: avatar-upload-g0-a7c2
Запрос: добавить avatar upload
Решения: none
Этапы:
- S01: storage contract and implementation
- S02: upload endpoint and validation
- S03: integration coverage and documentation
Действие: отправьте `APPROVE avatar-upload-g0-a7c2`
```

Только точная команда `APPROVE <approval-id>` разрешает запись tasks. Обычное «ок», другой ID или изменённые требования approval не дают. До approval tasks и journal не создаются.

### 3. Planning и per-stage review

После approval analyst автономно обрабатывает S01, затем S02 и далее:

```text
planning одного этапа
fresh stage review
correction при findings
fresh stage review до PASS
```

Planner пишет только текущий этап. Каждый task — self-contained vertical slice со stage metadata, acceptance, prerequisites, expected product paths, implementation, tests и validation.

### 4. Adjacent-pair review и backtrack

После всех stage PASS analyst проверяет пары строго по порядку: `S01+S02`, `S02+S03` и далее. Проверяются boundaries, dependencies, contracts, migrations/configuration, expected paths, execution order, approvals, non-goals и test ownership/cases. Correction справа предпочтительна.

Левый этап можно менять как `MINOR` только с доказательством неизменности behavior, boundaries, dependencies, paths, contracts, tests, ordering, approvals и non-goals. Затем повторяются invalidated stage/pair reviews.

Substantive earlier-stage finding передаётся fresh pinned-Sol reviewer только в режиме backtrack authority. Sol либо ограничивает correction текущим/правым этапом, либо разрешает exact amendments и определяет earliest invalidated stage. Sol не делает whole-plan final review: полная цепочка current stage PASS и adjacent-pair PASS достаточна для `READY/PASS`.

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

`1_orchestrator` всегда находится внутри working directory текущей OpenCode session. Git root расположение не меняет. Index, manifest, ledger и checkpoint artifact не создаются.

## Native OpenCode harness

Native agentic task loop — единственный scheduler. Primary вызывает fresh subagent через native task mechanism, получает результат и сразу вызывает следующий required tool в том же turn. Plugin, custom certificate, idle hook, prose-state parser и synthetic continuation отсутствуют.

Recovery plugin удалён: он дублировал native scheduling, добавлял скрытое состояние и synthetic messages, связывал корректность workflow с plugin lifecycle. Явные prompt contracts и native child-task completion дают более простой, наблюдаемый, agents-only flow.

Во время autonomous work phase update немедленно продолжается tool call. Progress-only final text запрещён. Final response допустим только при реальном user wait, blocker или завершении и всегда сообщает точное следующее действие.

## Reassess

После выполнения части задач снова выберите analyst и передайте exact target, authoritative request и exact completed paths:

```text
Режим: REASSESS
План: 1_orchestrator/avatar-upload/
Исходный запрос: ...
Завершённые задачи:
- 1_orchestrator/avatar-upload/tasks/01-add-storage-operation.md
```

`COMPLETE/PASS` tasks immutable. Gap становится corrective task. Obsolete unexecuted task может получить `SUPERSEDED`, но не удаляется и не переименовывается. `IN_PROGRESS` или `BLOCKED` execution сначала завершает executor lifecycle.

## Executor

Пользователь сам создаёт или выбирает execution branch. Product worktree должен быть clean; workflow-owned `WORKFLOW_BASE/1_orchestrator/**` может оставаться modified/untracked.

Передайте `orchestrator-executor` ровно один task path:

```text
1_orchestrator/avatar-upload/tasks/01-add-storage-operation.md
```

Executor проверяет status и prerequisites, требует non-detached `HEAD`, записывает immutable `START_COMMIT`, затем запускает fresh implementation, review, bounded adjustment и final review через native task loop. Product diff остаётся uncommitted. `DRAFT`, `SUPERSEDED`, `COMPLETE`, каталог, несколько tasks или исходный запрос отклоняются.

Следующий dependent task запускайте только после присутствия prerequisite result в подготовленной ветке.

## Безопасность

- Trusted build, test, restore и localhost checks выполняются автономно.
- Secrets, deploy, publish, release, destructive actions, unrelated external effects, material product choices и user-owned overlap требуют решения пользователя.
- Git mutation запрещена: agents не выполняют branch creation, checkout, stage, commit, reset, restore, clean, stash, merge, rebase или push.
- Prompt permissions уменьшают accidental access, но не являются OS sandbox.
- Analyst discovery/planning roles имеют только exact `opencode --version` и read-only `webfetch`, prompt-ограниченный официальными OpenCode docs/upstream; arbitrary shell запрещён. OpenCode 1.18.11 принимает для `webfetch` только scalar permission, поэтому URL allowlist в frontmatter недоступен.

## Состав

- `orchestrator-analyst` — staged planning primary.
- `orchestrator-stage-decomposer` — INITIAL/DISCOVERY/RESTAGE evidence и decomposition.
- `orchestrator-stage-question-reviewer` — independent current-batch question review до terminal PASS.
- `orchestrator-task-planner` — sole task/journal writer, one stage per call.
- `orchestrator-plan-reviewer` — one-stage review.
- `orchestrator-stage-pair-reviewer` — adjacent-pair consistency review.
- `orchestrator-plan-ultra-reviewer` — Sol substantive backtrack authority only.
- `orchestrator-executor` и execution support roles — one-task execution.

## Установка

```bash
curl -fsSL https://raw.githubusercontent.com/kostazol/opencode-agents/main/opencode-agents.py | python3 - install
curl -fsSL https://raw.githubusercontent.com/kostazol/opencode-agents/main/opencode-agents.py | python3 - update
curl -fsSL https://raw.githubusercontent.com/kostazol/opencode-agents/main/opencode-agents.py | python3 - status
```

Installer agents-only: устанавливает current agent files, удаляет только известные project-owned старые plugin и single-model files, сохраняет unknown/custom files. После install/update полностью перезапустите OpenCode: agent definitions загружаются при старте.

## Проверка

```bash
python3 tests/test-cli.py
python3 -m py_compile opencode-agents.py
opencode debug config >/dev/null
python3 tests/test-analyst-e2e.py
python3 tests/test-analyst-questions-e2e.py
```

Обе последние команды обязательны после любых изменений и требуют установленный и авторизованный OpenCode. Первая поднимает isolated `opencode serve --pure`, создаёт временный workspace fixture, проводит analyst через no-question terminal PASS и approval, проверяет S01/S02 `PASS` на revision 1 без `REVISE`, pair review, `FINALIZE`, отсутствие executor calls, synthetic user turns и product writes. Вторая отвечает первому native question batch через `/question/{requestID}/reply`, требует fresh DISCOVERY, затем второй batch из двух вопросов, ещё один DISCOVERY, terminal `PASS_NO_QUESTIONS`, единственный accepted RESTAGE из трёх этапов, обе adjacent pair проверки, три READY task и отсутствие обычных user messages для ответов. Она также запрещает question/discovery после RESTAGE. Допускаются максимум три bounded malformed `REJECTED` либо contract-invalid `BLOCKED` retry; substantive `BLOCKED` всегда завершает acceptance failure. Timeout на session по умолчанию 1800 секунд; переопределение: `ANALYST_E2E_TIMEOUT_SECONDS`.

## Источники OpenCode harness

- Agents and subagents: <https://opencode.ai/docs/agents/>
- Task tool: <https://opencode.ai/docs/tools/#task>
