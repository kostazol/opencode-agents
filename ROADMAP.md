# Roadmap 6.0 — stable TypeScript planning orchestrator

## Статус

**DONE.** Все запланированные production-фазы реализованы. Предыдущий Python controller сохранён отдельным родительским commit как проверяемый промежуточный снимок; текущий commit заменяет его одним Node-compatible TypeScript runtime, разделённым на небольшие source modules без дублирования state machine.

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

Один `tools/orchestrator.ts` экспортирует `next`, `apply`, `validate` и напрямую вызывает TypeScript runtime без subprocess или shell interpolation.

### 6. Prompt integration — DONE

Primary сведён к controller loop. Discovery формирует machine-readable analysis; planner работает с одним stage; reviewer независимо проверяет discovery, technical и human-review modes.

### 7. Release verification — DONE

Есть TypeScript build/typecheck, deterministic runtime tests, installer install/status/update checks, prompt contracts и downloadable source archive. Provider-dependent E2E остаётся отдельным environment-dependent release check.

## Definition of Done

- TypeScript — единственный production workflow runtime.
- Legacy state либо мигрируется строго, либо отклоняется с actionable diagnostic.
- Primary не вычисляет routing и revisions вручную.
- Нет silent stale acceptance, double advance, unbounded `REVISE` или полного reset при локальном upstream defect.
- `VERSION`, package, installer, prompts, docs и generated runtime согласованы.
- Финальный ZIP строится из того же дерева, которое опубликовано в GitHub.

<!-- 6.0.1-hardening:start -->
## 6.0.1 independent hardening

- Architecture preserved: four semantic agents, one TypeScript controller, three native tools.
- Runtime/code commit: `62b370be2456515f42e43555581bd7101ffaeeb2`.
- Controller, routing, NFR protocol, legacy migration, installer, build, and regression gates are executable and documented in `docs/RELEASE_GATES.md`.
- Cross-platform matrix has passed for the runtime commit.
- Final-tree packaging, final matrix confirmation, and draft PR publication are release-finalization gates; this section intentionally does not claim ROADMAP DONE before they run.
<!-- 6.0.1-hardening:end -->
