# OpenCode Agents 6.0.1

Stable 6.0.1 is the independent-hardening release of the existing TypeScript architecture. It keeps four semantic agents, one TypeScript controller, and three native OpenCode tools; it does not add a Python controller, generic workflow framework, service, or database.

## Immutable runtime source

Installer and package tree are pinned to `62b370be2456515f42e43555581bd7101ffaeeb2`. Documentation gates are in `be156bd707ab76ba0a8db1d18ddcda28610251ef` and `docs/RELEASE_GATES.md`.

## Executed gates

- exact dependency install: `npm ci`;
- full controller, native-tool, and installer baseline: `npm test`;
- actual plugin API: `npm run typecheck`;
- generated runtime: `npm run check:generated`;
- complete artifact-producing store journey;
- stale input/output, immutable remote installer, guarded retirement, legacy resume, NFR adversarial, impossible-state, symlink, and journal conflict/recovery tests;
- Linux, Windows, and macOS on Node 22 and 24.

The exact final-tree ZIP and SHA-256 are produced after this commit and stored on the dedicated artifact branch, so the archive cannot recursively alter the release tree it represents.
