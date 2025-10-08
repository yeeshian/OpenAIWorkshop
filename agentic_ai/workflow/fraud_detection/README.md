# Contoso Fraud Detection & Escalation Workflow

This example demonstrates a comprehensive fraud detection system using the Agent Framework's workflow capabilities.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Suspicious Activity Alert                         │
│                  (monitoring system trigger)                         │
└────────────────────────────┬────────────────────────────────────────┘
                             ↓
                    ┌────────────────┐
                    │  AlertRouter   │
                    └────────┬───────┘
                             ↓
           ┌─────────────────┼─────────────────┐
           ↓                 ↓                 ↓
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │   Usage      │  │  Location    │  │   Billing    │
    │   Pattern    │  │  Analysis    │  │   Charge     │
    │  Executor    │  │  Executor    │  │  Executor    │
    │  (MCP tools) │  │  (MCP tools) │  │  (MCP tools) │
    └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
           └─────────────────┼─────────────────┘
                             ↓
                    ┌────────────────┐
                    │  Fraud Risk    │
                    │  Aggregator    │
                    │  (LLM Agent)   │
                    └────────┬───────┘
                             ↓
                    (Risk Score Switch)
                             ↓
            ┌────────────────┴────────────────┐
            ↓                                 ↓
     (High Risk ≥0.6)                  (Low Risk <0.6)
            ↓                                 ↓
    ┌──────────────┐                 ┌──────────────┐
    │   Analyst    │                 │  Auto Clear  │
    │   Review     │                 │  Executor    │
    │ (Human Input)│                 └──────┬───────┘
    └──────┬───────┘                        │
           ↓                                 │
    ┌──────────────┐                        │
    │  Fraud       │                        │
    │  Action      │                        │
    │  Executor    │                        │
    └──────┬───────┘                        │
           └──────────────┬─────────────────┘
                          ↓
                 ┌────────────────┐
                 │ Final          │
                 │ Notification   │
                 │ Executor       │
                 └────────────────┘
```

## Key Features

### 1. **Event-Driven Processing**
- Triggered by suspicious activity alerts from monitoring systems
- Supports multiple alert types: multi-country logins, data spikes, unusual charges

### 2. **Fan-Out Pattern**
- Single alert routed to three specialist agents simultaneously
- Each agent uses filtered MCP tools for domain-specific analysis:
  - **UsagePatternExecutor**: Analyzes data usage patterns
  - **LocationAnalysisExecutor**: Checks geolocation anomalies
  - **BillingChargeExecutor**: Reviews billing and charges

### 3. **Fan-In Aggregation**
- **FraudRiskAggregatorExecutor** waits for all three analyses
- LLM-based agent synthesizes findings into single risk assessment
- Produces overall risk score (0.0-1.0) and recommended action

### 4. **Switch/Case Routing**
- Routes based on risk score threshold:
  - **High risk (≥0.6)**: Human analyst review required
  - **Low risk (<0.6)**: Auto-clear

### 5. **Human-in-the-Loop**
- Uses `RequestInfoExecutor` for analyst review
- Workflow pauses and creates checkpoint
- Analyst provides decision (lock account, refund charges, clear, both)
- Workflow resumes with analyst's decision

### 6. **Checkpointing**
- Workflow state saved at each superstep
- Can pause indefinitely while waiting for analyst
- Resume from exact point after analyst decision

### 7. **MCP Tool Integration**
- Each specialist agent has filtered access to relevant MCP tools
- Tools used:
  - Usage: `get_customer_detail`, `get_subscription_detail`, `get_data_usage`, `search_knowledge_base`
  - Location: `get_customer_detail`, `get_security_logs`, `search_knowledge_base`
  - Billing: `get_customer_detail`, `get_billing_summary`, `get_subscription_detail`, `get_customer_orders`, `search_knowledge_base`

## Message Flow

1. **SuspiciousActivityAlert** → AlertRouter
2. **SuspiciousActivityAlert** → [UsagePattern, Location, Billing] (fan-out)
3. **[UsageAnalysisResult, LocationAnalysisResult, BillingAnalysisResult]** → Aggregator (fan-in)
4. **FraudRiskAssessment** → Switch (risk score check)
5. **FraudRiskAssessment** → AnalystReview OR AutoClear
6. **AnalystDecision** → FraudAction (if high risk)
7. **ActionResult** → FinalNotification
8. **FinalNotification** → Workflow output

## Setup

### Prerequisites

1. **Azure OpenAI Configuration**:
   ```bash
   export AZURE_OPENAI_API_KEY="your-key"
   export AZURE_OPENAI_CHAT_DEPLOYMENT="your-deployment"
   export AZURE_OPENAI_ENDPOINT="https://your-endpoint.openai.azure.com/"
   export AZURE_OPENAI_API_VERSION="2024-10-01-preview"
   ```

2. **MCP Server**:
   ```bash
   export MCP_SERVER_URI="http://localhost:8000"
   ```

3. **Start MCP Server** (in separate terminal):
   ```bash
   cd mcp
   python mcp_service.py
   ```

### Running the Workflow

```bash
cd agentic_ai/workflow/examples/fraud_detection
python fraud_detection_workflow.py
```

## Sample Alerts

The example includes three sample alerts:

### Alert 1: Multi-Country Login (High Severity)
```python
alert_id: "ALERT-001"
customer_id: 1
alert_type: "multi_country_login"
description: "Login attempts from USA and Russia within 2 hours"
severity: "high"
```

### Alert 2: Data Spike (Medium Severity)
```python
alert_id: "ALERT-002"
customer_id: 2
alert_type: "data_spike"
description: "Data usage increased by 500% in last 24 hours"
severity: "medium"
```

### Alert 3: Unusual Charges (High Severity)
```python
alert_id: "ALERT-003"
customer_id: 3
alert_type: "unusual_charges"
description: "Three large purchases totaling $5,000 in 10 minutes"
severity: "high"
```

## Expected Output

```
================================================================================
Contoso Fraud Detection & Escalation Workflow
================================================================================
[Setup] Connecting to MCP server at http://localhost:8000
[Setup] Connected to MCP server, loaded 20 tools
[Workflow] Fraud detection workflow built successfully

