
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
