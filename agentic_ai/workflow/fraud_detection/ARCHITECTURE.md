# Fraud Detection Workflow - End-to-End System Architecture

## Overview

The Fraud Detection Workflow is a real-time, multi-agent AI system that analyzes suspicious activities, performs risk assessments, and enables human-in-the-loop decision-making. The system combines Azure OpenAI agents, Model Context Protocol (MCP) tools, and a React-based visualization interface.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER INTERFACE LAYER                            │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐    │
│  │                    React Frontend (Vite)                            │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │    │
│  │  │  Workflow    │  │   Analyst    │  │    Event Log             │  │    │
│  │  │  Control     │  │   Decision   │  │    (Real-time Stream)    │  │    │
│  │  │  Panel       │  │   Panel      │  │                          │  │    │
│  │  └──────────────┘  └──────────────┘  └──────────────────────────┘  │    │
│  │  ┌──────────────────────────────────────────────────────────────┐  │    │
│  │  │         React Flow - Workflow Visualization                   │  │    │
│  │  │  (Interactive DAG with real-time executor state updates)     │  │    │
│  │  └──────────────────────────────────────────────────────────────┘  │    │
│  └────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                        HTTP REST API │ WebSocket (Event Stream)             │
└────────────────────────────────────┼────────────────────────────────────────┘
                                     │
┌────────────────────────────────────┼────────────────────────────────────────┐
│                           APPLICATION LAYER                                 │
│                                    │                                         │
│  ┌────────────────────────────────▼────────────────────────────────────┐   │
│  │                    FastAPI Backend Server                            │   │
│  │  ┌──────────────────────────────────────────────────────────────┐   │   │
│  │  │  REST API Endpoints                                           │   │   │
│  │  │  • POST /api/workflow/start    - Start new workflow          │   │   │
│  │  │  • POST /api/workflow/decision - Submit analyst decision     │   │   │
│  │  │  • GET  /api/workflow/status   - Get workflow status         │   │   │
│  │  │  • GET  /api/alerts            - Get sample alerts           │   │   │
│  │  └──────────────────────────────────────────────────────────────┘   │   │
│  │  ┌──────────────────────────────────────────────────────────────┐   │   │
│  │  │  WebSocket Manager                                            │   │   │
│  │  │  • Real-time event broadcasting to all connected clients     │   │   │
│  │  │  • Connection lifecycle management                           │   │   │
│  │  └──────────────────────────────────────────────────────────────┘   │   │
│  │  ┌──────────────────────────────────────────────────────────────┐   │   │
│  │  │  Workflow Orchestration                                       │   │   │
│  │  │  • Workflow initialization & execution                        │   │   │
│  │  │  • Event streaming & processing                               │   │   │
│  │  │  • Human-in-the-loop coordination                            │   │   │
│  │  │  • Checkpoint management for resume capability               │   │   │
│  │  └──────────────────────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
└────────────────────────────────────┼────────────────────────────────────────┘
                                     │
