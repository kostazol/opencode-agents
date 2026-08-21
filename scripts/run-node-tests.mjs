
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
