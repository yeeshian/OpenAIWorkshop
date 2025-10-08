# Human-in-the-Loop Patterns in Microsoft Agent Framework

Human-in-the-loop (HITL) workflows let an AI-driven system pause, route a decision to a human, and resume once guidance arrives. Microsoft Agent Framework provides first-class building blocks—`RequestInfoExecutor`, workflow checkpointing, and the agent wrapper APIs—to make these patterns reliable at production scale.

This guide explains how the pieces fit together, compares common designs, and walks through end-to-end implementations using the samples in this repository.

## Why Human-in-the-Loop?

Use HITL when you need:

- **Regulated approvals** (finance, healthcare, legal) where humans must sign off.
- **Quality control** for generated content, data extraction, or recommendations.
- **Escalation paths** for ambiguous outcomes where a human provides context the model lacks.
- **Guardrails** that keep LLMs aligned with brand voice, tone, or safety policies.

## Core Concepts

| Concept | Description | Key APIs |
| --- | --- | --- |
| `RequestInfoExecutor` | Special executor that surfaces requests to the outside world through function calls, then resumes execution when the response arrives. | `RequestInfoExecutor`, `RequestInfoMessage`, `RequestResponse` |
| Function call bridge | The workflow emits a function call (`WorkflowAgent.REQUEST_INFO_FUNCTION_NAME`) which the host application handles to collect human input. | `FunctionCallContent`, `FunctionResultContent` |
| Workflow checkpointing | Persist runtime state so workflows can pause indefinitely and resume after minutes, hours, or days. | `WorkflowBuilder.with_checkpointing`, `FileCheckpointStorage`, `RedisCheckpointStorage`, `CosmosDBCheckpointStorage` |
| Workflow agent wrapper | Exposes the workflow via the agent protocol so you can drive it with `agent.run()`/`run_stream()` and process function calls uniformly. | `workflow.as_agent()` |

## High-Level Architecture

```
┌──────────────┐    Function Call     ┌────────────────────┐
│  Workflow    │ ───────────────────▶ │ External Host/UI   │
│ (RequestInfo │                     │ (Chat UI, API, etc) │
│ Executor)    │ ◀─────────────────── │                    │
└────┬─────────┘    Function Result   └────────┬───────────┘
     │                                       │
     │ (Optional)                             │
     ▼                                       ▼
┌──────────────┐                       ┌──────────────┐
│ Checkpoint   │◀─────────────────────▶│ Persisted    │
│ Storage      │   save/resume state   │ Workflow     │
└──────────────┘                       └──────────────┘
```

1. An executor sends a `RequestInfoMessage` to `RequestInfoExecutor`.
2. The workflow emits a function call with the request payload and pauses.
3. Your application surfaces the request (e.g., UI prompt, email) and collects the human decision.
4. The decision returns as a function result, which `RequestInfoExecutor` converts into a `RequestResponse`.
5. The workflow resumes where it left off.
6. If checkpointing is enabled, the workflow state is saved before and after the pause.

## Pattern 1: Synchronous Escalation

Best for prototypes or workflows where humans respond immediately.

**Sample:** `python/samples/getting_started/workflows/agents/workflow_as_agent_human_in_the_loop_azure.py`

### Key Steps

1. **Define the request message**

   ```python
   @dataclass
   class HumanReviewRequest(RequestInfoMessage):
       agent_request: ReviewRequest | None = None
   ```

2. **Route to `RequestInfoExecutor`**

   ```python
   await ctx.send_message(
       HumanReviewRequest(agent_request=request),
       target_id=request_info_executor.id,
   )
   ```

3. **Detect the function call** in the agent response and obtain the arguments via `WorkflowAgent.RequestInfoFunctionArgs`.

4. **Return the human response** as a `FunctionResultContent`, then call `agent.run(...)` again with a tool-role message.

### Pros & Cons

| Pros | Cons |
| --- | --- |
| Simple to reason about | Caller must stay connected while waiting |
| Minimal infrastructure | Not suitable for long delays |

## Pattern 2: Checkpointed Pause/Resume

Use this when responses may take minutes or days, or when you need resiliency across process restarts.

**Sample:** `python/samples/getting_started/workflows/checkpoint/checkpoint_with_human_in_the_loop.py`

### Implementation Overview

1. Enable checkpointing:

   ```python
   storage = FileCheckpointStorage(storage_path="./checkpoints")
   workflow = (
       WorkflowBuilder()
       # ... add executors and edges ...
       .with_checkpointing(checkpoint_storage=storage)
       .build()
   )
   agent = workflow.as_agent()
   ```

2. Start the workflow with a `checkpoint_id` (often a session or job ID):

   ```python
   checkpoint_id = "workflow-123"
   response = await agent.run(user_prompt, checkpoint_id=checkpoint_id)
   ```