┌────────────────────────────────────┼────────────────────────────────────────┐
│                          AGENT FRAMEWORK LAYER                              │
│                                    │                                         │
│  ┌────────────────────────────────▼────────────────────────────────────┐   │
│  │              Microsoft Agent Framework (agent-framework)             │   │
│  │  ┌──────────────────────────────────────────────────────────────┐   │   │
│  │  │  Workflow Engine                                              │   │   │
│  │  │  • DAG-based execution (Directed Acyclic Graph)              │   │   │
│  │  │  • State management & transitions                            │   │   │
│  │  │  • Checkpointing & resumability                              │   │   │
│  │  │  • Event emission (ExecutorInvoked, ExecutorCompleted, etc.) │   │   │
│  │  └──────────────────────────────────────────────────────────────┘   │   │
│  │  ┌──────────────────────────────────────────────────────────────┐   │   │
│  │  │  Executor Nodes (Agents)                                      │   │   │
│  │  │                                                                │   │   │
│  │  │  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐    │   │   │
│  │  │  │ Alert       │────▶│ Usage       │────▶│ Risk        │    │   │   │
│  │  │  │ Router      │     │ Pattern     │     │ Aggregator  │    │   │   │
│  │  │  └─────────────┘     └─────────────┘     └─────────────┘    │   │   │
│  │  │                                                                │   │   │
│  │  │  ┌─────────────┐     ┌─────────────┐            ┌──────┐    │   │   │
│  │  │  │ Location    │────▶│ Analyst     │───────────▶│ Auto │    │   │   │
│  │  │  │ Analysis    │     │ Review      │            │ Clear│    │   │   │
│  │  │  └─────────────┘     └─────────────┘            └──────┘    │   │   │
│  │  │                      (Human-in-Loop)                  │      │   │   │
│  │  │  ┌─────────────┐                                     │      │   │   │
│  │  │  │ Billing     │───────────────────────────┬─────────┘      │   │   │
│  │  │  │ Charge      │                           │                │   │   │
│  │  │  └─────────────┘                           ▼                │   │   │
│  │  │                                     ┌─────────────┐         │   │   │
│  │  │                                     │ Fraud       │         │   │   │
│  │  │                                     │ Action      │         │   │   │
│  │  │                                     └─────────────┘         │   │   │
│  │  │                                            │                │   │   │
│  │  │                                            ▼                │   │   │
│  │  │                                     ┌─────────────┐         │   │   │
│  │  │                                     │ Final       │         │   │   │
│  │  │                                     │ Notification│         │   │   │
│  │  │                                     └─────────────┘         │   │   │
│  │  └──────────────────────────────────────────────────────────────┘   │   │
│  │  ┌──────────────────────────────────────────────────────────────┐   │   │
│  │  │  RequestInfoExecutor (Human-in-the-Loop)                     │   │   │
│  │  │  • Pauses workflow execution                                 │   │   │
│  │  │  • Creates checkpoint with current state                     │   │   │
│  │  │  • Waits for external decision (analyst input)               │   │   │
│  │  │  • Resumes from checkpoint with decision                     │   │   │
│  │  └──────────────────────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
└────────────────────────────────────┼────────────────────────────────────────┘
                                     │
┌────────────────────────────────────┼────────────────────────────────────────┐
│                            AI & TOOLS LAYER                                 │
│                                    │                                         │
│  ┌────────────────────────────────▼────────────────────────────────────┐   │
│  │                     Azure OpenAI Service                             │   │
│  │  ┌──────────────────────────────────────────────────────────────┐   │   │
│  │  │  GPT-4 Model (Chat Completion)                                │   │   │
│  │  │  • Agent reasoning & decision-making                          │   │   │
│  │  │  • Natural language analysis                                  │   │   │
│  │  │  • Risk assessment generation                                 │   │   │
│  │  │  • Tool calling (function calling)                            │   │   │
│  │  └──────────────────────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                         │
│  ┌────────────────────────────────▼────────────────────────────────────┐   │
│  │         Model Context Protocol (MCP) Server                          │   │
│  │  ┌──────────────────────────────────────────────────────────────┐   │   │
│  │  │  FastMCP Server (HTTP/SSE)                                    │   │   │
│  │  │  • Exposes tools via standardized MCP protocol               │   │   │
│  │  │  • Handles tool invocation requests                          │   │   │
│  │  │  • Returns structured tool responses                         │   │   │
│  │  └──────────────────────────────────────────────────────────────┘   │   │
│  │  ┌──────────────────────────────────────────────────────────────┐   │   │
│  │  │  MCP Tools (Simulated Customer Service System)               │   │   │
│  │  │                                                                │   │   │
│  │  │  Customer Tools:                    Subscription Tools:       │   │   │
│  │  │  • get_all_customers()             • get_subscription_detail()│   │   │
│  │  │  • get_customer_detail()           • update_subscription()    │   │   │
│  │  │  • get_customer_orders()           • get_data_usage()         │   │   │
│  │  │  • unlock_account()                                           │   │   │
│  │  │                                                                │   │   │
│  │  │  Billing Tools:                    Support Tools:             │   │   │
│  │  │  • get_billing_summary()           • get_support_tickets()    │   │   │
│  │  │  • pay_invoice()                   • create_support_ticket()  │   │   │
│  │  │  • get_invoice_payments()                                     │   │   │
│  │  │                                                                │   │   │
│  │  │  Knowledge Base:                                              │   │   │
│  │  │  • search_knowledge_base() - Semantic search on policies     │   │   │
│  │  └──────────────────────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
┌────────────────────────────────────┼────────────────────────────────────────┐
│                          DATA & STORAGE LAYER                               │
│                                    │                                         │
│  ┌────────────────────────────────▼────────────────────────────────────┐   │
│  │  File-Based Storage                                                  │   │
│  │  ┌──────────────────────────────────────────────────────────────┐   │   │
│  │  │  Checkpoint Storage (./checkpoints/)                          │   │   │
│  │  │  • Workflow state snapshots                                   │   │   │
│  │  │  • Executor states at pause points                            │   │   │
│  │  │  • Pending request information                                │   │   │
│  │  │  • JSON format, UUID-based filenames                          │   │   │
│  │  └──────────────────────────────────────────────────────────────┘   │   │
│  │  ┌──────────────────────────────────────────────────────────────┐   │   │
│  │  │  Simulated Database (In-Memory)                               │   │   │
│  │  │  • Customer records                                           │   │   │
│  │  │  • Subscription data                                          │   │   │
│  │  │  • Invoice & payment history                                  │   │   │
│  │  │  • Support tickets                                            │   │   │
│  │  │  • Security logs                                              │   │   │
│  │  │  (Generated with Faker library for demo purposes)            │   │   │
│  │  └──────────────────────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Component Details

