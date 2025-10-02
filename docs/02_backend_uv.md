# Microsoft AI Agentic Application Backend Setup
Previous step: [mcp_uv.md](mcp_uv.md)

## 🚀 Microsoft Agent Framework Setup (NEW!)

This workshop now includes full support for [Microsoft's Agent Framework](https://github.com/microsoft/agent-framework), the latest agentic AI framework from Microsoft with advanced capabilities.

### Agent Framework Options:

**Single Agent (`agents.agent_framework.single_agent`):**
- Basic ChatAgent with MCP tools
- Token-by-token streaming via WebSocket
- Tool call visibility in React UI
- Session state persistence across requests

**Magentic Multi-Agent (`agents.agent_framework.multi_agent.magentic_group`):**
- Intelligent orchestrator coordinates specialist agents (CRM/Billing, Product/Promotions, Security)
- Real-time streaming of orchestrator planning and agent responses
- Custom progress ledger for human-in-the-loop support
- Checkpointing for resumable workflows
- React UI shows full internal process: task ledger, instructions, agent tool calls

**Handoff Multi-Agent (`agents.agent_framework.multi_agent.handoff_multi_domain_agent`):**
- Direct agent-to-user communication with intelligent domain routing
- Configurable context transfer between specialists (preserves customer info, history)
- Smart intent classification for seamless handoffs
- Cost-efficient (33% fewer LLM calls vs orchestrator patterns)

### Recommended Configuration for Agent Framework:
There are a few configurations that are made in the `.env` file within the `agentic_ai/applications` folder to enable the Agent Framework or another agent type.
```bash
# In your .env file in agentic_ai/applications folder, uncomment one of following for agent framework, or another option:
AGENT_MODULE="agents.agent_framework.single_agent"
# OR
AGENT_MODULE="agents.agent_framework.multi_agent.magentic_group"
# OR
AGENT_MODULE="agents.agent_framework.multi_agent.handoff_multi_domain_agent"
```

### Important Environment Variables for Agent Framework
In addition to setting the `AGENT_MODULE`, there are a few additional environment variables that can be configured with the same .env file. Add these to the bottom of your existing `.env` file:

**Magentic Orchestration Settings (for magentic_group)**
```bash
MAGENTIC_LOG_WORKFLOW_EVENTS=true
MAGENTIC_ENABLE_PLAN_REVIEW=false  # Set to true for human-in-the-loop plan approval
MAGENTIC_MAX_ROUNDS=10
```
**Handoff Agent Context Transfer (for handoff_multi_domain_agent)**
```bash
HANDOFF_CONTEXT_TRANSFER_TURNS=-1  # -1=all history, 0=none, N=last N turns
```

📚 **[See detailed pattern guide and configuration →](agentic_ai/agents/agent_framework/README.md)**

## Run Backend Service
1. Navigate to the `agentic_ai/applications` directory:
```bash
cd agentic_ai/applications
```
2. Run commands with uv:
```bash
uv run python backend.py
```
--- 

## 🎨 Choose Your Frontend Experience

### **React Frontend (Recommended for Agent Framework)** ✨

The React frontend provides **advanced streaming visualization** ideal for:
- **Microsoft Agent Framework** agents (single-agent and multi-agent Magentic orchestration)
- Real-time token-by-token streaming
- **Internal agent process visibility**: See orchestrator planning, agent thinking, and tool calls
- Turn-by-turn conversation history with tool call tracking
- Agent event timeline with emoji labels (📋 planning, 💳 billing agent, 🎁 promotions, etc.)

## 📊 Quick Comparison: Which Setup Is Right For You?

| Feature | React Frontend | Streamlit Frontend |
|---------|---------------|-------------------|
| **Real-time streaming** | ✅ Token-by-token | ❌ Full response only |
| **Internal process visibility** | ✅ Orchestrator, agents, tools | ❌ Final answer only |
| **Tool call tracking** | ✅ Per-turn history | ❌ Not shown |
| **Multi-agent visualization** | ✅ Agent timeline & planning | ❌ Not shown |
| **Best for Agent Framework** | ✅ **Recommended** | ⚠️ Basic support |
| **Setup complexity** | Medium (npm install) | Low (pip only) |
| **Best use case** | Development, demos, debugging | Quick testing, simple chat |

**Recommendation:**
- Use **React** for Agent Framework agents to see the full multi-agent orchestration
- Use **Streamlit** for quick testing of any agent type or simple demos

---

Next step: [Run Frontend with React](03_frontend_react.md) | [Run Frontend with Streamlit](03_frontend_streamlit_uv.md)

**📌 Important:** Agent Framework works best with the **React frontend** to visualize the internal agent processes, orchestrator planning, and tool calls in real-time.

---  


