
# OpenCode Agents 6.0.1 executable release gates

The release architecture is intentionally narrow: four semantic agents, one TypeScript controller, and three native OpenCode tools. There is no parallel Python controller, generic workflow engine, external service, or database.

A claim is accepted only when the corresponding executable gate passes:

| Gate | Executable evidence |
|---|---|
| Exact dependency graph | `npm ci` |
| Controller and installer regression baseline | `npm test` |
| Real OpenCode plugin API | `npm run typecheck`; no local `tool: any` shim |
| Generated runtime | `npm run check:generated` and clean `git diff -- runtime` |
| Complete store journey | `tests-ts/journey.test.mjs` creates analysis, discovery, technical, human, and review artifacts before COMPLETE |
| stale-input and stale-output rejection | `tests-ts/release-blockers.test.mjs` and `tests-ts/controller-hardening.test.mjs` |
| immutable remote install | `tests/test_installer_hardening.py` and `tests/test_installer_regression.py` use mocked commit/tree/blob responses |
| guarded retirement | installer regression covers known Python 6.0 and managed 5.x hashes with mandatory backup and customized-file preservation |
| legacy validate → next | `tests-ts/legacy-resume-hardening.test.mjs` verifies lossless backup and explicit discovery continuation |
| NFR adversarial protocol | `tests-ts/nfr-adversarial.test.mjs` rejects duplicate, contradictory, unowned, and unlinked categories |
| impossible-state matrix | `tests-ts/routing-state-hardening.test.mjs` rejects illegal status, stage, human, and pending combinations |
| symlink containment | `tests-ts/release-gates.test.mjs` and installer symlink tests |
| journal conflict and recovery | `tests-ts/release-gates.test.mjs` |
| Cross-platform support | `.github/workflows/release-gates.yml`: Linux, Windows, macOS × Node 22, 24 |

The independent blocker workflow remains part of the branch. `opencode debug config grep` is not release evidence and is not used as a substitute for native tool invocation.
