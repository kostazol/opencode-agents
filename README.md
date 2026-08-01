# OpenCode Agents

Четыре автономных primary workflow для standard и single-model анализа и выполнения задач в OpenCode.

## Архитектура

```text
orchestrator-analyst (run with Terra)
  reconnaissance
  model-inheriting task planning
  model-inheriting plan review
  independent Sol ultra plan review
  self-contained task Markdown files

orchestrator-analyst-single-model
  reconnaissance, planning, and review on caller model
  no Sol ultra plan review

orchestrator-executor <one-task.md> (run with Luna)
  fresh implementation
  independent ordinary review
  Terra task adjustment
  Terra final review or loop diagnosis
  validated uncommitted result

orchestrator-executor-single-model <one-task.md>
  implementation and corrective ordinary review on caller model
  reviewer records task repair direction
  no separate final review
```

Других primary agents, aliases и profile variants нет. Analyst не запускает implementation. Executor принимает ровно один task file и не переключает ветки, не stage и не commit изменения.

Каждый agent prompt self-contained и содержит только нужные ему workflow contracts. Runtime protocol file не устанавливается и не читается; согласованность producer/consumer fields проверяется tests.

## Как пользоваться

После установки полностью перезапустите OpenCode. В agent selector выберите нужный primary agent.

### 1. Подготовить задачи через analyst

Выберите `orchestrator-analyst` с Terra для Sol final plan review либо `orchestrator-analyst-single-model` для workflow только на выбранной модели. Отправьте полный запрос одним сообщением:

```text
Добавь в API загрузку аватара пользователя.

Требования:
- принимать JPEG и PNG до 5 MB;
- сохранять файл через существующий storage abstraction;
- возвращать URL загруженного изображения;
- добавить unit и integration tests;
- не менять публичный контракт других endpoints.
```

Standard analyst выполнит reconnaissance, model-inheriting planning/review и independent Sol ultra plan review. Single-model analyst выполнит только reconnaissance, planning и review на выбранной модели. Результат:

```text
Итог: READY
Задачи:
- .orchestrator/avatar-upload/tasks/01-add-storage-operation.md
- .orchestrator/avatar-upload/tasks/02-add-upload-endpoint.md
```

Каждый task file self-contained. `Ordered prerequisites` показывает, какие более ранние задачи должны быть завершены до выбранной задачи. Analyst не создаёт ветки и не меняет product code.

### 2. Подготовить execution branch

Пользователь самостоятельно создаёт или выбирает ветку. Product worktree должен быть clean; `.orchestrator/**` может оставаться untracked или modified.

```bash
git switch -c feature/avatar-storage
git status --short
```

Executor не выполняет `git switch`, `git add` или `git commit`.

### 3. Выполнить ровно одну задачу

Выберите `orchestrator-executor` с Luna для Luna implementation/review и Terra adjustment/final review либо `orchestrator-executor-single-model` для implementation/review loop только на выбранной модели. Передайте только один task path, без второго task и дополнительных инструкций:

```text
.orchestrator/avatar-upload/tasks/01-add-storage-operation.md
```

Standard executor:

1. проверит branch, task status, prerequisites и clean product state;
2. зафиксирует `START_COMMIT` в task file;
3. запустит fresh implementation role;
4. запустит independent ordinary reviewer;
5. при findings вызовет Terra adjuster и fresh repair cycle;
6. завершит работу только после Terra final review `PASS`.

Product changes останутся uncommitted. После `DONE` пользователь проверяет diff и самостоятельно делает commit:

```bash
git status --short
git diff --check
git diff
git add <нужные-файлы>
git commit -m "feat: add avatar storage operation"
```

### 4. Выполнить следующую зависимую задачу

Сначала обеспечьте присутствие результата prerequisite task в подготовленной ветке: merge, cherry-pick или новая ветка от уже завершённой работы выполняются пользователем. Затем выберите `orchestrator-executor` и передайте следующий task path:

```text
.orchestrator/avatar-upload/tasks/02-add-upload-endpoint.md
```

Не передавайте executor весь каталог, несколько task paths или исходный пользовательский запрос. Он работает только с выбранной задачей и перечисленными в ней prerequisites.

## Analyst

Оба analyst primary agents создают задачи под `.orchestrator/<request>/tasks/`:

```text
.orchestrator/<request>/tasks/<NN>-<slug>.md
.orchestrator/<request>/planning-issues.md
```

Reconnaissance ищет implementation/integration prototypes, существующие тесты и test prototypes для новых тестов. Model-inheriting planner раскладывает запрос на working vertical slices. Каждый task self-contained, может зависеть от более ранних task paths и содержит acceptance, expected paths, prototypes, обязательную test work и validation commands.

Fresh model-inheriting plan reviewer проверяет полное покрытие запроса, зависимости, buildability, scope и тесты. Standard analyst после его `PASS` запускает fresh Sol ultra reviewer. Любое замечание Sol возвращает planner, затем fresh model-inheriting review и новую Sol проверку. Planner выполняет `FINALIZE` только после обоих `PASS`. Single-model analyst завершает после model-inheriting review `PASS`. Четвёртое появление одной и той же проблемы блокирует planning; разные проблемы продолжают исправляться при измеримом прогрессе.

