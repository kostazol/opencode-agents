from __future__ import annotations

import json
from pathlib import Path
import sys

from common import npm_exec, run, write_files


PACKAGE_JSON = {
    "name": "opencode-agents",
    "version": "6.0.1",
    "private": True,
    "type": "module",
    "engines": {"node": ">=20 <23"},
    "scripts": {
        "clean": "node scripts/clean.mjs",
        "build": "npm run clean && tsc -p tsconfig.json && tsc -p tsconfig.tools.json",
        "typecheck": "tsc -p tsconfig.json --noEmit && tsc -p tsconfig.tools.json --noEmit",
        "test:node": "node scripts/run-node-tests.mjs",
        "test:python": "node scripts/run-python-tests.mjs",
        "test": "npm run build && npm run typecheck && npm run test:node && npm run test:python",
        "check:generated": "node scripts/check-generated.mjs",
        "test:release": "npm ci && npm run check:generated && npm test && npm run check:generated"
    },
    "devDependencies": {},
}


TSCONFIG = r'''
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "rootDir": "src",
    "outDir": "runtime",
    "declaration": true,
    "declarationMap": false,
    "sourceMap": false,
    "strict": true,
    "noImplicitAny": true,
    "noImplicitOverride": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedIndexedAccess": false,
    "exactOptionalPropertyTypes": false,
    "forceConsistentCasingInFileNames": true,
    "skipLibCheck": false,
    "types": ["node"]
  },
  "include": ["src/**/*.ts"]
}
'''


TOOLS_TSCONFIG = r'''
{
  "extends": "./tsconfig.json",
  "compilerOptions": {
    "rootDir": ".",
    "outDir": "dist-tools",
    "declaration": false,
    "sourceMap": false,
    "noEmit": false
  },
  "include": ["tools/**/*.ts"]
}
'''


CLEAN = r'''
import { readdir, rm } from "node:fs/promises"
import path from "node:path"

async function removeGenerated(root) {
  let entries = []
  try { entries = await readdir(root, { withFileTypes: true }) } catch (error) { if (error.code === "ENOENT") return; throw error }
  for (const entry of entries) {
    const candidate = path.join(root, entry.name)
    if (entry.isDirectory()) await removeGenerated(candidate)
    else if (entry.name.endsWith(".js") || entry.name.endsWith(".d.ts")) await rm(candidate, { force: true })
  }
}

await removeGenerated("runtime")
await rm("dist-tools", { recursive: true, force: true })
'''


RUN_NODE = r'''
import { readdir } from "node:fs/promises"
import path from "node:path"
import { spawnSync } from "node:child_process"

async function collect(root) {
  const result = []
  for (const entry of await readdir(root, { withFileTypes: true })) {
    const candidate = path.join(root, entry.name)
    if (entry.isDirectory()) result.push(...await collect(candidate))
    else if (entry.name.endsWith(".test.mjs")) result.push(candidate)
  }
  return result
}

const tests = (await collect("tests-ts")).sort()
if (!tests.length) throw new Error("no Node regression tests found")
const processResult = spawnSync(process.execPath, ["--test", ...tests], { stdio: "inherit" })
process.exit(processResult.status ?? 1)
'''


RUN_PYTHON = r'''
import { spawnSync } from "node:child_process"

const candidates = process.platform === "win32"
  ? [["python", []], ["py", ["-3"]]]
  : [["python3", []], ["python", []]]
let found = false
for (const [command, prefix] of candidates) {
  const probe = spawnSync(command, [...prefix, "--version"], { stdio: "ignore" })
  if (probe.error?.code === "ENOENT") continue
  found = true
  const result = spawnSync(command, [...prefix, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"], { stdio: "inherit" })
  process.exit(result.status ?? 1)
}
if (!found) throw new Error("Python 3 executable was not found")
'''


CHECK_GENERATED = r'''
import { mkdtemp, readdir, readFile, rm } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import { spawnSync } from "node:child_process"

async function files(root) {
  const result = new Map()
  async function walk(directory) {
    let entries = []
    try { entries = await readdir(directory, { withFileTypes: true }) } catch (error) { if (error.code === "ENOENT") return; throw error }
    for (const entry of entries) {
      const candidate = path.join(directory, entry.name)
      if (entry.isDirectory()) await walk(candidate)
      else if (entry.name.endsWith(".js") || entry.name.endsWith(".d.ts")) result.set(path.relative(root, candidate).replaceAll(path.sep, "/"), await readFile(candidate))
    }
  }
  await walk(root)
  return result
}

const temporary = await mkdtemp(path.join(os.tmpdir(), "opencode-agents-generated-"))
try {
  const out = path.join(temporary, "runtime")
  const tsc = path.join("node_modules", ".bin", process.platform === "win32" ? "tsc.cmd" : "tsc")
  const compiled = spawnSync(tsc, ["-p", "tsconfig.json", "--outDir", out, "--declarationDir", out], { stdio: "inherit" })
  if (compiled.status !== 0) process.exit(compiled.status ?? 1)
  const expected = await files(out)
  const actual = await files("runtime")
  const names = [...new Set([...expected.keys(), ...actual.keys()])].sort()
  const drift = names.filter((name) => !expected.has(name) || !actual.has(name) || !expected.get(name).equals(actual.get(name)))
  if (drift.length) {
    console.error("generated runtime drift:")
    for (const name of drift) console.error(`- ${name}`)
    process.exit(1)
  }
  console.log(`generated runtime matches ${expected.size} compiled files`)
} finally {
  await rm(temporary, { recursive: true, force: true })
}
'''