### 1. Frontend Layer (React + Vite)

**Technology Stack:**
- React 18+ with Hooks
- Material-UI (MUI) for components
- React Flow for workflow visualization
- WebSocket for real-time updates
- Vite for fast development builds

**Key Components:**

#### 1.1 Workflow Control Panel
- Displays available alerts (from backend)
- Alert selection dropdown with severity indicators
- "Start Workflow" button with loading state
- Shows active workflow status

#### 1.2 Analyst Decision Panel
- Appears when `decision_required` event received
- Shows risk assessment & AI analysis
- Dropdown for decision selection
- Text area for analyst notes
- "Submit Decision" button
- Compact layout optimized for visibility

#### 1.3 Workflow Graph Visualizer
- Interactive DAG visualization using React Flow
- Real-time executor state updates:
  - `idle` - Gray, not yet executed
  - `running` - Blue, currently executing
  - `completed` - Green, finished successfully
- Shows workflow structure and data flow
- Zoom, pan, and fit-to-screen controls

#### 1.4 Event Log Panel
- Real-time event stream display
- Color-coded event types
- Timestamps and executor tracking
- Auto-scroll to latest events
- Custom scrollbar with overflow handling
- Deduplication to prevent duplicate events

**Communication Protocols:**
- REST API for control operations (start workflow, submit decisions)
- WebSocket for event streaming (bi-directional, persistent connection)

---

### 2. Backend Layer (FastAPI)

**Technology Stack:**
- FastAPI for async REST API
- WebSocket support for real-time events
- Python 3.12+ with async/await
- Pydantic for data validation

**Key Modules:**

#### 2.1 REST API Endpoints

```python
POST /api/workflow/start
  • Input: SuspiciousActivityAlert
  • Creates workflow instance
  • Returns: { status, alert_id, message }
  • Spawns async workflow execution task

GET /api/alerts
  • Returns sample alerts for testing
  • Includes: alert_id, customer_id, alert_type, severity

POST /api/workflow/decision
  • Input: AnalystDecisionRequest
  • Resolves checkpoint for resume
  • Continues workflow with analyst's decision
  • Returns: { status, message }

GET /api/workflow/status/{alert_id}
  • Returns current workflow state
  • Includes: status, current_executor, events, pending_decision
```

#### 2.2 WebSocket Manager

**Connection Lifecycle:**
```python
1. Client connects → Accept WebSocket
2. Add to active_connections list
3. Stream events via broadcast()
4. On disconnect → Remove from list
```

**Event Broadcasting:**
- Sends JSON messages to all connected clients
- Handles disconnections gracefully
- No message queuing (real-time only)

**Event Types:**
- `workflow_initializing` - Setup in progress
- `workflow_started` - Execution beginning
- `executor_invoked` - Agent starting work
- `executor_completed` - Agent finished
- `decision_required` - Human input needed
- `workflow_completed` - All done
- `workflow_error` - Error occurred

#### 2.3 Workflow Orchestration

**Initialization Phase:**
```python
async def run_workflow(alert):
    1. Create workflow instance (pre-initialized resources)
    2. Send progress updates during setup
    3. Store workflow reference & instance
    4. Stream events via workflow.run_stream()
    5. Handle RequestInfoEvent → pause for analyst
```

