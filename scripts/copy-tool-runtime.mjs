
import { cp, mkdir, rm } from "node:fs/promises"

await rm("dist-tools/runtime", { recursive: true, force: true })
await mkdir("dist-tools", { recursive: true })
await cp("runtime", "dist-tools/runtime", { recursive: true, force: true })
