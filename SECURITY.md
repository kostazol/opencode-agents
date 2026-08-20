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

- Локальный build/test/script evidence доступен без хрупкого command allowlist.
- Неизвестная отдельная capability не получает silent access.
- Machine state меняет только TypeScript controller; prompts не записывают state/journal/transaction вручную.
- Request ID и canonical paths не позволяют выбрать соседний workflow target.
- Optimistic revision, lock, atomic transaction и idempotency уменьшают риск concurrent/double advance.
- Reviewer не передаёт доверенный hash: controller читает реальные repository-relative evidence files.
- Custom tool не запускает Python или shell subprocess.

## Что эта модель не защищает

`bash: allow` и `edit: allow` доверены целиком. Fallback `* → ask` не анализирует семантику команды внутри shell и не является sandbox.

Перед действием, способным изменить remote/shared state, выйти за disposable checkout, опубликовать/удалить данные или передать private source/logs/customer data/secrets, требуется явное согласие пользователя. Для untrusted/confidential code реальная enforcement boundary должна находиться в окружении.

## Рекомендуемое окружение

Для обычного planning:

- чистый disposable clone/worktree;
- отсутствие production credentials;
- ограниченный набор mutating integrations;
- финальная проверка `git status`/diff;
- удаление checkout после результата.

Для недоверенного или конфиденциального кода:

- container/VM/sandbox либо отдельный OS user;
- read-only source mount или disposable overlay;
- ограниченный network egress;
- минимальные scoped credentials;
- CPU/memory/process/time limits;
- отдельная policy для mutating MCP/cloud/database tools.

OpenCode `--auto` допустим только когда внешние ограничения уже обеспечены окружением.

## Durable workflow data

Workflow хранит данные в `1_orchestrator/<request>/`. State, journal и semantic artifacts могут содержать внутренние identifiers и paths, поэтому их не следует автоматически публиковать из private repositories.

`context7_*` используется только для публичных package identifiers, версий и API-вопросов. Private symbols, source fragments, credentials и proprietary logs туда не передаются.

## Проверки

Deterministic tests покрывают protocol/traceability, routing, revisions, idempotency, evidence hashing, convergence, reopening, locking, store persistence и recovery. Live provider и permission behavior требуют конкретного OpenCode runtime и не считаются доказанными только static tests.