**Resume Phase:**
```python
async def continue_workflow(alert_id, responses, checkpoint_id):
    1. Create NEW workflow instance
    2. Load checkpoint state
    3. Resume with workflow.run_stream_from_checkpoint()
    4. Provide analyst responses via responses dict
    5. Continue streaming events
```

**Checkpoint Resolution:**
- Retries up to 20 times with exponential backoff
- Checkpoints written AFTER superstep completion
- Maps request_id to checkpoint_id for resume

---

### 3. Agent Framework Layer

**Technology Stack:**
- Microsoft Agent Framework (`agent-framework`)
- DAG-based workflow engine
- State machine with transitions
- Checkpoint-based resumability

**Architecture Pattern:**
- **Directed Acyclic Graph (DAG)** for workflow structure
- **Executor Nodes** as individual agents/tasks
- **Edges** define dependencies and data flow
- **State Management** tracks execution progress

#### 3.1 Workflow Engine

**Execution Model:**
```
SuperStep Cycle:
1. Identify ready executors (dependencies met)
2. Execute executors in parallel
3. Collect outputs
4. Update shared state
5. Write checkpoint
6. Repeat until terminal state
```

**Event System:**
```python
- ExecutorInvokedEvent → Executor starting
- ExecutorCompletedEvent → Executor finished
- WorkflowStatusEvent → State transition
- RequestInfoEvent → Human input needed
- WorkflowOutputEvent → Final result
```

**Checkpointing:**
- Snapshot of entire workflow state
- Includes: executor states, shared state, pending requests
- File-based storage (JSON)
- Required for human-in-the-loop resume

#### 3.2 Executor Nodes (Agents)

**Executor Types:**

1. **AlertRouter** - Entry point, routes alert to analysis
2. **UsagePatternExecutor** - Analyzes data usage patterns
3. **LocationAnalysisExecutor** - Analyzes login locations
4. **BillingChargeExecutor** - Checks billing anomalies
5. **RiskAggregator** - Combines analyses, calculates risk score
6. **ReviewGateway** - Decides: auto-clear or analyst review
7. **AutoClear** - Handles low-risk alerts automatically
8. **RequestInfoExecutor (AnalystReview)** - Human-in-the-loop
9. **FraudAction** - Executes approved action (lock/refund/etc.)
10. **FinalNotification** - Logs completion and notifies

**Executor Pattern:**
```python
class CustomExecutor(Executor):
    async def execute(self, input_data, shared_state):
        # Access MCP tools
        tool_result = await self.mcp_tool.call_tool(...)
        
        # LLM reasoning
        response = await self.chat_client.chat(...)
        
        # Update state
        return output_data
```

#### 3.3 RequestInfoExecutor (Human-in-the-Loop)

**Mechanism:**
```python
1. Workflow reaches RequestInfoExecutor
2. Executor pauses (yields RequestInfoEvent)
3. Checkpoint created with pending request
4. Backend broadcasts decision_required to UI
5. Analyst provides decision via UI
6. Backend calls continue_workflow() with responses
7. Workflow resumes from checkpoint
8. RequestInfoExecutor returns analyst's response
9. Workflow continues execution
```

**Key Features:**
- Multiple pending requests supported
- Request ID mapping to checkpoint iteration
- Timeout handling (if needed)
- Request-response correlation

---

### 4. AI & Tools Layer

#### 4.1 Azure OpenAI Service

**Model Configuration:**
```python
Deployment: gpt-4 (or gpt-4-turbo)
Authentication: Azure CLI Credential (DefaultAzureCredential)
Endpoint: Azure OpenAI resource endpoint
Features: 
  - Chat completion
  - Function calling (tool calling)
  - JSON mode responses
```

**Usage Pattern:**
```python
# Agent makes decision
response = await chat_client.chat(
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ],
    tools=available_tools,
    temperature=0.7
)

# LLM decides to call a tool
tool_call = response.tool_calls[0]
tool_result = await mcp_tool.call_tool(tool_call.name, args)

# LLM processes result and continues
```

#### 4.2 Model Context Protocol (MCP) Server

**Purpose:**
- Standardized protocol for tool exposure
- HTTP-based (FastMCP implementation)
- Server-Sent Events (SSE) for streaming
- Used by agents to access customer data

**MCP Tool Integration:**
```python
# Backend initializes MCP client
mcp_tool = MCPStreamableHTTPTool(
    name="contoso_mcp",
    url="http://localhost:8000/mcp",
    headers={"Content-Type": "application/json"}
)

# Agent calls tool
result = await mcp_tool.call_tool(
    "get_customer_detail",
    {"params": {"customer_id": 123}}
)
```

