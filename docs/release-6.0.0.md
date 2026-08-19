# Release 6.0.0 — practical roadmap completion

This release completes the corrected practical roadmap for the planning orchestrator.

The implementation keeps semantic repository analysis in agents and moves only deterministic integrity concerns into code: versioned artifacts and migrations, legal transitions, revision checks, request locking, recoverable atomic writes, stale-result rejection, convergence detection, evidence traceability, dependency-aware reopening, and a minimal OpenCode tool adapter.

The default workflow deliberately avoids duplicate review passes and heavyweight orchestration infrastructure. Agents retain broad trusted local capabilities for repository search, builds, tests, scripts, logs and LSP; unknown tools fall back to an approval request.

Release gates are the repository's deterministic fast suite, safe full unittest discovery, Python compilation, migration and lifecycle tests, and Git diff validation. Live provider-dependent OpenCode scenarios remain a separate runtime gate when an authenticated runtime is available.
