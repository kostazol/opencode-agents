# OpenCode Agents

Набор агентов и протоколов для OpenCode. Репозиторий ориентирован на управляемую разработку через Orchestrator v2: фиксация запроса, планирование, последовательная реализация, валидация и независимое ревью.

## Состав

```text
orchestrator-00-main-caveman (UI: orchestrator)
├── orchestrator-10-workflow-bootstrap-caveman
├── orchestrator-20-planner-caveman
├── orchestrator-30-planner-senior-caveman (Terra)
├── orchestrator-40-executor-caveman
├── orchestrator-50-validator-caveman
├── orchestrator-60-mini-reviewer-caveman
├── orchestrator-70-review-aggregator-caveman
└── orchestrator-80-final-reviewer-caveman (Terra)
```

- `agents/` — исходные prompt-файлы агентов.
- `protocols/` — общий протокол Orchestrator v2.
- `AGENTS.md` — правила сопровождения репозитория.
- `CHANGELOG.md` — история изменений.
- `VERSION` — версия конфигурации.

Все filenames используют общий `orchestrator-` prefix и номер порядка. OpenCode хранит agents в flat-папке, поэтому связанная группа остаётся рядом при сортировке и ручной работе с Markdown. Primary agent имеет UI name `orchestrator`.

## Что делает Orchestrator v2

- сохраняет неизменяемый запрос и baseline до изменения продукта;
- проводит разведку и проверяет prototype references перед каждой стадией;
- выполняет product-mutating stages последовательно;
- требует buildable/testable границы каждой стадии;
- запускает targeted, affected и broad validation;
- проводит независимые mini-review lanes;
- передаёт финальный результат независимому Terra reviewer;
- хранит планы, evidence, patches и логи в `.orchestrator/tasks/<workflow-id>/`;
- не создаёт временные Git-коммиты и не изменяет историю или индекс.

## Caveman skill — рекомендуется

[Caveman](https://github.com/JuliusBrussee/caveman) — официальный skill для коротких, но технически полных ответов. Его рекомендуется установить для экономии output-токенов и уменьшения лишнего текста.

Основной официальный installer:

```bash
npx -y github:JuliusBrussee/caveman -- --only opencode
```

Наш CLI не содержит копию Caveman. После своей установки он выводит эту команду и ссылку на официальный репозиторий. Если skill не установлен, внутренние workflow-агенты продолжают работу без него. Orchestrator не требует Caveman.

## Модельная политика

Только роли, которым нужна независимость senior-уровня, используют фиксированную модель:

- `orchestrator-30-planner-senior-caveman`: `openai/gpt-5.6-terra`;
- `orchestrator-80-final-reviewer-caveman`: `openai/gpt-5.6-terra`.

Остальные агенты наследуют выбранную модель OpenCode.

## Установка

Клонирование не требуется. CLI получает файлы через GitHub Contents/Git Trees API. Для private repository задайте `GITHUB_TOKEN`.

### Linux и macOS

```bash
curl -fsSL https://raw.githubusercontent.com/kostazol/opencode-agents/main/opencode-agents.py | python3 - install
curl -fsSL https://raw.githubusercontent.com/kostazol/opencode-agents/main/opencode-agents.py | python3 - update --prune-legacy
curl -fsSL https://raw.githubusercontent.com/kostazol/opencode-agents/main/opencode-agents.py | python3 - status
```

### Windows

```powershell
py -3 -c "import urllib.request; exec(urllib.request.urlopen('https://raw.githubusercontent.com/kostazol/opencode-agents/main/opencode-agents.py').read())" install
py -3 -c "import urllib.request; exec(urllib.request.urlopen('https://raw.githubusercontent.com/kostazol/opencode-agents/main/opencode-agents.py').read())" update --prune-legacy
py -3 -c "import urllib.request; exec(urllib.request.urlopen('https://raw.githubusercontent.com/kostazol/opencode-agents/main/opencode-agents.py').read())" status
```

`install` добавляет отсутствующие файлы. `update` заменяет изменённые файлы и создаёт backup. `update --prune-legacy` удаляет только старые имена агентов, ранее поставлявшиеся этим репозиторием, включая имена до current `orchestrator-` grouping. Неизвестные пользовательские prompt-файлы не удаляются.

Для другого fork или версии используйте `--repository owner/name` либо URL и `--ref branch-or-tag`:

```bash
curl -fsSL https://raw.githubusercontent.com/kostazol/opencode-agents/main/opencode-agents.py | python3 - install --repository owner/name --ref main
```

Полезные параметры:

- `--dry-run` — показать изменения без записи;
- `--target DIR` — выбрать другой OpenCode config root;
- `--backup-dir DIR` — выбрать каталог backup.

CLI также добавляет управляемый блок рекомендации Caveman в глобальный `AGENTS.md`, не затрагивая остальное содержимое файла.

После установки перезапустите OpenCode: agent, protocol и instruction-файлы читаются при запуске процесса.

## Проверка

```bash
# Linux/macOS
python3 tests/test-cli.py

# Windows
py -3 tests/test-cli.py
```

После установки конфигурации:

```bash
opencode debug config >/dev/null
```

## Безопасность

Репозиторий не содержит `opencode.json`, credentials, auth/session databases, MCP tokens, `.env`, tool output или workflow artifacts пользователя. Не добавляйте секреты, private keys и содержимое пользовательских репозиториев.