**Tool Categories:**

**Customer Management:**
- `get_all_customers()` - List all customers
- `get_customer_detail(customer_id)` - Full customer profile
- `get_customer_orders(customer_id)` - Order history
- `unlock_account(customer_id)` - Unlock locked account

**Subscription Management:**
- `get_subscription_detail(subscription_id)` - Detailed subscription info
- `update_subscription(...)` - Modify subscription settings
- `get_data_usage(...)` - Data usage over time period

**Billing:**
- `get_billing_summary(customer_id)` - Current balance
- `pay_invoice(invoice_id, amount)` - Record payment
- `get_invoice_payments(invoice_id)` - Payment history

**Support & Security:**
- `get_support_tickets(customer_id)` - Ticket history
- `create_support_ticket(...)` - Create new ticket
- `get_security_logs(customer_id)` - Security events
- `search_knowledge_base(query)` - Semantic search policies

---

### 5. Data & Storage Layer

#### 5.1 Checkpoint Storage

**Format:**
```json
{
  "checkpoint_id": "uuid-here",
  "workflow_id": "workflow-uuid",
  "timestamp": "2025-10-09T10:30:00Z",
  "executor_states": {
    "executor_id": {
      "status": "completed",
      "output": {...}
    }
  },
  "shared_state": {
    "alert": {...},
    "risk_assessment": {...},
    "__pending_requests__": {
      "request-id": {...}
    }
  }
}
```

**Location:** `./checkpoints/`
**Cleanup:** Deleted after workflow completion

#### 5.2 Simulated Database

**Implementation:**
- In-memory Python data structures
- Generated with Faker library
- Realistic customer scenarios

**Data Models:**
```python
Customer:
  - customer_id, name, email, phone
  - account_status, loyalty_tier
  - created_at, last_login

Subscription:
  - subscription_id, customer_id, product_id
  - status, start_date, end_date
  - data_cap_gb, speed_tier
  - autopay_enabled, roaming_enabled

Invoice:
  - invoice_id, customer_id, subscription_id
  - amount, due_date, status
  - payments (linked)

SupportTicket:
  - ticket_id, customer_id, subscription_id
  - category, priority, status
  - subject, description
```

---

## Data Flow: Complete Request Cycle

### Scenario: High-Risk Alert with Analyst Review

