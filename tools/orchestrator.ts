import { spawn } from "node:child_process"
import { fileURLToPath } from "node:url"
import { tool, type ToolContext } from "@opencode-ai/plugin"

const requestSchema = tool.schema.string().min(1).max(80).regex(/^[a-z0-9][a-z0-9-]{0,79}$/)
const revisionSchema = tool.schema.number().int().nonnegative().optional()
const runtime = fileURLToPath(new URL("../runtime/orchestrator.py", import.meta.url))

function pythonCommand(): string {
  return process.env.OPENCODE_AGENTS_PYTHON ?? (process.platform === "win32" ? "python" : "python3")
}

async function invoke(
  operation: "next" | "apply" | "validate",
  request: string,
  input: Record<string, unknown>,
  context: ToolContext,
): Promise<string> {
  return await new Promise((resolve) => {
    const child = spawn(
      pythonCommand(),
      [runtime, operation, "--directory", context.directory, "--request", request],
      { cwd: context.directory, shell: false, stdio: ["pipe", "pipe", "pipe"] },
    )
    const output: Buffer[] = []
    const errors: Buffer[] = []
    child.stdout.on("data", (chunk) => output.push(Buffer.from(chunk)))
    child.stderr.on("data", (chunk) => errors.push(Buffer.from(chunk)))
    const abort = () => child.kill()
    context.abort.addEventListener("abort", abort, { once: true })
    child.on("error", (error) => resolve(JSON.stringify({ ok: false, error: { type: "runtime", message: error.message } }, null, 2)))
    child.on("close", () => {
      context.abort.removeEventListener("abort", abort)
      const text = Buffer.concat(output).toString("utf8").trim()
      if (text) return resolve(text)
      resolve(JSON.stringify({ ok: false, error: { type: "runtime", message: Buffer.concat(errors).toString("utf8").trim() || "Python controller produced no output" } }, null, 2))
    })
    child.stdin.end(JSON.stringify(input))
  })
}

export const next = tool({
  description: "Reserve and return the single deterministic next planning action.",
  args: { request: requestSchema, expected_state_revision: revisionSchema },
  execute: (args, context) => invoke("next", args.request, { expected_state_revision: args.expected_state_revision }, context),
})

export const apply = tool({
  description: "Apply one typed result or user decision to the pending planning transition.",
  args: {
    request: requestSchema,
    transition_id: tool.schema.string().min(1),
    event_type: tool.schema.string().min(1),
    payload_json: tool.schema.string().min(2),
    expected_state_revision: revisionSchema,
  },
  execute(args, context) {
    let payload: unknown
    try {
      payload = JSON.parse(args.payload_json)
    } catch (error) {
      return Promise.resolve(JSON.stringify({ ok: false, error: { type: "protocol", field: "payload_json", message: error instanceof Error ? error.message : String(error) } }, null, 2))
    }
    return invoke("apply", args.request, {
      transition_id: args.transition_id,
      event_type: args.event_type,
      payload,
      expected_state_revision: args.expected_state_revision,
    }, context)
  },
})

export const validate = tool({
  description: "Validate durable planning state and artifacts without advancing the workflow.",
  args: { request: requestSchema },
  execute: (args, context) => invoke("validate", args.request, {}, context),
})