================================================================================
Processing Alert: ALERT-001
================================================================================
[Workflow] Starting fraud detection workflow...
[AlertRouter] Processing alert ALERT-001 for customer 1
[AlertRouter] Alert routed to 3 analysis executors
[UsagePatternExecutor] Analyzing alert ALERT-001
[LocationAnalysisExecutor] Analyzing alert ALERT-001
[BillingChargeExecutor] Analyzing alert ALERT-001
[UsagePatternExecutor] Sent analysis result (risk_score=0.7)
[LocationAnalysisExecutor] Sent analysis result (risk_score=0.85)
[BillingChargeExecutor] Sent analysis result (risk_score=0.4)
[FraudRiskAggregator] Aggregating 3 analysis results
[FraudRiskAggregator] Sent assessment (risk_score=0.65, action=lock_account)

================================================================================
ANALYST REVIEW REQUIRED
================================================================================
Request: {'type': 'fraud_analyst_review', ...}

Simulating analyst decision...
[Analyst] Decision: lock_account
[FraudAction] Executing action: lock_account for alert ALERT-001
[FraudAction] Action executed for alert ALERT-001
[FinalNotification] Alert ALERT-001 completed and logged

================================================================================
Workflow completed successfully!
================================================================================
```

## Customization

### Adjust Risk Threshold

Change the risk threshold in the switch/case edge:

```python
# Current: 0.6 threshold
(lambda assessment: assessment.overall_risk_score >= 0.6, analyst_review)

# Example: 0.5 threshold (more sensitive)
(lambda assessment: assessment.overall_risk_score >= 0.5, analyst_review)
```

### Add Custom Analysis

Create a new executor:

```python
class CustomAnalysisExecutor(Executor):
    async def handle_alert(
        self, ctx: WorkflowContext[CustomAnalysisResult], alert: SuspiciousActivityAlert
    ) -> None:
        # Your analysis logic
        pass