```
┌──────────────────────────────────────────────────────────────────────────┐
│ PHASE 1: WORKFLOW START                                                  │
└──────────────────────────────────────────────────────────────────────────┘

1. User selects "ALERT-001" in UI
2. UI → POST /api/workflow/start { alert_id: "ALERT-001", ... }
3. Backend:
   - Creates workflow instance
   - Spawns run_workflow(alert) task
   - Returns immediately
4. Workflow Engine:
   - Broadcasts: workflow_initializing
   - Creates workflow graph
   - Broadcasts: workflow_started
5. UI updates: Workflow Control shows "Running..."

┌──────────────────────────────────────────────────────────────────────────┐
│ PHASE 2: AGENT ANALYSIS (Automatic)                                      │
└──────────────────────────────────────────────────────────────────────────┘

6. AlertRouter executes:
   - Broadcasts: executor_invoked (AlertRouter)
   - Routes alert to analysis executors
   - Broadcasts: executor_completed (AlertRouter)

7. Analysis Executors (parallel):
   A. UsagePatternExecutor:
      - Calls MCP: get_data_usage()
      - LLM analyzes: "500% spike is suspicious"
      - Broadcasts: executor_completed
   
   B. LocationAnalysisExecutor:
      - Calls MCP: get_security_logs()
      - LLM analyzes: "USA to Russia in 2 hours - impossible travel"
      - Broadcasts: executor_completed
   
   C. BillingChargeExecutor:
      - Calls MCP: get_billing_summary()
      - LLM analyzes: "No unusual charges"
      - Broadcasts: executor_completed

8. RiskAggregator executes:
   - Combines all analysis results
   - Calculates overall_risk_score: 0.88
   - Determines risk_level: "critical"
   - Recommends: "lock_account" & "refund_charges"
   - Broadcasts: executor_completed

9. ReviewGateway executes:
   - Evaluates: risk_score >= 0.6 → needs review
   - Routes to: analyst_review (not auto_clear)
   - Broadcasts: executor_completed

┌──────────────────────────────────────────────────────────────────────────┐
│ PHASE 3: HUMAN-IN-THE-LOOP (Pause & Wait)                                │
└──────────────────────────────────────────────────────────────────────────┘

10. AnalystReview (RequestInfoExecutor) executes:
    - Yields RequestInfoEvent
    - Workflow pauses
    - Checkpoint written to disk

11. Backend processes RequestInfoEvent:
    - Resolves checkpoint (retry with backoff)
    - Stores pending_decisions[alert_id]
    - Broadcasts: decision_required
    - WebSocket → UI

12. UI receives decision_required:
    - Displays Analyst Decision Panel
    - Shows: risk score, analysis, recommended action
    - Workflow graph: "analyst_review" node shows "running"

13. Analyst makes decision:
    - Selects: "Lock Account & Refund"
    - Adds notes: "Confirmed fraud - Russia login"
    - Clicks "Submit Decision"

14. UI → POST /api/workflow/decision
    {
      request_id: "req-123",
      approved_action: "both",
      analyst_notes: "Confirmed fraud..."
    }

┌──────────────────────────────────────────────────────────────────────────┐
│ PHASE 4: WORKFLOW RESUME                                                 │
└──────────────────────────────────────────────────────────────────────────┘

15. Backend continue_workflow():
    - Creates NEW workflow instance
    - Loads checkpoint from disk
    - Calls: workflow.run_stream_from_checkpoint(
        checkpoint_id,
        responses={req_id: AnalystDecision(...)}
      )

16. Workflow Engine:
    - Restores state from checkpoint
    - Resumes at analyst_review executor
    - RequestInfoExecutor returns analyst's decision
    - Broadcasts: executor_completed (analyst_review)

17. FraudAction executes:
    - Input: approved_action = "both"
    - Calls MCP: update_subscription(status="locked")
    - Calls MCP: pay_invoice(refund_amount)
    - Broadcasts: executor_completed

18. FinalNotification executes:
    - Calls MCP: create_support_ticket(...)
    - Logs: "Alert ALERT-001 resolved - account locked & refunded"
    - Broadcasts: executor_completed

19. Workflow completes:
    - Broadcasts: workflow_completed
    - Cleanup checkpoints
    - UI updates: All nodes green, workflow done

┌──────────────────────────────────────────────────────────────────────────┐
│ PHASE 5: UI UPDATE CYCLE (Throughout)                                    │
└──────────────────────────────────────────────────────────────────────────┘

WebSocket events → UI state updates:

• executor_invoked → Node color: blue (running)
• executor_completed → Node color: green (completed)
• decision_required → Show Analyst Decision Panel
• workflow_completed → Reset UI, show success

Event Log displays all events in real-time with timestamps
```

---

## Key Design Patterns

### 1. Event-Driven Architecture
- **Pattern:** Observer pattern via WebSocket
- **Benefit:** Real-time UI updates without polling
- **Implementation:** ConnectionManager broadcasts to all clients

### 2. Checkpoint-Resume Pattern
- **Pattern:** Memento pattern for workflow state
- **Benefit:** Enable human-in-the-loop without blocking
- **Implementation:** FileCheckpointStorage with JSON serialization

### 3. Agent Pattern
- **Pattern:** Autonomous agents with tools
- **Benefit:** Modular, testable, extensible analysis
- **Implementation:** Executor nodes with LLM + MCP tools

### 4. DAG-Based Orchestration
- **Pattern:** Workflow as directed acyclic graph
- **Benefit:** Parallel execution, clear dependencies
- **Implementation:** Agent Framework workflow engine

### 5. Tool Abstraction (MCP)
- **Pattern:** Adapter pattern for external systems
- **Benefit:** Standardized tool interface, swap implementations
- **Implementation:** MCP protocol with HTTP transport

---

## Scalability Considerations

### Current Design (Single Server)
- **Concurrent Workflows:** Limited by FastAPI worker threads
- **State Storage:** File-based (not distributed)
- **WebSocket:** Single server, no load balancing

### Production Enhancements

#### 1. Distributed Workflow Execution
```
Replace: FileCheckpointStorage
With: Azure Cosmos DB or Redis
Benefit: Multiple backend instances, shared state
```

