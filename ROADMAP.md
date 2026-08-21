# Roadmap 6.0 — stable TypeScript planning orchestrator

## Статус

**DONE.** Все запланированные production-фазы реализованы. Предыдущий Python controller сохранён отдельным родительским commit как проверяемый промежуточный снимок; текущая ветка заменяет его одним Node-compatible TypeScript runtime, разделённым на небольшие source modules без дублирования state machine.

## Цель

Дать OpenCode практическую замену техническому аналитику для сложных изменений: глубоко исследовать репозиторий, обнаруживать скрытые зависимости и NFR, задавать только material questions и выпускать план, пригодный для реализации без повторного исследования.

## Архитектурный итог

```text
OpenCode native custom tools
  → TypeScript controller
  → state.json / journal.jsonl / generated plan.md
```

Модель отвечает за semantic reasoning. Controller отвечает за deterministic mechanics. Параллельной Python state machine нет.

## Реализованные этапы

### 0. Regression baseline — DONE

Сохранены installer contracts, prompt/static checks и изолированный OpenCode E2E harness.

### 1. Capability-first execution — DONE

Доверены универсальные local capabilities; всё неизвестное наследует `ask`. Planning выполняется в disposable checkout и может использовать build/tests/scripts без command-by-command каталога.

### 2. Versioned protocol и traceability — DONE

Реализован strict `analysis.json` с `REQ/NFR/DEC/CON/AC/SCN`, reciprocal links, stage ownership, producer/consumer validation и change-surface-driven NFR applicability.

### 3. Transition core и durable store — DONE

Реализованы pure next/apply reducer, one-pending-action invariant, monotonic revisions, optimistic concurrency, idempotency, lock, atomic transaction, journal и crash recovery.

### 4. Convergence и controlled reopening — DONE

Повторяющиеся unchanged findings ограничены; evidence digest считается controller по реальным файлам. Upstream defect переоткрывает только минимальный dependency/contract subgraph.

### 5. Native OpenCode adapter — DONE

Один `tools/orchestrator.ts` экспортирует `next`, `apply`, `validate`, которые OpenCode публикует как `orchestrator_next`, `orchestrator_apply`, `orchestrator_validate`, и напрямую вызывает TypeScript runtime без subprocess или shell interpolation.

### 6. Prompt integration — DONE

Primary сведён к controller loop. Discovery формирует machine-readable analysis; planner работает с одним stage; reviewer независимо проверяет discovery, technical и human-review modes.

### 7. Release verification — DONE

Есть TypeScript build/typecheck, deterministic runtime tests, installer install/status/update checks, prompt contracts, permanent CI и GitHub source archives для точных commit SHA. Provider-dependent E2E остаётся отдельным environment-dependent release check.

## Definition of Done

- TypeScript — единственный production workflow runtime.
- Legacy state либо мигрируется строго, либо отклоняется с actionable diagnostic.
- Primary не вычисляет routing и revisions вручную.
- Нет silent stale acceptance, double advance, unbounded `REVISE` или полного reset при локальном upstream defect.
- `VERSION`, package, installer, prompts, docs и generated runtime согласованы.
- Любой публикуемый source archive должен строиться из того же точного Git tree, который прошёл release gates.

<!-- 6.0.1-hardening:start -->
## ROADMAP DONE: 6.0.1 independent hardening

Все исполняемые local gates и три последовательных матрицы Linux/Windows/macOS × Node 22/24 завершены успешно. Machine-readable evidence находится в `release/6.0.1-gates.json`.

- Фактическая ветка: `agent/6.0.1-final-complete`.
- Base из `main`: `5c897d5b3afba74940fcd188d2a2e13b21ebcc0b`.
- Runtime/code ref: `62b370be2456515f42e43555581bd7101ffaeeb2`.
- Documentation ref: `be156bd707ab76ba0a8db1d18ddcda28610251ef`.
- Release ref: `6faaa57c637712059b89e2e2ca62b196c3a361aa`.
- Permanent CI ref: `efdee043ddf792c52f90454b1224f375d2e84389`.
- Архитектура: четыре semantic agents, один TypeScript controller, три native tools.
- Отдельная artifact-ветка или ZIP не заявляются; точный GitHub source archive доступен для любого указанного commit SHA.
<!-- 6.0.1-hardening:end -->
