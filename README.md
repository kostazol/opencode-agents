# OpenCode Agents

Минимальный planning workflow для OpenCode. Один primary управляет тремя fresh subagents, а состояние хранится в читаемых Markdown-артефактах.

## Агенты

- `orchestrator-analyst` — primary, вопросы, approval, routing и resume.
- `orchestrator-discovery` — repository evidence, material questions и оглавление этапов.
- `orchestrator-stage-planner` — подробный исполнимый план одного этапа.
- `orchestrator-stage-reviewer` — fresh review одного этапа.

Все определения начинаются с `orchestrator-`. Workflow планирует работу и не реализует product changes.

## Поток

```text
discovery
  -> questions when needed
  -> approval of stage map
  -> plan S01
  -> review S01
     -> revise S01 when needed
     -> PASS
  -> plan S02
  -> review S02
  -> ...
  -> READY
```

Одновременно активен один этап. Следующий этап начинается после `PASS` текущего.

## Артефакты

```text
1_orchestrator/<request>/
├── discovery.md
├── questions.md
├── plan.md
├── stages/
│   ├── 01-<slug>.md
│   └── 02-<slug>.md
└── reviews/
    ├── 01.md
    └── 02.md
```

`plan.md` — оглавление и источник состояния. Он содержит outcome, решения, ordered stage map, dependencies, consumed/produced contracts, revisions, statuses и ссылки на stage/review files.

`discovery.md` хранит evidence и assumptions. `questions.md` хранит текущий batch и ответы. Каждый stage file является самостоятельным планом для fresh implementation agent. Каждый review file фиксирует gate текущей revision.

## Запуск

Выберите `orchestrator-analyst` и отправьте запрос. Агент исследует repository, задаст только material вопросы и покажет оглавление. Для подтверждения отправьте:

```text
APPROVE
```

После approval этапы планируются и проверяются последовательно.

## Resume и диагностика

Обычный режим продолжает workflow автоматически:

```text
MODE: RUN
RESUME: 1_orchestrator/<request>/plan.md
```

Диагностический режим выполняет один переход:

```text
MODE: STEP
RESUME: 1_orchestrator/<request>/plan.md
```

`STEP` используется маленькими E2E-тестами. Любая новая session восстанавливает следующий шаг из artifacts, а не из истории чата.

## Установка

```bash
curl -fsSL https://raw.githubusercontent.com/kostazol/opencode-agents/main/opencode-agents.py | python3 - install
curl -fsSL https://raw.githubusercontent.com/kostazol/opencode-agents/main/opencode-agents.py | python3 - update
curl -fsSL https://raw.githubusercontent.com/kostazol/opencode-agents/main/opencode-agents.py | python3 - status
```

Update создаёт backup, удаляет известные неизменённые retired agents и сохраняет пользовательские изменения. После install/update полностью перезапустите OpenCode.

## Проверки

Быстрые проверки:

```bash
python3 tests/test-cli.py
python3 tests/test-routing.py
python3 -m py_compile opencode-agents.py tests/e2e_system/harness.py
git diff --check
```

System E2E используют обычную пользовательскую OpenCode-конфигурацию и временный product workspace:

```bash
python3 tests/e2e_system/test_discovery_questions.py
python3 tests/e2e_system/test_question_answers.py
python3 tests/e2e_system/test_approval.py
python3 tests/e2e_system/test_first_stage.py
python3 tests/e2e_system/test_next_stage.py
python3 tests/e2e_system/test_resume_review.py
python3 tests/e2e_system/test_revise_stage.py
python3 tests/e2e_system/test_plan_revision.py
python3 tests/e2e_system/test_reconcile_stage.py
python3 tests/e2e_system/test_map_change_approval.py
python3 tests/e2e_system/test_revision_resume.py
python3 tests/e2e_system/test_revision_four.py
python3 tests/e2e_system/test_complete.py
```

Каждый micro-E2E запускает `MODE: STEP` и проверяет один переход. Вместе snapshots покрывают продолжение из каждого durable состояния.

## Источники подхода

- [OpenCode agents](https://opencode.ai/docs/agents/)
- [BMAD Method](https://github.com/bmad-code-org/BMAD-METHOD)
- [bmad-loop](https://github.com/bmad-code-org/bmad-loop)
- [OpenAgents Control](https://github.com/darrenhinde/OpenAgentsControl)
- [GitHub Spec Kit](https://github.com/github/spec-kit)
- [GSD](https://github.com/open-gsd/gsd-core)