```

Add to workflow:

```python
builder.add_executor(custom_executor)
builder.add_edge(alert_router, custom_executor)
builder.add_fan_in_edge([usage, location, billing, custom_executor], aggregator)
```

### Modify Agent Instructions

Adjust agent instructions in executor constructors:

```python
instructions=(
    "Your custom instructions here..."
)
```

## Key Concepts Demonstrated

1. **Fan-Out Pattern**: One message → multiple executors
2. **Fan-In Pattern**: Multiple messages → one executor (waits for all)
3. **Switch/Case Routing**: Conditional routing based on message content
4. **Human-in-the-Loop**: Workflow pause/resume with external input
5. **Checkpointing**: Persistent workflow state across restarts
6. **MCP Tool Integration**: Domain-specific tool filtering
7. **LLM Agent Executors**: AI-powered decision making
8. **Type-Safe Messaging**: Pydantic models for all messages
9. **Event Streaming**: Real-time workflow event monitoring

## Recent Improvements

### ✅ Fixed Issues (Latest)

1. **Analyst Review Data Rendering**: Fixed dataclass serialization in `_serialize_analyst_request()` to properly display Risk Score, Recommended Action, Alert ID, and other assessment details in the UI.

2. **Event Ordering**: Corrected event broadcast sequence so Analyst Review completion appears before Fraud Action execution, maintaining proper workflow visualization order.

These fixes ensure the UI accurately reflects the workflow state and displays all relevant fraud assessment information during analyst review.

## Troubleshooting

### MCP Connection Fails

Ensure MCP server is running:
```bash
curl http://localhost:8000/health
```

### Missing Environment Variables

Check all required variables are set:
```bash
echo $AZURE_OPENAI_API_KEY
echo $AZURE_OPENAI_CHAT_DEPLOYMENT
echo $AZURE_OPENAI_ENDPOINT
```

### Analyst Review Panel Not Showing Data

This should now be fixed. If you still see issues:
- Restart the backend server to load the updated code
- Check browser console for WebSocket errors
- Verify the MCP server is responding

### Workflow Hangs

Check logs for executor errors. Each executor logs its progress.

### Checkpoint Restoration

To restore from checkpoint:
```python
checkpoint_id = workflow.get_latest_checkpoint_id()
await workflow.restore_from_checkpoint(checkpoint_id)
```

## Real-Time Workflow Visualizer UI

### Overview

A modern React + FastAPI dashboard for real-time workflow visualization and analyst interaction.

**Features:**
- 🎯 Interactive workflow graph (React Flow)
- 📊 Real-time executor status updates
- 💬 Live event stream with WebSocket
- 🎨 Professional Material-UI design
- 👤 Human-in-the-loop analyst panel

### Architecture

```
┌─────────────────────┐         ┌──────────────────────┐
│   React Frontend    │◄────────┤   FastAPI Backend    │
│   (Port 3000)       │ WebSocket│   (Port 8001)        │
│                     │◄────────┤                      │
│  - React Flow       │   HTTP  │  - Workflow Engine   │
│  - Material-UI      │         │  - Event Streaming   │
│  - WebSocket Client │         │  - Azure OpenAI      │
└─────────────────────┘         └──────────────────────┘
                                          │
                                          ▼
                                 ┌──────────────────┐
                                 │   MCP Server     │
                                 │   (Port 8000)    │
                                 └──────────────────┘
```

### Quick Start

**1. Install Frontend Dependencies:**
```bash
cd ui
npm install
```

**2. Start All Services (3 terminals):**

Terminal 1 - MCP Server:
```bash
cd mcp
uv run mcp_service.py
```

Terminal 2 - FastAPI Backend:
```bash
cd agentic_ai/workflow/fraud_detection
uv run --prerelease allow backend.py
```

Terminal 3 - React Frontend:
```bash
cd agentic_ai/workflow/fraud_detection/ui
npm run dev
```

**3. Open Browser:**
```
http://localhost:3000
```

### Using the UI

1. **Select Alert**: Choose from 3 sample alerts (ALERT-001, ALERT-002, ALERT-003)
2. **Start Workflow**: Click button to begin processing
3. **Watch Live Updates**: Nodes change color as executors run
   - 🔵 Blue = Running
   - 🟢 Green = Completed
   - ⚪ Gray = Idle
4. **Analyst Review**: When high-risk fraud detected, review panel appears
5. **Submit Decision**: Choose action and add notes
6. **Monitor Events**: Right panel shows complete event stream

### API Endpoints

**REST API:**
- `GET /api/alerts` - List sample alerts
- `POST /api/workflow/start` - Start workflow execution
- `POST /api/workflow/decision` - Submit analyst decision
- `GET /api/workflow/status/{alert_id}` - Get current status

**WebSocket:**
- `WS /ws` - Real-time event stream

### Technology Stack

**Frontend:**
- React 18 + Vite
- React Flow (workflow visualization)
- Material-UI (components)
- Axios + WebSocket

**Backend:**
- FastAPI (async web framework)
- Agent Framework (workflow engine)
- Pydantic (data validation)
- WebSocket (real-time events)

### Troubleshooting

**WebSocket Connection Failed:**
- Ensure backend is running on port 8001
- Check browser console for errors

**Workflow Not Starting:**
- Verify MCP server is running (port 8000)
- Check Azure OpenAI credentials in .env
- Check backend logs

**UI Not Updating:**
- Check WebSocket connection in DevTools
- Verify events are being sent from backend

## Next Steps

- ✅ ~~Implement real-time UI for analyst review~~ (Completed)
- Add database persistence for checkpoints (Redis, Cosmos DB)
- Add metrics and monitoring (OpenTelemetry)
- Integrate with actual fraud detection systems
- Add multiple workflow instances for parallel alert processing
- Implement escalation chains for critical cases
- Add workflow history/replay to UI
- Export workflow results to PDF
- Add custom alert creation in UI

## Related Examples

- `human-in-the-loop/guessing_game_with_human_input.py` - Basic human-in-the-loop pattern
- `agents/workflow_as_agent_human_in_the_loop_azure.py` - Azure-integrated human input
- `control-flow/` - Switch/case and conditional routing examples
- `parallelism/` - Fan-out and concurrent execution patterns

## License

Copyright (c) Microsoft. All rights reserved.