Analyst возвращает только reviewed task paths. Index и manifest не создаются.

## Executor

Пользователь выбирает один task и заранее создаёт или переключает execution branch. Executor требует:

- существующий non-detached `HEAD`;
- task status `READY` и planning review `PASS`;
- завершённые prerequisite tasks;
- отсутствие staged, unstaged и untracked product changes;
- `.orchestrator/**` может оставаться workflow-owned dirty state.

Оба executor primary agents фиксируют `START_COMMIT`, но не меняют Git. Fresh implementation и ordinary reviewer чередуются. Standard finding проходит через Terra adjuster. В single-model workflow отдельного adjuster нет: специальный reviewer сам фиксирует bounded repair direction и при доказанной необходимости расширяет expected paths, но не меняет product code.

Execution findings хранятся newest-first рядом с task:

```text
.orchestrator/<request>/tasks/<NN>-<slug>.issues.md
```

Обычные роли читают только последние одну-две записи. Standard executor после трёх неудачных repairs одной semantic finding вызывает Terra full-history loop diagnosis; single-model executor завершает task как blocked. Разные findings продолжаются только при измеримом прогрессе.

Standard executor после ordinary review PASS запускает fresh Terra final reviewer. Его finding возвращается через adjuster, fresh executor и ordinary reviewer. Standard task получает `COMPLETE` только после Terra PASS; single-model task получает `COMPLETE` после ordinary review PASS. Product diff остаётся пользователю без commit.

## Автономность и безопасность

- Standard build, test, package restore и localhost-only testing через project commands выполняются автономно в trusted development repository. Raw network clients не выдаются как универсальный localhost escape hatch.
- Repository-controlled checks выполняются с обычными правами текущего пользователя. Production secrets не должны присутствовать в development environment.
- Agent prompts и direct-read permissions запрещают целевое использование common secret files, но search tools и запущенный repository code не являются OS sandbox.
- Secrets, credentials, deploy, publish, release, destructive actions, unrelated external effects и overlap с user-owned changes требуют решения пользователя.
- Git mutation полностью запрещена: нет branch creation, checkout, stage, commit, reset, restore, clean, stash, merge, rebase или push.

## Сообщения пользователю

Primary agents сообщают только смену пользовательской фазы:

```text
Планирование: ...
Анализ и реализация: ...
Проверка: ...
Финальное ревью: ...
Готово: ...
Стоп: <что требуется от пользователя>
```

Внутренние signatures, cycle counts, issue journals и handoffs не выводятся. Analyst возвращает task paths; executor возвращает изменённые product paths, проверки, риски и blocker.

## Состав

- `orchestrator-analyst` — primary анализа и подготовки задач.
- `orchestrator-analyst-single-model` — primary анализа и подготовки задач только на модели caller.
- `orchestrator-recon` — read-only поиск implementation/integration/test evidence.
- `orchestrator-task-planner` — model-inheriting task planning и planning-journal maintenance.
- `orchestrator-plan-reviewer` — independent model-inheriting plan review.
- `orchestrator-plan-ultra-reviewer` — independent Sol ultra plan review.
- `orchestrator-executor` — primary выполнения одной задачи.
- `orchestrator-executor-single-model` — primary выполнения одной задачи только на модели caller.
- `orchestrator-task-executor` — model-inheriting implementation role.
- `orchestrator-task-reviewer` — model-inheriting read-only ordinary reviewer standard workflow.
- `orchestrator-task-reviewer-single-model` — model-inheriting ordinary reviewer и task correction authority single-model workflow.
- `orchestrator-task-adjuster` — Terra task correction and scope authority standard workflow.
- `orchestrator-final-reviewer` — Terra final review and loop diagnosis.

## Установка

```bash
curl -fsSL https://raw.githubusercontent.com/kostazol/opencode-agents/main/opencode-agents.py | python3 - install
curl -fsSL https://raw.githubusercontent.com/kostazol/opencode-agents/main/opencode-agents.py | python3 - update
curl -fsSL https://raw.githubusercontent.com/kostazol/opencode-agents/main/opencode-agents.py | python3 - status
```

Windows:

```powershell
py -3 -c "import urllib.request; exec(urllib.request.urlopen('https://raw.githubusercontent.com/kostazol/opencode-agents/main/opencode-agents.py').read())" install
py -3 -c "import urllib.request; exec(urllib.request.urlopen('https://raw.githubusercontent.com/kostazol/opencode-agents/main/opencode-agents.py').read())" update
py -3 -c "import urllib.request; exec(urllib.request.urlopen('https://raw.githubusercontent.com/kostazol/opencode-agents/main/opencode-agents.py').read())" status
```

После install/update полностью перезапустите OpenCode: prompts и permissions загружаются при старте.

## Проверка

```bash
python3 tests/test-cli.py
opencode debug config >/dev/null
```

## Repository safety

Репозиторий не содержит provider config, production credentials, auth/session databases, MCP tokens, `.env`, пользовательские workflow artifacts или tool logs.
