# OpenCode Agents 6.0.1

Stable 6.0.1 is the independently hardened release of the existing TypeScript architecture. It keeps four semantic agents, one TypeScript controller, and three native OpenCode tools; it does not add a Python controller, generic workflow framework, external service, or database.

## Published source

The final product branch is `agent/6.0.1-final-complete`, created from the audited `main` commit `5c897d5b3afba74940fcd188d2a2e13b21ebcc0b`.

- Installable runtime source: `62b370be2456515f42e43555581bd7101ffaeeb2`.
- Documentation gate source: `be156bd707ab76ba0a8db1d18ddcda28610251ef`.
- Verified release commit: `6faaa57c637712059b89e2e2ca62b196c3a361aa`.
- Permanent cross-platform CI commit: `efdee043ddf792c52f90454b1224f375d2e84389`.
- Machine-readable evidence: `release/6.0.1-gates.json`.

## Executed gates

- exact dependency installation: `npm ci`;
- full controller, native-tool, and installer baseline: `npm test`;
- actual OpenCode plugin API: `npm run typecheck`;
- deterministic generated runtime: `npm run check:generated`;
- complete artifact-producing store journey;
- stale-input and stale-output rejection;
- immutable remote installer and guarded retirement/update;
- lossless legacy resume, adversarial NFR validation, impossible-state checks, symlink containment, and journal conflict/recovery;
- fresh install, status, update, and mandatory backup;
- implementation and release-candidate matrices in run `32445239800`;
- final release matrix in run `32445714201`;
- Linux, Windows, and macOS on supported Node lines 22 and 24.

The package declares the exact supported Node range `^22.22.2 || ^24.15.0`, matching the current `@opencode-ai/plugin` dependency graph.

## Publication boundary

No separate artifact branch or prebuilt ZIP is claimed by this release metadata. GitHub can generate a source archive from any exact commit above. The product branch contains the complete source, generated runtime, tests, release evidence, and persistent CI workflow. No merge into `main` is performed by the finalization process.