#### 2. Message Queue for Events
```
Add: Azure Service Bus or RabbitMQ
Pattern: Producer (workflow) → Queue → Consumer (WebSocket broadcaster)
Benefit: Decouple execution from UI updates
```

#### 3. Horizontal Scaling
```
Add: Load balancer + multiple backend instances
Add: Redis for WebSocket connection state
Pattern: Sticky sessions or broadcast via Redis pub/sub
```

#### 4. Async Job Processing
```
Add: Celery or Azure Functions
Pattern: Backend submits workflow jobs to queue
Workers execute workflows, emit events to message bus
```

---

## Security Considerations

### Authentication & Authorization
- **Current:** Azure CLI credential (dev only)
- **Production:** Add user authentication (OAuth2, OIDC)
- **RBAC:** Analyst vs. Admin vs. Viewer roles

### Data Protection
- **Encryption:** TLS for API & WebSocket
- **PII Handling:** Mask sensitive customer data in logs
- **Audit Trail:** Log all analyst decisions with timestamps

### MCP Tool Security
- **API Keys:** Secure MCP server with authentication
- **Rate Limiting:** Prevent tool abuse
- **Input Validation:** Sanitize all tool parameters

---

## Monitoring & Observability

### Application Insights Integration
```python
from azure.monitor.opentelemetry import configure_azure_monitor

configure_azure_monitor(
    connection_string=os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
)
```

**Track:**
- Workflow execution times
- Analyst response times
- Tool call durations
- Error rates & exceptions
- WebSocket connection metrics

### Logging Strategy
```
INFO: Workflow lifecycle events
DEBUG: Tool calls & LLM prompts
ERROR: Exceptions with stack traces
WARN: Checkpoint resolution delays
```

### Tracing
- OpenTelemetry tracing built into agent-framework
- Correlate events across workflow → backend → MCP → LLM

---

## Deployment Architecture

### Development
```
Local Machine:
├─ Frontend: npm run dev (Vite) → localhost:5173
├─ Backend: uvicorn backend:app → localhost:8001
└─ MCP Server: uvicorn mcp_service:app → localhost:8000
```

### Production (Azure)

```
┌────────────────────────────────────────────────────────────┐
│                     Azure Front Door                        │
│                  (CDN + Load Balancer)                      │
└─────────────────────┬──────────────────────────────────────┘
                      │
        ┌─────────────┴─────────────┐
        │                           │
        ▼                           ▼
┌───────────────┐          ┌───────────────┐
│ Static Web    │          │ Azure App     │
│ App           │          │ Service       │
│ (React build) │          │ (FastAPI)     │
└───────────────┘          └───────┬───────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
                    ▼              ▼              ▼
            ┌─────────────┐ ┌──────────┐  ┌──────────┐
            │ Azure       │ │ Azure    │  │ MCP      │
            │ OpenAI      │ │ Cosmos DB│  │ Server   │
            └─────────────┘ └──────────┘  └──────────┘
                                                │
                                                ▼
                                         ┌──────────┐
                                         │ Azure SQL│
                                         │ Database │
                                         └──────────┘
```

---

## Technology Summary

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | React 18 | UI framework |
| | Material-UI | Component library |
| | React Flow | Workflow visualization |
| | WebSocket API | Real-time events |
| | Vite | Build tool |
| **Backend** | FastAPI | REST API server |
| | WebSocket | Event streaming |
| | Uvicorn | ASGI server |
| | Pydantic | Data validation |
| **Agent Framework** | agent-framework | Workflow engine |
| | Azure OpenAI | LLM reasoning |
| | MCP Client | Tool invocation |
| **MCP Server** | FastMCP | MCP implementation |
| | Faker | Test data generation |
| **Storage** | File System | Checkpoints (dev) |
| | JSON | Checkpoint format |
| **AI** | Azure OpenAI | GPT-4 model |
| | Azure CLI Credential | Authentication |

---

## Conclusion

This architecture demonstrates a modern, event-driven AI agent system with:

✅ **Real-time visualization** - WebSocket streaming for live updates  
✅ **Human-in-the-loop** - Checkpoint-based pause/resume  
✅ **Modular agents** - Each executor is independent and testable  
✅ **Standardized tools** - MCP protocol for tool integration  
✅ **Production-ready patterns** - Async/await, error handling, logging  
✅ **Scalable design** - Ready for distributed deployment  

The system can handle complex fraud detection scenarios while providing full transparency and control to human analysts.
