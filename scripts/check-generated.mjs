
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
  const tsc = path.join("node_modules", "typescript", "bin", "tsc")
  const compiled = spawnSync(process.execPath, [tsc, "-p", "tsconfig.json", "--outDir", out, "--declarationDir", out], { stdio: "inherit" })
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