3. Detect a pause by inspecting `FunctionCallContent` or the returned `WorkflowStatusEvent`.

4. Persist the outstanding request and notify the reviewer (email, Teams, ticketing system, etc.).

5. When the decision arrives, resume from the saved checkpoint:

   ```python
   human_response = FunctionResultContent(call_id=call_id, result=decision)
   response = await agent.run(
       ChatMessage(role=Role.TOOL, contents=[human_response]),
       checkpoint_id=checkpoint_id,
   )
   ```

   Alternatively, call `workflow.run_stream_from_checkpoint(...)` if you are driving the workflow directly rather than through `WorkflowAgent`.

### Storage Options

| Development | Production |
| --- | --- |
| `FileCheckpointStorage` | `RedisCheckpointStorage`, `CosmosDBCheckpointStorage` |

**Tip:** The sample demonstrates `RequestInfoExecutor.pending_requests_from_checkpoint(...)` which makes it easy to pre-supply human answers before resuming a checkpoint.

## Pattern 3: Event-Driven Architectures

For high-scale systems, place a message bus between the workflow and reviewers. The workflow publishes a “human approval needed” event, then sleeps with its state checkpointed. A worker or API endpoint collects the human decision later and calls `agent.run(... checkpoint_id=...)` to resume.

### Suggested Flow

1. Workflow publishes `{session_id, function_call_payload}` to a queue or Event Grid topic.
2. Notification service surfaces the request to humans.
3. Reviewer submits a decision through a web app or chat bot.
4. API handler constructs `FunctionResultContent` and resumes the workflow using the stored `session_id`.

This pattern avoids holding open network connections and makes it easy to scale out workflow runners and human-facing services independently.

## Putting It Together: End-to-End Example

```python
async def start_workflow(session_id: str, prompt: str):
    response = await agent.run(prompt, checkpoint_id=session_id)
    call = extract_request_info_call(response)
    if call:
        save_pending_request(session_id, call)
        notify_manager(session_id, call)
        return {"status": "pending", "session_id": session_id}
    return {"status": "completed", "result": read_output(response)}


async def resume_workflow(session_id: str, decision: ReviewResponse):
    call = load_pending_request(session_id)
    result = FunctionResultContent(call_id=call.call_id, result=decision)
    response = await agent.run(
        ChatMessage(role=Role.TOOL, contents=[result]),
        checkpoint_id=session_id,
    )
    return {"status": "resumed", "result": read_output(response)}
```

## Best Practices

- **Keep request payloads serializable.** Use dataclasses with primitive types so checkpoints can persist them reliably.
- **Include identifiers.** Store request IDs, user IDs, and draft previews to help humans decide quickly.
- **Set checkpoint TTLs.** Clean up abandoned sessions using the storage provider’s expiry features.
- **Audit every decision.** Persist the human response alongside the workflow output for compliance.
- **Stress-test resume logic.** Simulate process crashes by stopping and restarting the workflow runner before providing the human response.
- **Secure the channel.** Ensure that only authorized users can approve or reject requests.

## Troubleshooting

| Symptom | Likely Cause | Fix |
| --- | --- | --- |
| `ValueError: Human review request payload must be a mapping` | The function call payload was parsed without respecting the custom dataclass type. | Access `request.data` as the dataclass (`HumanReviewRequest`) and reference its fields directly. |
| Workflow does not pause | Request was not routed through `RequestInfoExecutor`. | Ensure `ctx.send_message(..., target_id=request_info_executor.id)` is used. |
| Workflow resumes but re-prompts for the same request | Decision was not supplied or `call_id` mismatch. | Pass the same `call_id` from the original `FunctionCallContent` when constructing `FunctionResultContent`. |
| No checkpoints saved | `WorkflowBuilder.with_checkpointing(...)` was not called or checkpoint storage misconfigured. | Configure storage and provide a unique `checkpoint_id` when running the workflow/agent. |

## Additional Resources

- **Samples**
  - [`workflow_as_agent_human_in_the_loop_azure.py`](../python/samples/getting_started/workflows/agents/workflow_as_agent_human_in_the_loop_azure.py)
  - [`checkpoint_with_human_in_the_loop.py`](../python/samples/getting_started/workflows/checkpoint/checkpoint_with_human_in_the_loop.py)
- **API References**
  - [`RequestInfoExecutor`](../python/packages/core/agent_framework/_workflows/_request_info_executor.py)
  - [`WorkflowBuilder`](../python/packages/core/agent_framework/_workflows/_workflow.py)
  - [`WorkflowAgent`](../python/packages/core/agent_framework/_workflows/_workflow_agent.py)

By combining `RequestInfoExecutor` with checkpoint-aware workflows, you can build resilient human-in-the-loop systems that pause safely, resume on demand, and provide a clear audit trail for every decision.
