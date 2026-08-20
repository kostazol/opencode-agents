# Security и эксплуатационная модель

## Default capability profile

Стандартный профиль рассчитан на доверенный repository в чистом disposable checkout:

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

Primary дополнительно доверяет native `question`, три controller tools и три штатных subagents. Неизвестные tools, MCP namespaces, skills и subagents наследуют `ask`.

## Что эта модель защищает

- Не требуется хрупкий список разрешённых .NET, Python, Node, Git или Docker commands.
- Локальный build/test/script evidence доступен агенту без постоянных approval prompts.
- Неизвестная отдельная capability не получает silent access.
- Machine state меняет только Python controller; prompts не записывают `state.json`, journal и transaction вручную.
- Request ID и canonical paths не позволяют выбрать соседний workflow target.
- Optimistic revision, lock, atomic transaction и idempotency уменьшают риск concurrent/double advance.
- Reviewer не передаёт доверенный hash: runtime читает реальные repository-relative evidence paths и вычисляет digest самостоятельно.

## Что эта модель не защищает

`bash: allow` и `edit: allow` доверены целиком. Fallback `* → ask` не анализирует семантику команды внутри shell и не является sandbox.

Перед действием, способным:

- изменить состояние за пределами disposable checkout;
- затронуть remote/shared infrastructure;
- опубликовать или удалить данные;
- передать наружу private source, logs, customer data, secrets или credentials;

агент обязан получить явное согласие пользователя. Реальная enforcement boundary для untrusted/confidential code должна находиться в окружении.

## Рекомендуемое окружение

Для обычного planning:

- чистый disposable clone/worktree;
- отсутствие production credentials;
- ограниченный набор подключённых mutating integrations;
- финальная проверка `git status`/diff;
- удаление checkout после результата.

Для недоверенного или конфиденциального кода:

- container/VM/sandbox либо отдельный OS user;
- read-only source mount или disposable overlay;
- ограниченный network egress;
- минимальные scoped credentials;
- CPU/memory/process/time limits;
- отдельная policy для mutating MCP и cloud/database tools.

OpenCode `--auto` может автоматически подтверждать `ask`; его следует использовать только когда внешние ограничения уже обеспечены окружением.

## Durable workflow data

Workflow хранит данные только в `1_orchestrator/<request>/`. `.orchestrator/state.json` и journal могут содержать названия внутренних contracts и путей, поэтому не следует автоматически публиковать target artifacts из private repositories.

`context7_*` используется только для публичных package identifiers, версий и API-вопросов. Private symbols, source fragments, credentials, environment values и proprietary logs туда не передаются.

## Проверки

Static и deterministic tests проверяют:

- capability-first frontmatter;
- unknown-tool fallback;
- controller ownership machine state;
- canonical paths и request containment;
- strict JSON parsing;
- state revisions, locking, idempotency и recovery;
- фактическое hashing evidence;
- bounded no-progress handling;
- controlled reopening.

Live permission, provider и full-journey assertions требуют конкретного установленного OpenCode и не считаются доказанными только static tests.
