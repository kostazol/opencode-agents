# OpenCode Agents

Минимальный planning workflow для OpenCode. Один primary управляет тремя fresh subagents, а состояние хранится в читаемых Markdown-артефактах.

## Агенты

- `orchestrator-analyst` — primary, вопросы, approval, routing и resume.
- `orchestrator-discovery` — repository evidence, material questions и оглавление этапов.
- `orchestrator-stage-planner` — компактный архитектурный план одного этапа с образцами, рисками и проверяемым результатом.
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
  -> reviewed human-readable plans
  -> APPROVE PLAN or feedback
  -> READY
```

Одновременно активен один этап. Следующий этап начинается после `PASS` текущего.

Технический `PASS` подтверждает качество stage plan для будущей реализации. После `PASS` всех этапов workflow создаёт рядом с каждым stage file упрощённый `.human-review.md` на русском языке и отдельно проверяет его соответствие техническому плану. Документ рассчитан на человека, который знает продукт и предметную область поверхностно: без глубокой архитектуры, но с ясным итогом этапа, обычным сценарием работы, границами и вопросами для подтверждения.

Вопросы, варианты, рекомендации, stage map, stage plans, reviews, assumptions, decisions и summaries пишутся по-русски. Protocol statuses, обязательные section headings, пути, команды и code identifiers сохраняются без перевода.

## Артефакты

```text
1_orchestrator/<request>/
├── discovery.md
├── questions.md
├── feedback.md
├── plan.md
├── stages/
│   ├── 01-<slug>.md
│   ├── 01-<slug>.human-review.md
│   └── 02-<slug>.md
└── reviews/
    ├── 01.md
    ├── 01-human-review.md
    └── 02.md
```

`plan.md` — оглавление и источник состояния. Он содержит outcome, решения, ordered stage map, dependencies, affected system areas, primary risks, consumed/produced contracts, revisions, statuses и ссылки на stage/review files.

`discovery.md` хранит evidence и assumptions. `questions.md` хранит текущий batch и ответы. Каждый stage file задаёт outcome, основную архитектуру, ближайшие образцы, обязательные ограничения и существенные риски. Для каждого обязательного бизнес-кейса и валидации он фиксирует вход или предусловия, действие, ожидаемый observable output, error, state или side effect, а также значимые значения или equivalence classes. Acceptance signals и способ проверки остаются явными. Имена и расположение тестов, fixtures, mocks, структура test framework, детали assertions и дополнительные найденные при реализации тесты остаются implementation agent. Каждый review file фиксирует gate текущей revision.

## Запуск

Выберите `orchestrator-analyst` и отправьте запрос. Агент исследует repository, задаст только material вопросы и покажет оглавление. Для подтверждения отправьте:

```text
APPROVE
```

После первого approval этапы планируются и проверяются последовательно. Затем создаются понятные пользовательские версии всех этапов. Пользователь читает их и отправляет точное `APPROVE PLAN` либо замечания обычным текстом. Замечания сохраняются, исследуются и возвращают затронутые этапы в planning/review loop. `READY` появляется только после `APPROVE PLAN`.

## Resume

Workflow продолжает работу автоматически:

```text
RESUME: 1_orchestrator/<request>/plan.md
```

Любая новая session восстанавливает следующий шаг из exact `RESUME` artifact, а не из истории чата. `WORKFLOW_BASE` означает текущую рабочую директорию и не добавляется в путь буквальным сегментом. Однопереходные checkpoints существуют только внутри E2E harness и не входят в production prompt.

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

System E2E читают реальную пользовательскую OpenCode-конфигурацию, но используют временные HOME, session DB, state, cache и product workspace. Micro-E2E отключают external plugins, чтобы plugin installation/cache не меняли рабочую среду:

```bash
python3 tests/e2e_system/test_discovery_questions.py
python3 tests/e2e_system/test_question_answers.py
python3 tests/e2e_system/test_approval.py
python3 tests/e2e_system/test_first_stage.py
python3 tests/e2e_system/test_next_stage.py
python3 tests/e2e_system/test_resume_review.py
python3 tests/e2e_system/test_missing_scenario_expectation.py
python3 tests/e2e_system/test_revise_stage.py
python3 tests/e2e_system/test_plan_revision.py
python3 tests/e2e_system/test_reconcile_stage.py
python3 tests/e2e_system/test_map_change_approval.py
python3 tests/e2e_system/test_revision_resume.py
python3 tests/e2e_system/test_revision_four.py
python3 tests/e2e_system/test_run_revise_continues.py
python3 tests/e2e_system/test_complete.py
python3 tests/e2e_system/test_human_review_creation.py
python3 tests/e2e_system/test_human_review_gate.py
python3 tests/e2e_system/test_human_review_revise.py
python3 tests/e2e_system/test_plan_approval.py
python3 tests/e2e_system/test_plan_feedback.py
python3 tests/e2e_system/test_plan_feedback_resume.py
python3 tests/e2e_system/test_legacy_human_review_migration.py
python3 tests/e2e_system/test_reset_stage_reserved_revision.py
python3 tests/e2e_system/test_human_review_mismatch_resume.py
```

Каждый micro-E2E использует test-only checkpoint из harness и проверяет один переход. Вместе snapshots покрывают продолжение из каждого durable состояния.

## Источники подхода

- [OpenCode agents](https://opencode.ai/docs/agents/)
- [BMAD Method](https://github.com/bmad-code-org/BMAD-METHOD)
- [bmad-loop](https://github.com/bmad-code-org/bmad-loop)
- [OpenAgents Control](https://github.com/darrenhinde/OpenAgentsControl)
- [GitHub Spec Kit](https://github.com/github/spec-kit)
- [GSD](https://github.com/open-gsd/gsd-core)
