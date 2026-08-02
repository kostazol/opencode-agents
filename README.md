# OpenCode Agents

Четыре автономных primary workflow для standard и single-model анализа и выполнения задач в OpenCode, с runtime guard незавершённого analyst workflow.

## Архитектура

```text
orchestrator-analyst (run with Terra)
  model-inheriting evidence discovery and task planning
  independent model-inheriting plan review
  independent Sol ultra plan review
  self-contained task Markdown files

orchestrator-analyst-single-model
  evidence discovery, planning, and review on caller model
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

Других primary agents, aliases и profile variants нет. Analyst не запускает implementation. Он может создать новый план либо пересмотреть существующий после выполнения части задач. Executor принимает ровно один executable task file и не переключает ветки, не stage и не commit изменения.

Каждый agent prompt self-contained и содержит только нужные ему workflow contracts. Runtime protocol file не устанавливается и не читается; согласованность producer/consumer fields проверяется tests. Global auto-discovered plugin продолжает analyst в той же session, если модель добровольно завершила turn до обязательного review или finalization.

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

Standard analyst выполнит model-inheriting evidence discovery/planning, fresh model-inheriting review и independent Sol ultra plan review. Single-model analyst выполнит discovery, planning и review на выбранной модели. Результат:

```text
Итог: READY
Задачи:
- 1_orchestrator/avatar-upload/tasks/01-add-storage-operation.md
- 1_orchestrator/avatar-upload/tasks/02-add-upload-endpoint.md
```

Каждый task file self-contained. `Ordered prerequisites` показывает, какие более ранние задачи должны быть завершены до выбранной задачи. Analyst не создаёт ветки и не меняет product code.

### 2. Подготовить execution branch

Пользователь самостоятельно создаёт или выбирает ветку. Product worktree должен быть clean; только `WORKFLOW_BASE/1_orchestrator/**` может оставаться untracked или modified.

```bash
git switch -c feature/avatar-storage
git status --short
```

Executor не выполняет `git switch`, `git add` или `git commit`.

### 3. Выполнить ровно одну задачу

Выберите `orchestrator-executor` с Luna для Luna implementation/review и Terra adjustment/final review либо `orchestrator-executor-single-model` для implementation/review loop только на выбранной модели. Передайте только один task path, без второго task и дополнительных инструкций:

```text
1_orchestrator/avatar-upload/tasks/01-add-storage-operation.md
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
1_orchestrator/avatar-upload/tasks/02-add-upload-endpoint.md
```

Не передавайте executor весь каталог, несколько task paths или исходный пользовательский запрос. Он работает только с выбранной задачей и перечисленными в ней prerequisites.

### 5. Пересмотреть оставшийся план

После выполнения части большого плана снова выберите analyst и передайте exact target, authoritative request и exact completed task paths:

```text
Режим: REASSESS
План: 1_orchestrator/avatar-upload/

Исходный запрос:
Добавить загрузку аватара пользователя с JPEG/PNG, лимитом 5 MB и тестами.

Завершённые задачи:
- 1_orchestrator/avatar-upload/tasks/01-add-storage-operation.md
```

Planner проверит, что заявленные задачи уже имеют `COMPLETE`, planning `PASS` и execution result `PASS`, не изменит их, повторно исследует repository и скорректирует только unexecuted remainder. Exact target может содержать ранее назначенный CREATE collision suffix. Наличие `IN_PROGRESS` или `BLOCKED` task останавливает reassessment до завершения её executor lifecycle. Пробел завершённого результата становится новой corrective task. Ненужная unexecuted task получает `SUPERSEDED`, но не удаляется и не переименовывается. Новые задачи получают номера после текущего максимума в двухзначном диапазоне до `99`.

Возможные результаты:

- `READY` — весь оставшийся scope доказуемо спланирован;
- `PARTIAL_READY` — готов полезный executable prefix, но дальнейшее планирование зависит от evidence, которое создаст его реализация;
- `SATISFIED` — completed outcomes уже полностью покрывают authoritative request;
- `BLOCKED` — нужен доступ, завершение active execution lifecycle или user-visible решение.

При `PARTIAL_READY` пользователь выполняет перечисленные ready tasks по одной через executor, затем явно возвращается к analyst `REASSESS` с их completed paths. Analyst и planner не запускают implementation автоматически.

### Одно уточнение перед автономным workflow

После bounded repository research и первого in-memory planning attempt analyst может один раз вернуть `CLARIFICATION_REQUIRED`. Вопросы задаются одним полным batch только для material user-visible решений, которые нельзя вывести из запроса и repository evidence. До ответа CREATE target остаётся отсутствующим, а REASSESS target не изменяется.

Ответьте одним сообщением с полученными `Clarification ID` и `Question IDs`. Любой answer turn закрывает gate, даже если ответ неполный. После этого planner и reviewers больше не задают вопросов: ordinary technical choices выбираются автономно по repository conventions и lowest-scope reversible default. Missing access, safety constraint, unfinished execution lifecycle или решение, без которого безопасное планирование невозможно, остаются явными `BLOCKED`, но не открывают новый question batch.

## Analyst

Оба analyst primary agents создают задачи под `1_orchestrator/<request>/tasks/`:

```text
1_orchestrator/<request>/tasks/<NN>-<slug>.md
1_orchestrator/<request>/planning-issues.md
```

`1_orchestrator` всегда создаётся внутри working directory, из которой запущена текущая OpenCode-сессия. Non-hidden имя предотвращает пропуск workflow artifacts glob-поиском OpenCode, который исключает dot-prefixed hidden directories. Git root и родительские каталоги не меняют расположение. Например, при запуске из `/repo/src/MyProject` artifacts находятся в `/repo/src/MyProject/1_orchestrator/`, даже если Git root — `/repo`. Expected product paths остаются относительными к `/repo/src/MyProject`; Git status paths `src/MyProject/...` нормализуются снятием этого prefix. Изменения вне `/repo/src/MyProject` считаются user-owned overlap. `REASSESS` всегда использует exact existing target и никогда не применяет CREATE collision suffix.

В `CREATE` model-inheriting planner сначала проводит bounded no-write evidence phase: раскладывает запрос на acceptance areas, ищет implementation/integration prototypes, существующие tests, test prototypes и applicable repository instructions. До завершения evidence phase будущий `1_orchestrator/<request>/` target обязан отсутствовать; planner не читает его и ничего не записывает. Затем planner создаёт working vertical slices. Каждый task self-contained, может зависеть от более ранних task paths и содержит acceptance, expected paths, проверяемые prototypes, обязательную test work и validation commands. Для `none found` task фиксирует search basis, ожидаемую новую область и ближайшую convention.

Fresh model-inheriting plan reviewer независимо проверяет repository evidence, полное покрытие запроса, зависимости, buildability, scope и тесты. Каждый reviewer сначала завершает exhaustive проверку всего текущего плана, затем одним ответом возвращает все независимые demonstrated actionable findings, упорядоченные dependency-first и по impact. Analyst передаёт reviewer output в planner `REVISE` verbatim, без переименования или ручной сборки полей. Planner нормализует complete singular, unnumbered и imperfectly numbered findings в batch; presentation-only numbering или wrapper не являются причиной `REJECTED`. Planner применяет все совместимые bounded corrections одной ревизией и записывает отдельную newest-first issue entry для каждого finding. Standard analyst после чистого `PASS` запускает fresh Sol ultra reviewer. Любой исправимый Sol batch возвращается planner, затем fresh model-inheriting review и новая Sol проверка. Ordering, dependency, test ownership, path allocation, decomposition, evidence accuracy и buildability findings на occurrences `1`–`3` всегда исправляются через `REVISE`; наличие нескольких технических вариантов само по себе не блокирует planning. Первое появление каждой signature имеет progress `NOT_APPLICABLE`; при `NONE` на occurrences `2`–`3` planner обязан применить materially different correction. Счётчик каждой signature независим. Planner выполняет `FINALIZE` только после обоих `PASS`. Single-model analyst завершает после model-inheriting review `PASS`. Occurrence `4` или greater одной и той же проблемы блокирует planning независимо от ошибочно возвращённого reviewer verdict.

После любого успешного `CREATE`, `REASSESS` или `REVISE` analyst немедленно запускает следующий обязательный review в том же user turn. Незавершённый review, число разных findings или cycles, elapsed time, context growth, добровольный model/tool budget и valid progressive checkpoint не разрешают `BLOCKED`, остановку или просьбу повторить, продолжить либо перезапустить запрос. Workflow останавливается только при missing access, safety constraint, unfinished declared execution lifecycle, unresolved user-visible product decision или occurrence `4` одной signature. Reviewers и planner находят task files через exact target-directory glob/read, поэтому Git-ignore rules не скрывают workflow artifacts.

Progressive planning возвращает `PARTIAL_READY` только когда bounded static discovery доказывает implementation-dependent uncertainty. Готовый prefix обязан быть independently useful и buildable, произвести durable evidence, а deferred scope, uncertainty IDs и reassessment conditions должны быть exact. Model-inheriting reviewer и, в standard workflow, Sol reviewer независимо подтверждают обоснование. Task count, complexity, time, context, tool budget, ordinary technical options и weak decomposition не являются допустимыми причинами partial planning.

Planner возвращает `REJECTED` без edits для malformed/contradictory mode input, семантически несовместимого finding batch или target collision. Это не user blocker: presentation-only rejection получает один planner retry с verbatim reviewer output, затем fresh rejection-recovery reviewer получает original request, exact base/target, current task paths и exact rejected response. Recovery reviewer читает actual tasks и не требует отсутствующий current planner `PASS`; metadata-only `BLOCKED` при readable tasks считается malformed internal response и повторяется. Rejected finalization перезапускает required review chain, collision использует deterministic suffixes `-2`, `-3`, ... без чтения workflow directory. Только planner проверяет существование exact candidate target через exact-path `read`, поэтому ignored existing targets и races не пропускаются. Immediate blocker остаётся отдельным от findings: `Findings: none` плюс exact blocker, user action и доказательство невозможности bounded correction.

Analyst возвращает только reviewed task paths. Index и manifest не создаются.

## Executor

Пользователь выбирает один task и заранее создаёт или переключает execution branch. Executor требует:

- существующий non-detached `HEAD`;
- task status `READY` и planning review `PASS`;
- завершённые prerequisite tasks;
- отсутствие staged, unstaged и untracked product changes;
- только точный `WORKFLOW_BASE/1_orchestrator/**` может оставаться workflow-owned dirty state; другой `1_orchestrator` в Git worktree считается user/product state.

`DRAFT`, `SUPERSEDED` и `COMPLETE` не являются executable входами. Analyst outcome не заменяет status выбранного task file.

Оба executor primary agents фиксируют `START_COMMIT`, но не меняют Git. Fresh implementation и ordinary reviewer чередуются. Standard finding проходит через Terra adjuster. В single-model workflow отдельного adjuster нет: специальный reviewer сам фиксирует bounded repair direction и при доказанной необходимости расширяет expected paths, но не меняет product code.

Execution findings хранятся newest-first рядом с task:

```text
1_orchestrator/<request>/tasks/<NN>-<slug>.issues.md
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
- `orchestrator-task-planner` — model-inheriting evidence discovery, task planning и planning-journal maintenance.
- `orchestrator-plan-reviewer` — independent model-inheriting plan review.
- `orchestrator-plan-ultra-reviewer` — independent Sol ultra plan review.
- `orchestrator-executor` — primary выполнения одной задачи.
- `orchestrator-executor-single-model` — primary выполнения одной задачи только на модели caller.
- `orchestrator-task-executor` — model-inheriting implementation role.
- `orchestrator-task-reviewer` — model-inheriting read-only ordinary reviewer standard workflow.
- `orchestrator-task-reviewer-single-model` — model-inheriting ordinary reviewer и task correction authority single-model workflow.
- `orchestrator-task-adjuster` — Terra task correction and scope authority standard workflow.
- `orchestrator-final-reviewer` — Terra final review and loop diagnosis.
- `analyst-workflow-guard.js` — runtime plugin: на root-session idle проверяет terminal workflow certificates и безопасно продолжает незавершённый analyst на исходных agent и model.

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

После install/update полностью перезапустите OpenCode: prompts, permissions и plugin загружаются при старте. Plugin автоматически устанавливается в `~/.config/opencode/plugins/analyst-workflow-guard.js`; отдельная запись в `opencode.json` не нужна.

Guard работает только для `orchestrator-analyst` и `orchestrator-analyst-single-model`. Latest non-synthetic user message и latest completed assistant message должны указывать один и тот же analyst agent; session с явно объявленным другим agent отклоняется до чтения messages. Guard игнорирует child sessions, errored или active turns, explicit cancellation и все другие agents. Valid `CLARIFICATION_REQUIRED` требует fresh planner certificate после completed evidence и planning attempt без edits. Valid `READY`, `PARTIAL_READY` или `SATISFIED` требует matching planner `FINALIZE`, closed clarification gate, task partitions, outcome, uncertainty fields и обязательные review results; valid `BLOCKED` требует matching planner evidence certificate. Synthetic continuations имеют persisted deduplication marker, максимум три повтора без workflow progress и двенадцать continuations на один user request.

При update устаревшие project-owned files архивируются в backup directory и удаляются точечно; пользовательские agents и plugins сохраняются.

## Проверка

```bash
python3 tests/test-cli.py
node --test tests/test-plugin.mjs
opencode debug config >/dev/null
```

## Repository safety

Репозиторий не содержит provider config, production credentials, auth/session databases, MCP tokens, `.env`, пользовательские workflow artifacts или tool logs.
