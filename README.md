# OpenCode Agents

Набор агентов и протоколов для OpenCode. Репозиторий ориентирован на управляемую разработку через Orchestrator v3: фиксация запроса, планирование, последовательная реализация, checkpoint commits, валидация и независимое ревью.

## Состав

```text
orchestrator-00-main (UI: orchestrator, OpenAI collaboration)
orchestrator-01-single-model-main (UI: orchestrator-single-model)
├── orchestrator-10-workflow-bootstrap
├── orchestrator-20-planner
├── orchestrator-25-planner-full (single-model)
├── orchestrator-30-planner-senior (Terra)
├── orchestrator-40-executor
├── orchestrator-45-checkpointer
├── orchestrator-50-validator
├── orchestrator-60-mini-reviewer
├── orchestrator-70-review-aggregator
├── orchestrator-75-escalation-reviewer (Terra)
└── orchestrator-80-final-reviewer (Terra)
```

### Назначение агентов

- `orchestrator` — управляет workflow с Terra-планированием и финальным Terra-ревью.
- `orchestrator-single-model` — управляет workflow одной выбранной моделью без Terra.
- `orchestrator-10-workflow-bootstrap` — фиксирует запрос, профиль и исходный baseline.
- `orchestrator-20-planner` — уточняет прототипы, формирует dispatch и ведёт состояние плана.
- `orchestrator-25-planner-full` — исследует, планирует и перепланирует в `SINGLE_MODEL`.
- `orchestrator-30-planner-senior` — строит и проверяет план в `OPENAI_COLLABORATION`.
- `orchestrator-40-executor` — реализует одну стадию или пакет исправлений.
- `orchestrator-45-checkpointer` — создаёт точный stage checkpoint commit после review PASS.
- `orchestrator-50-validator` — проверяет baseline, стадии, итог и идентичность артефактов.
- `orchestrator-60-mini-reviewer` — независимо проверяет один аспект изменений.
- `orchestrator-70-review-aggregator` — объединяет mini-review и формирует общий verdict.
- `orchestrator-75-escalation-reviewer` — независимо проверяет post-budget escalation в `OPENAI_COLLABORATION`.
- `orchestrator-80-final-reviewer` — выполняет финальное независимое Terra-ревью.

### Порядок запуска

1. Пользователь запускает `orchestrator` или `orchestrator-single-model`.
2. `orchestrator-10-workflow-bootstrap` фиксирует запрос и baseline.
3. Планирование: `20 → 50 → 30 → 50` для `OPENAI_COLLABORATION` либо `25 → 50 → 25 → 50` для `SINGLE_MODEL`.
4. Каждая стадия: `20 candidate → 50 AUTHORIZE_DISPATCH → 20 ACTIVATE_DISPATCH → 40 → 50 STAGE → 50 PREPARE_MINI_REVIEW → 20 ACTIVATE_REVIEW_EPOCH → 60` (параллельные lanes) `→ 70 → 20 MINI_REVIEW_RESULT → 45 → 20 CHECKPOINT_RESULT → 50 ACCEPT_STAGE → 20 ADVANCE`.
5. После PASS checkpointer создаёт stage commit, validator принимает стадию, а `orchestrator-20-planner` запускает следующую; после замечаний текущая stage остаётся активной. После двух unresolved mini-review/repair cycles `75` Terra adjudicates только реальные открытые риски; подтверждённый риск возвращается в replan и новый mini cycle.
6. Финальный цикл: `50 → PREPARE_MINI_REVIEW → 60 → 70 → 80 → 50` для `OPENAI_COLLABORATION` либо `50 → PREPARE_MINI_REVIEW → 60 → 70 → 50` для `SINGLE_MODEL`; repairable findings перезапускают видимый final cycle без numeric limit.

- `agents/` — исходные prompt-файлы агентов.
- `protocols/` — общий протокол Orchestrator v3.
- `AGENTS.md` — правила сопровождения репозитория.
- `CHANGELOG.md` — история изменений.
- `VERSION` — версия конфигурации.

Все filenames используют общий `orchestrator-` prefix и номер порядка. OpenCode хранит agents в flat-папке, поэтому связанная группа остаётся рядом при сортировке и ручной работе с Markdown. Primary agent имеет UI name `orchestrator`.

## Что делает Orchestrator v3

- сохраняет неизменяемый запрос и baseline до изменения продукта;
- проводит разведку и проверяет prototype references перед каждой стадией;
- выполняет product-mutating stages последовательно;
- требует buildable/testable границы каждой стадии;
- запускает targeted, affected и broad validation;
- проводит независимые mini-review lanes;
- передаёт финальный результат независимому Terra reviewer;
- хранит планы, evidence, patches, human-readable `status.md` и логи в `.orchestrator/tasks/<workflow-id>/`;
- создаёт один stage commit после review PASS, сохраняя user-owned staged entries и не переписывая историю.

## Статус workflow

После установки v3 human-readable status будет находиться здесь:

```text
.orchestrator/tasks/<workflow-id>/status.md
```

Файл показывает текущую стадию и общее число стадий, текущий шаг, repair/final-cycle attempt, review epoch, checkpoint commit, следующий action и требуемое решение пользователя. Primary agent также выводит короткую progress-строку после каждой видимой границы. `status.md` — удобный view; источники истины для исполнения остаются в `plan/master.md`, validation и review artifacts.

## Caveman skill — рекомендуется

[Caveman](https://github.com/JuliusBrussee/caveman) — официальный skill для коротких, но технически полных ответов. Его рекомендуется установить для экономии output-токенов и уменьшения лишнего текста.

Основной официальный installer:

```bash
npx -y github:JuliusBrussee/caveman -- --only opencode
```

Наш CLI не содержит копию Caveman. После своей установки он выводит эту команду и ссылку на официальный репозиторий. Если skill не установлен, внутренние workflow-агенты продолжают работу без него. Orchestrator не требует Caveman.

## Модельные профили

Выберите primary agent для проекта:

- `orchestrator` использует `OPENAI_COLLABORATION`: `orchestrator-30-planner-senior`, `orchestrator-75-escalation-reviewer` и `orchestrator-80-final-reviewer` фиксированы на `openai/gpt-5.6-terra`.
- `orchestrator-single-model` использует `SINGLE_MODEL`: `orchestrator-25-planner-full` наследует выбранную модель, а Terra-pinned agents недоступны через permissions.

Остальные агенты наследуют выбранную модель OpenCode. Profile фиксируется в workflow manifest до baseline capture и не меняется для follow-up requests.

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

`install` добавляет отсутствующие файлы. `update` заменяет изменённые файлы и создаёт backup. `update --prune-legacy` удаляет только прежние имена Orchestrator и его workflow-подагентов. Built-in и неизвестные пользовательские prompt-файлы не удаляются.

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
