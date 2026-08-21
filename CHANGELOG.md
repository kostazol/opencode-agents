# Changelog

## 6.0.0 — 2026-08-20

### Added

- strict `analysis.json` protocol with requirement, NFR, decision, contract, acceptance, scenario and stage identities;
- reciprocal traceability and producer/consumer dependency validation;
- deterministic `orchestrator_next`, `orchestrator_apply`, `orchestrator_validate` tools;
- durable state, journal, atomic transaction, request lock and crash recovery;
- optimistic revisions and idempotent event replay;
- evidence-content-based convergence and bounded no-progress escalation;
- controlled reopening of the minimal affected dependency/contract subgraph;
- independent discovery review and human-readable stage review;
- capability-first agent permissions.

### Changed

- production controller moved from the completed Python 6.0 snapshot to a single Node-compatible TypeScript runtime;
- primary prompt now follows the controller action loop instead of maintaining a manual transition table;
- `plan.md` is generated as a readable index rather than used as the machine state database;
- installer now deploys agents, native TypeScript tools and compiled JavaScript runtime.

### Removed

- Python production controller and TypeScript-to-Python subprocess bridge;
- duplicated workflow state-machine logic in prompts;
- command-by-command permission catalogs.

### Compatibility

- strict legacy `plan.md` migration is supported for the stable v5 subset;
- Python remains only for the installer and external black-box E2E harness.
