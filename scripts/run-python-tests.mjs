
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
