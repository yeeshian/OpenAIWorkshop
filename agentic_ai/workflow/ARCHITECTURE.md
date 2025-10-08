# Workflow Architecture

The Agent Framework workflow system is a **directed-graph execution engine** modeled after Google's [Pregel](https://research.google/pubs/pub36726/) distributed graph computation model, adapted for orchestrating AI agents, tools, and arbitrary compute steps in a type-safe, checkpointable, and observable manner.

## Core abstractions

| Component | Purpose |
|-----------|---------|
| **Executor** (`_executor.py`) | A unit of work with typed handlers that process messages. Can be a class (subclassing `Executor`) or a decorated function (`@executor`). Executors define what input types they accept and what they emit. |
| **Edge / EdgeGroup** (`_edge.py`) | Defines how messages flow between executors. Supports single, fan-out (1→N), fan-in (N→1 aggregation), and switch/case routing patterns. |
| **WorkflowContext** (`_workflow_context.py`) | Injected into each executor handler; provides `send_message()`, `yield_output()`, state persistence APIs (`set_state`, `get_state`, `set_shared_state`). Enforces type safety through generic parameters. |
| **Runner** (`_runner.py`) | Orchestrates execution in synchronized **supersteps**: delivers messages, invokes executors concurrently, drains events, creates checkpoints. Runs until the graph becomes idle (no pending messages). |
| **Workflow** (`_workflow.py`) | The user-facing API that wraps the Runner and provides entry points (`run()`, `run_stream()`, `run_from_checkpoint()`). Built via `WorkflowBuilder`. |

---

## Execution model: Pregel-style supersteps

### 1. Initialization phase

- User calls `workflow.run(initial_message)`.
- The starting executor receives the message and runs its handler.
- Handler can emit messages via `ctx.send_message()` or final outputs via `ctx.yield_output()`.
- All emitted messages are queued in the `RunnerContext`.

### 2. Superstep iteration

- The Runner **drains** all pending messages from the queue.
- Messages are routed through `EdgeRunner` implementations based on edge topology:
  - **SingleEdgeRunner**: Delivers to one target if type and condition match.
  - **FanOutEdgeRunner**: Broadcasts to multiple targets or selects a subset dynamically.
  - **FanInEdgeRunner**: Buffers messages from multiple sources; delivers aggregated list when all sources have sent.
  - **SwitchCaseEdgeRunner**: Evaluates predicates and routes to the first matching case.
- All deliverable messages invoke their target executors **concurrently** (via `asyncio.gather`).
- Each executor processes its messages and may emit new messages or outputs.
- At the end of the superstep:
  - Events (outputs, custom events) are streamed to the caller.
  - A checkpoint is optionally created (if `CheckpointStorage` is configured).
  - The Runner checks if new messages are pending; if yes, starts the next superstep.

### 3. Convergence / termination

- The workflow runs until **no messages remain** or the **max iteration limit** is hit.
- Final state is emitted as a `WorkflowStatusEvent`:
  - `IDLE`: Clean completion, no pending requests.
  - `IDLE_WITH_PENDING_REQUESTS`: Waiting for external input (via `RequestInfoExecutor`).
  - `FAILED`: An executor raised an exception.

---

## Message routing and type safety

- Each executor declares **input types** via handler parameter annotations (`text: str`, `data: MyModel`, etc.).
- `WorkflowContext[T_Out]` declares the **output message type** the executor can emit.
- `WorkflowContext[T_Out, T_W_Out]` adds workflow-level output types (for `yield_output`).
- Edge runners use `executor.can_handle(message_data)` to enforce type compatibility at runtime.
- Routing predicates (`edge.should_route(data)`) and selection functions (`selection_func(data, targets)`) allow dynamic control flow.

---

## State and persistence

| Layer | Mechanism |
|-------|-----------|
| **Executor-local state** | `ctx.set_state(key, value)` / `ctx.get_state(key)` stores per-executor JSON blobs in the `RunnerContext`. Executors can override `snapshot_state()` / `restore_state()` for custom serialization. |
| **Shared state** | `WorkflowContext.set_shared_state(key, value)` writes to a `SharedState` dictionary visible to all executors. Protected by an async lock to prevent race conditions. |
| **Checkpoints** | After each superstep, the Runner calls `_auto_snapshot_executor_states()`, then serializes: <br> - Pending messages per executor <br> - Shared state dictionary <br> - Executor state snapshots <br> - Iteration counter / metadata <br><br> `CheckpointStorage` (in-memory, file, Redis, Cosmos DB) persists `WorkflowCheckpoint` objects. |
| **Restoration** | `workflow.run_from_checkpoint(checkpoint_id)` rehydrates the full runner context, re-injects shared state, restores iteration count, and validates graph topology (via a hash of the executor/edge structure). |

