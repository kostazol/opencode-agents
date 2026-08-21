import { tool, type ToolContext } from "@opencode-ai/plugin"
import { ProtocolError, WorkflowStore, parseJsonStrict, type EventInput } from "../runtime/orchestrator.js"

const requestSchema = tool.schema.string().min(1).max(80).regex(/^[a-z0-9][a-z0-9-]{0,79}$/)
const revisionSchema = tool.schema.number().int().nonnegative().optional()

function response(value: unknown): string {
  return JSON.stringify(value, null, 2)
}

function failure(error: unknown): string {
  if (error instanceof ProtocolError) {
    return response({ ok: false, error: { type: "protocol", field: error.field, message: error.message, value: error.value } })
  }
  return response({ ok: false, error: { type: "runtime", message: error instanceof Error ? error.message : String(error) } })
}

async function withStore<T>(request: string, context: ToolContext, operation: (store: WorkflowStore) => Promise<T>): Promise<string> {
  try {
    return response({ ok: true, ...(await operation(new WorkflowStore(context.directory, request)) as object) })
  } catch (error) {
    return failure(error)
  }
}

export const next = tool({
  description: "Reserve and return the single deterministic next technical-analysis action.",
  args: { request: requestSchema, expected_state_revision: revisionSchema },
  execute: (args: { request: string; expected_state_revision?: number }, context: ToolContext) => withStore(args.request, context, async (store) => {
    const { state, action } = await store.reserve(args.expected_state_revision)
    return { state_revision: state.state_revision, status: state.status, action }
  }),
})

export const apply = tool({
  description: "Apply one typed agent result or user decision to the pending technical-analysis transition.",
  args: {
    request: requestSchema,
    transition_id: tool.schema.string().min(1),
    event_type: tool.schema.string().min(1),
    payload_json: tool.schema.string().min(2),
    expected_state_revision: revisionSchema,
  },
  execute: (args: { request: string; transition_id: string; event_type: string; payload_json: string; expected_state_revision?: number }, context: ToolContext) => withStore(args.request, context, async (store) => {
    let payload: unknown
    try {
      payload = parseJsonStrict(args.payload_json)
    } catch (error) {
      throw new ProtocolError("payload_json", "invalid JSON", error instanceof Error ? error.message : String(error))
    }
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new ProtocolError("payload_json", "root must be an object")
    const event: EventInput = { transition_id: args.transition_id, type: args.event_type, payload: payload as Record<string, unknown> }
    const { state, result } = await store.apply(event, args.expected_state_revision)
    return { state_revision: state.state_revision, status: state.status, result }
  }),
})

export const validate = tool({
  description: "Validate technical-analysis state and artifacts without advancing the workflow.",
  args: { request: requestSchema },
  execute: (args: { request: string }, context: ToolContext) => withStore(args.request, context, async (store) => ({ validation: await store.validate() })),
})