CI = r'''
name: release-gates

on:
  push:
    branches:
      - agent/6.0.1-independent-hardening
  pull_request:
    branches:
      - main
  workflow_dispatch:

permissions:
  contents: read

jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        node: [20, 22]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node }}
          cache: npm
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install exact dependency graph
        run: npm ci
      - name: Verify committed generated runtime before build
        run: npm run check:generated
      - name: Typecheck, build, and execute regression baseline
        run: npm test
      - name: Verify generated runtime remains clean
        run: npm run check:generated
      - name: Reject generated drift in Git tree
        run: git diff --exit-code -- runtime package.json package-lock.json
'''


NPMRC = r'''
save-exact=true
engine-strict=true
fund=false
audit=false
'''


def fix_sources(root: Path) -> list[str]:
    changed: dict[str, str] = {}

    analysis_path = root / "src/analysis.ts"
    analysis = analysis_path.read_text(encoding="utf-8")
    broken = 'risks: strings(item.risks, `${field}.risks\\", false),'
    if broken in analysis:
        analysis = analysis.replace(broken, 'risks: strings(item.risks, `${field}.risks`, false),')
    broken2 = 'risks: strings(item.risks, `${field}.risks", false),'
    if broken2 in analysis:
        analysis = analysis.replace(broken2, 'risks: strings(item.risks, `${field}.risks`, false),')
    changed["src/analysis.ts"] = analysis

    state_path = root / "src/state.ts"
    state = state_path.read_text(encoding="utf-8")
    state = state.replace(
        'new Set(["blocked", "ready", "waiting_reopen_approval"]).has(resume)',
        'new Set(["blocked", "waiting_reopen_approval"]).has(resume)',
    )
    changed["src/state.ts"] = state

    events_path = root / "src/events.ts"
    events = events_path.read_text(encoding="utf-8")
    events = events.replace(
        '  state.status = "blocked"\n  state.current_stage = null\n  state.blocker =',
        '  state.status = "blocked"\n  state.blocker =',
    )
    changed["src/events.ts"] = events

    installer_path = root / "opencode-agents.py"
    installer = installer_path.read_text(encoding="utf-8")
    if "import sys\n" not in installer:
        installer = installer.replace("import stat\n", "import stat\nimport sys\n", 1)
    installer = installer.replace("from dataclasses import dataclass\n", "")
    installer = installer.replace(
        '@dataclass(frozen=True)\nclass FileRecord:\n    path: str\n    sha256: str\n    size: int\n',
        'class FileRecord:\n    def __init__(self, path: str, sha256: str, size: int) -> None:\n        self.path = path\n        self.sha256 = sha256\n        self.size = size\n',
    )
    changed["opencode-agents.py"] = installer
    return write_files(root, changed)


def apply(root: Path, log: Path) -> list[str]:
    changed = fix_sources(root)
    changed += write_files(root, {
        "package.json": json.dumps(PACKAGE_JSON, indent=2, ensure_ascii=False) + "\n",
        "tsconfig.json": TSCONFIG,
        "tsconfig.tools.json": TOOLS_TSCONFIG,
        ".npmrc": NPMRC,
        "scripts/clean.mjs": CLEAN,
        "scripts/run-node-tests.mjs": RUN_NODE,
        "scripts/run-python-tests.mjs": RUN_PYTHON,
        "scripts/check-generated.mjs": CHECK_GENERATED,
        ".github/workflows/release-gates.yml": CI,
    })

    for relative in ["types/node-shims.d.ts", "types/opencode-plugin.d.ts"]:
        candidate = root / relative
        if candidate.exists():
            candidate.unlink()
            changed.append(relative)

    npm_exec(root, ["install", "--save-dev", "--save-exact", "typescript@5", "@types/node@22", "@opencode-ai/plugin@latest"], log=log)
    npm_exec(root, ["ci"], log=log)
    npm_exec(root, ["run", "build"], log=log)
    npm_exec(root, ["run", "typecheck"], log=log)
    npm_exec(root, ["run", "check:generated"], log=log)
    npm_exec(root, ["run", "test:node"], log=log)
    npm_exec(root, ["run", "test:python"], log=log)
    run(["git", "diff", "--check"], cwd=root, log=log)
    return changed + ["package-lock.json", "runtime", "dist-tools"]


if __name__ == "__main__":
    repository = Path(sys.argv[1]).resolve()
    log = Path(sys.argv[2]).resolve()
    print("\n".join(apply(repository, log)))