Checkpoints are **delta-neutral**: the graph structure itself is not serialized, only the runtime state. You must rebuild the workflow with the same topology before restoring.

---

## Observability and tracing

- **OpenTelemetry integration**: The workflow creates a root span (`workflow_run`) that encompasses all supersteps. Each executor invocation and edge delivery gets nested spans.
- **Trace context propagation**: Messages carry `trace_contexts` and `source_span_ids` to link spans across async boundaries (following W3C Trace Context).
- **Event streaming**: The Runner emits `WorkflowEvent` subclasses:
  - `WorkflowStartedEvent`, `WorkflowStatusEvent` (lifecycle).
  - `WorkflowOutputEvent` (from `yield_output`).
  - `RequestInfoEvent` (external input requests).
  - Custom events via `ctx.add_event()`.
- Events are streamed live via `run_stream()` or collected in `WorkflowRunResult` for batch runs.

---

## Composition patterns

1. **Nested workflows**: `WorkflowExecutor` wraps a child workflow as an executor. When invoked, it runs the child to completion and processes outputs.
2. **Human-in-the-loop**: `RequestInfoExecutor` emits `RequestInfoEvent`, transitions the workflow to `IDLE_WITH_PENDING_REQUESTS`, and waits for external responses via `send_responses()`.
3. **Multi-agent teams**: `MagenticOrchestratorExecutor` (in `_magentic.py`) wraps multiple agents, manages broadcast/targeted communication, and snapshots each participant's conversation history.

---

## Key design decisions

- **Type-driven routing**: Edge runners and executors use Python type annotations to enforce contracts at runtime, providing early feedback for wiring errors.
- **Separation of data/control planes**: Executor invocations and message passing happen "under the hood"; only workflow-level events (outputs, requests) are exposed to callers. This keeps the event stream clean and hides internal coordination.
- **Checkpointing by convention**: Executors opt into persistence by implementing `snapshot_state()` or exposing a `state` attribute. The framework handles serialization (including Pydantic models and dataclasses) transparently.
- **Graph immutability**: Once built, workflows are immutable. This enables safe checkpoint restoration and parallel invocations (if you construct separate `Workflow` instances).
- **Concurrency within supersteps**: All deliverable messages in a superstep execute concurrently. This parallelizes work but requires shared state to be protected (via `SharedState`'s async lock).

---

## Validation and safety

- **Graph validation**: `validate_workflow_graph()` (in `_validation.py`) checks for unreachable executors, missing start nodes, and cycles (for non-cyclic workflows).
- **Concurrent execution guard**: The `Workflow` class prevents multiple `run()` calls on the same instance to avoid state corruption.
- **Max iterations**: Prevents infinite loops by bounding superstep counts (default 100, configurable).
- **Graph signature hashing**: Before restoring a checkpoint, the Runner compares a hash of the workflow topology to the checkpoint metadata to detect structural changes.

---

## Sample execution trace

```
User calls workflow.run("hello world")
  ↓
Workflow emits WorkflowStartedEvent, WorkflowStatusEvent(IN_PROGRESS)
  ↓
Executor "upper_case_executor" receives "hello world"
  → Handler: to_upper_case(text: str, ctx: WorkflowContext[str])
  → Calls ctx.send_message("HELLO WORLD")
  → Message queued
  ↓
Runner drains messages → SingleEdgeRunner delivers to "reverse_text_executor"
  ↓
Executor "reverse_text_executor" receives "HELLO WORLD"
  → Handler: reverse_text(text: str, ctx: WorkflowContext[Never, str])
  → Calls ctx.yield_output("DLROW OLLEH")
  → WorkflowOutputEvent emitted
  ↓
No more messages → Workflow emits WorkflowStatusEvent(IDLE)
  ↓
workflow.run() returns WorkflowRunResult([WorkflowOutputEvent("DLROW OLLEH"), ...])
```

---

## Additional references

- Full workflow builder API: `WorkflowBuilder` in `_workflow.py`.
- Edge runner implementations: `_edge_runner.py`.
- Checkpoint encoding: `_runner_context.py` (`_encode_checkpoint_value`, `_decode_checkpoint_value`).
- Magentic multi-agent orchestration: `_magentic.py`.

This architecture balances **expressiveness** (flexible routing, composition), **type safety** (runtime contract enforcement), **observability** (OpenTelemetry spans, event streams), and **durability** (checkpointing for long-running workflows), making it suitable for both simple pipelines and complex multi-agent systems.
