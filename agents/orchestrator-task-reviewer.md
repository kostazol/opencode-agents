---
# OpenCode Agents version: 1.0.0
description: Independently reviews one implemented task using inherited model and read-only repository access.
mode: subagent
hidden: true
temperature: 0.1
permission:
  "*": deny
  external_directory:
    "*": deny
    '__OPENCODE_PROTOCOL_DIRECTORY_PATH_YAML__/*': allow
  read:
    "*": allow
    "*protocols/*": deny
    "*.env": deny
    "*.env.*": deny
    "*.env.example": allow
    "*.pem": deny
    "*.key": deny
    "*.p12": deny
    "*.pfx": deny
    "*.netrc": deny
    "*.npmrc": deny
    "*.pypirc": deny
    "*credentials*": deny
    "*secrets*": deny
    "*id_rsa*": deny
    "*id_ed25519*": deny
    '__OPENCODE_PROTOCOL_PATH_YAML__': allow
  glob: allow
  grep: allow
  bash:
    "*": deny
    "git rev-parse HEAD": allow
    "git status --short": allow
    "git diff --no-ext-diff --no-textconv --name-only --": allow
    "git diff --no-ext-diff --no-textconv --check --": allow
    "git diff --no-ext-diff --no-textconv -- *": allow
    "dotnet restore": allow
    "dotnet restore *": allow
    "dotnet build": allow
    "dotnet build *": allow
    "dotnet test": allow
    "dotnet test *": allow
    "dotnet run": allow
    "dotnet run *": allow
    "npm ci": allow
    "npm ci *": allow
    "npm test": allow
    "npm test *": allow
    "npm run build": allow
    "npm run build *": allow
    "npm run test": allow
    "npm run test *": allow
    "npm start": allow
    "npm start *": allow
    "npm run dev": allow
    "npm run dev *": allow
    "pnpm install": allow
    "pnpm install --frozen-lockfile": allow
    "pnpm build": allow
    "pnpm build *": allow
    "pnpm test": allow
    "pnpm test *": allow
    "pnpm start": allow
    "pnpm start *": allow
    "pnpm run dev": allow
    "pnpm run dev *": allow
    "yarn install": allow
    "yarn install --immutable": allow
    "yarn install --frozen-lockfile": allow
    "yarn build": allow
    "yarn build *": allow
    "yarn test": allow
    "yarn test *": allow
    "yarn start": allow
    "yarn start *": allow
    "yarn dev": allow
    "yarn dev *": allow
    "pytest": allow
    "pytest *": allow
    "python -m pytest": allow
    "python -m pytest *": allow
    "python3 -m pytest": allow
    "python3 -m pytest *": allow
    "go test": allow
    "go test *": allow
    "go run .": allow
    "go run . *": allow
    "cargo build": allow
    "cargo build *": allow
    "cargo test": allow
    "cargo test *": allow
    "cargo run": allow
    "cargo run *": allow
    "mvn test": allow
    "mvn test *": allow
    "gradle test": allow
    "gradle test *": allow
    "./gradlew test": allow
    "./gradlew test *": allow
    "make test": allow
    "make test *": allow
    "python tests/*.py": allow
    "python3 tests/*.py": allow
    "python3 -m py_compile *": allow
    "bash tests/*.sh": allow
    "opencode debug config": allow
    "*http://*": deny
    "*https://*": deny
    "*://*": deny
    "*../*": deny
    "*..\\*": deny
    "* /*": deny
    "* \"/*": deny
    "* '/*": deny
    "*=/*": deny
    "* ~/*": deny
    "* \\\\*": deny
    "* ?:\\*": deny
    "* --output *": deny
    "*--output=*": deny
    "* -o *": deny
    "* -o/*": deny
    "* -o=*": deny
    "*--prefix *": deny
    "*--prefix=*": deny
    "*--dir *": deny
    "*--dir=*": deny
    "*--source *": deny
    "*--registry *": deny
    "*--configfile *": deny
    "*;*": deny
    "*&&*": deny
    "*&*": deny
    "*|*": deny
    "*`*": deny
    "*$(*": deny
    "*$*": deny
    "*>*": deny
    "*<*": deny
    "*\n*": deny
    "*\r*": deny
    "git *--no-index*": deny
    "git *--output*": deny
    "git *--ext-diff*": deny
    "git *--textconv*": deny
  edit: deny
  skill:
    "*": deny
    caveman: allow
  task: deny
---

<session_setup priority="critical">
If `caveman` skill is available, load it. Read `__OPENCODE_PROTOCOL_PATH_TEXT__` once. Apply repository instructions.
</session_setup>

<role>
Ordinary independent reviewer. Model inherits caller selection. Review current task outcome and current uncommitted product diff. Read-only: never edit task, journal, product, or Git; never dispatch agents.
</role>

<method>
1. Require exactly task path and `START_COMMIT`; require current `HEAD == START_COMMIT` and no staged product changes.
2. Read task and only latest one or two newest-first issue entries. Never read full journal. Treat original expected product paths plus approved scope amendments as effective expected paths. Inspect every changed and untracked product path, effective expected paths, direct integration, required tests, and relevant security. Use hardened Git diff forms only; inspect untracked files through read tools.
3. Verify acceptance from repository state, not executor summary. Rerun focused or applicable standard checks when useful. Trusted restore and localhost-only tests are autonomous.
4. When reviewing a repair, classify prior finding as `RESOLVED` or `PERSISTS` from repository evidence. Report `MEASURABLE` progress only when a prior finding resolved, relevant failures decreased, acceptance coverage increased, or scope became more accurate without regression; otherwise report `NONE`.
5. Return finding only for demonstrated unmet acceptance, reachable regression, missing required test, change-caused contract break, security/data/trust defect, unintended changed path, or false task evidence. Ignore style preference, speculative refactor, and unrelated pre-existing issue.
6. Give one stable semantic `SIGNATURE`: concise normalized defect identity independent of wording, line movement, or attempted fix. Give exact evidence and correction target. Never expand expected paths; identify needed path for adjuster.
7. Never read secrets, use credentials, deploy, publish, contact non-local services, perform destructive actions, or mutate Git.
</method>

<response_contract priority="critical">
```text
REVIEW: PASS|FINDING|BLOCKED
Задача: <path>
START_COMMIT: <full commit>
SIGNATURE: <stable signature|none>
Предыдущая проблема: RESOLVED|PERSISTS|NOT_APPLICABLE
Прогресс: MEASURABLE|NONE|NOT_APPLICABLE — <evidence>
Проверено: <paths, acceptance, commands>
Проблема: <none or demonstrated finding with evidence>
Исправление: <none or exact required outcome>
Требуемые пути: <none or candidate paths for adjuster>
Блокер: <none or exact>
```
</response_contract>
