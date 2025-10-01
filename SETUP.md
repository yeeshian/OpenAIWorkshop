# Microsoft AI Agentic Workshop Setup

## Setup & Installation
  
### 1. Clone the Repository

Open VS Code terminal 

```bash 
git clone <repo_url> # from folder where you want clone to reside
```
### 2. Install Python dependencies  

#### ⚡ Recommended: Use `uv` for fastest setup

[**uv**](https://github.com/astral-sh/uv) is a blazing-fast Python package installer and resolver written in Rust. It's 10-100x faster than `pip` and automatically manages virtual environments.

**Install uv:**
```bash
# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Setup dependencies with uv:**
```bash
# Navigate to the applications directory
cd agentic_ai/applications

# Create virtual environment and install all dependencies in one command
uv sync

# uv automatically creates .venv and installs dependencies from pyproject.toml
```

**Run commands with uv:**
```bash
# Run Python scripts without manual venv activation
uv run python backend.py
uv run streamlit run frontend.py

# Or activate the venv manually if you prefer
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
```

#### Alternative: Traditional pip/venv approach

If you prefer the traditional approach or don't want to install `uv`:

```bash 
# Creating and activating virtual environment on macOS/Linux
python -m venv venv
source venv/bin/activate
```
```cmd
# Creating and activating virtual environment on Windows
python -m venv venv
venv\Scripts\activate
```
```bash
# Install dependencies from `agentic_ai/applications`
cd agentic_ai/applications
pip install -r requirements.txt  
```

### 3. Deploy LLM model using Azure AI Foundry

1. Login to ai.azure.com. Create account if you don't already have access to an account.
2. Create project, use new hub is none exists. This will setup a hub, project container, AI services, Storage account and Key Vault
3. Use API Key, Azure OpenAI Service endpoint and Project connection string and add to .env file (next step)
4. On project page, go to Models + endpoints -> Deploy model -> Deploy base model -> gpt-4.1
5. Select deployment type (Standard, Global Standard etc.) and region if desired
6. Customize deployment details to reduce tokens per minute to 10K, disable dynamic quote 
  
### 4. Set up your environment variables and select the agent to run 
  
Rename `.env.sample` to `.env` and fill in all required fields:  
  
```bash  
############################################  
#  Azure OpenAI – chat model configuration #  
############################################  
# Replace with your model-deployment endpoint in Azure AI Foundry  
AZURE_OPENAI_ENDPOINT="https://YOUR-OPENAI-SERVICE-ENDPOINT.openai.azure.com"  
  
# Replace with your Foundry project’s API key  
AZURE_OPENAI_API_KEY="YOUR-OPENAI-API-KEY"  
  
# Connection-string that identifies your Foundry project / workspace. Only needed if you're using Azure Agent Service
AZURE_AI_AGENT_PROJECT_CONNECTION_STRING="YOUR-OPENAI-PROJECT-CONNECTION-STRING"  
  
# Model deployment & API version  
AZURE_OPENAI_CHAT_DEPLOYMENT="gpt-4.1"  
AZURE_AI_AGENT_MODEL_DEPLOYMENT_NAME="gpt-4.1"  
AZURE_OPENAI_API_VERSION="2025-01-01-preview"  
OPENAI_MODEL_NAME="gpt-4.1-2025-04-14"  #only applicable for Autogen
  
############################################  
#     Local URLs for backend & MCP server  #  
############################################  
BACKEND_URL="http://localhost:7000"  
MCP_SERVER_URI="http://localhost:8000/mcp"  
  
############################################  
  
############################################  
#         Agent module to be executed      #  
############################################  
# AGENT_MODULE="agents.autogen.multi_agent.reflection_agent"
# AGENT_MODULE="agents.autogen.single_agent.loop_agent"
# AGENT_MODULE="agents.autogen.multi_agent.collaborative_multi_agent_round_robin"
# AGENT_MODULE="agents.autogen.multi_agent.collaborative_multi_agent_selector_group"
# AGENT_MODULE="agents.autogen.multi_agent.handoff_multi_domain_agent"
# AGENT_MODULE="agents.agent_framework.single_agent"
# AGENT_MODULE="agents.agent_framework.multi_agent.handoff_multi_domain_agent"
# AGENT_MODULE="agents.agent_framework.multi_agent.magentic_group"
# AGENT_MODULE="agents.semantic_kernel.multi_agent.collaborative_multi_agent"
# AGENT_MODULE="agents.semantic_kernel.multi_agent.a2a.collaborative_multi_agent"
AGENT_MODULE="agents.autogen.single_agent.loop_agent"  
  
# -----------------------------------------------------------  
# If you are experimenting with Logistics-A2A, uncomment:  
# LOGISTIC_MCP_SERVER_URI="http://localhost:8100/sse"  
# LOGISTICS_A2A_URL="http://localhost:9100"  
# -----------------------------------------------------------  
  
  
#############################################################  
#          Cosmos DB – state persistence settings           #  
#############################################################  
# Endpoint for your Cosmos DB account (SQL API)  
COSMOSDB_ENDPOINT="https://YOUR-COSMOS-ACCOUNT.documents.azure.com:443/"  
  
# ---------  Choose ONE authentication method  --------------  
# (1) Account key  
#COSMOSDB_KEY="YOUR-COSMOS-ACCOUNT-KEY"  
  
# (2) Azure AD service-principal (preferred in production)  
#AAD_CLIENT_ID="00000000-0000-0000-0000-000000000000"  
#AAD_CLIENT_SECRET="YOUR-AAD-CLIENT-SECRET"  
#AAD_TENANT_ID="11111111-1111-1111-1111-111111111111"  
# -----------------------------------------------------------  
  
# Logical (application) tenant for data isolation  
# Leave as "default" unless you partition data by customer / org  
DATA_TENANT_ID="default"  
  
# Database & container names (created automatically if not present)  
COSMOSDB_DB_NAME="ai_state_db"  
COSMOSDB_CONTAINER_NAME="state_store"  
```

**Note:**    
#### Choosing a State Store  
  
- **Do nothing** ➜ the workshop uses an in-memory Python `dict` (fast, but data is lost when the process exits).  
- **Fill in the Cosmos variables** ➜ the app automatically switches to an Azure Cosmos DB container with a hierarchical partition-key (`/tenant_id + /id`) so chat history survives restarts and scales across instances.  
  
> If neither `COSMOSDB_KEY` nor the AAD credential set is provided, the code silently falls back to the in-memory store.  
> **Important:**    
> If you choose Cosmos DB and use Azure AD service-principal authentication, you must grant the service principal a custom role for data plane (read/write) access in Cosmos DB.    
> See: [Grant data plane access using custom roles in Azure Cosmos DB](https://learn.microsoft.com/en-us/azure/cosmos-db/nosql/how-to-grant-data-plane-access?tabs=custom-definition%2Ccsharp&pivots=azure-interface-cli)  
>  
> Without this role, the application will not be able to access or persist chat history in Cosmos DB using Azure AD authentication.  

#### Make sure your Azure resources are configured to use the correct model deployment names, endpoints, and API versions.  
  
---

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

```bash
# In your .env file, uncomment one of these:
AGENT_MODULE="agents.agent_framework.single_agent"
# OR
AGENT_MODULE="agents.agent_framework.multi_agent.magentic_group"
# OR
AGENT_MODULE="agents.agent_framework.multi_agent.handoff_multi_domain_agent"

# Magentic Orchestration Settings (for magentic_group)
MAGENTIC_LOG_WORKFLOW_EVENTS=true
MAGENTIC_ENABLE_PLAN_REVIEW=false  # Set to true for human-in-the-loop plan approval
MAGENTIC_MAX_ROUNDS=10

# Handoff Agent Context Transfer (for handoff_multi_domain_agent)
HANDOFF_CONTEXT_TRANSFER_TURNS=-1  # -1=all history, 0=none, N=last N turns
```

📚 **[See detailed pattern guide and configuration →](agentic_ai/agents/agent_framework/README.md)**

**📌 Important:** Agent Framework works best with the **React frontend** to visualize the internal agent processes, orchestrator planning, and tool calls in real-time.

---  
  
### 5. Run MCP Server 

Navigate to the `mcp` folder and start the MCP server:

**With uv (recommended):**
```bash
cd mcp
uv run python mcp_service.py
# Keep this terminal open; open another terminal for the next step.
```

**Alternative (traditional approach):**
```bash
cd mcp
# Make sure your virtual environment is activated
python mcp_service.py
# Keep this terminal open; open another terminal for the next step.
```

### 6. Run application  

The common backend application runs the agent selected in the .env file and connects to the frontend UI.

---

## 🎨 Choose Your Frontend Experience

### **Option A: React Frontend (Recommended for Agent Framework)** ✨

The React frontend provides **advanced streaming visualization** ideal for:
- **Microsoft Agent Framework** agents (single-agent and multi-agent Magentic orchestration)
- Real-time token-by-token streaming
- **Internal agent process visibility**: See orchestrator planning, agent thinking, and tool calls
- Turn-by-turn conversation history with tool call tracking
- Agent event timeline with emoji labels (📋 planning, 💳 billing agent, 🎁 promotions, etc.)

#### Prerequisites for React Frontend:

**Install Node.js (if not already installed):**

The React frontend requires Node.js 16+ and npm. Check if you have them installed:

```bash
node --version  # Should be v16 or higher
npm --version   # Should be v8 or higher
```

If not installed, download and install from:
- **Windows/macOS/Linux:** [https://nodejs.org/](https://nodejs.org/) (Download the LTS version)
- **Alternative (Windows):** Use `winget install OpenJS.NodeJS.LTS`
- **Alternative (macOS):** Use `brew install node`

#### Running with React:

**Terminal 1 - Start Backend:**

*With uv (recommended):*
```bash
cd agentic_ai/applications
uv run python backend.py
# Backend runs on http://localhost:7000 with WebSocket support
```

*Alternative (traditional):*
```bash
cd agentic_ai/applications
python backend.py  # venv must be activated
# Backend runs on http://localhost:7000 with WebSocket support
```

**Terminal 2 - Start React Frontend:**

```bash
# Navigate to the React frontend directory
cd agentic_ai/applications/react-frontend

# Install dependencies (first time only, or after package.json changes)
npm install

# Start the development server
npm start

# The React app will automatically open at http://localhost:3000
# If it doesn't open automatically, navigate to http://localhost:3000 in your browser
```

**Configuration (Optional):**

The React frontend connects to `http://localhost:7000` by default. To customize the backend URL, create a `.env` file in the `react-frontend` directory:

```bash
# react-frontend/.env
REACT_APP_BACKEND_URL=http://localhost:7000
```

**Troubleshooting:**

- **Port 3000 already in use?** The React app will prompt you to use a different port. Type `Y` to accept.
- **npm install fails?** Try clearing npm cache: `npm cache clean --force` and retry.
- **WebSocket connection errors?** Ensure the backend is running on port 7000 and firewall isn't blocking connections.

**Best for:** Agent Framework single-agent, magentic_group multi-agent, viewing internal agent processes

---

### **Option B: Streamlit Frontend (Simple & Fast)** 🚀

The Streamlit frontend provides a **clean, simple chat interface** ideal for:
- Quick prototyping and demos
- Simple interaction without streaming visualization
- All agent types (Autogen, Semantic Kernel, Agent Framework)

#### Running with Streamlit:

**Option B1: Run Both Backend and Frontend Together**

*With uv (recommended):*
```bash  
cd agentic_ai/applications
uv run bash run_application.sh  
```

*Alternative (traditional):*
```bash  
cd agentic_ai/applications
bash run_application.sh  # venv must be activated
```

This script starts both FastAPI backend and Streamlit frontend simultaneously.
- Backend: [http://localhost:7000](http://localhost:7000)
- Streamlit: [http://localhost:8501](http://localhost:8501)

**Option B2: Run Backend and Frontend Separately**

**Terminal 1 - Start Backend:**

*With uv (recommended):*
```bash  
cd agentic_ai/applications
uv run python backend.py  
```

*Alternative (traditional):*
```bash  
cd agentic_ai/applications
python backend.py  # venv must be activated
```

**Terminal 2 - Start Streamlit:**

*With uv (recommended):*
```bash  
cd agentic_ai/applications
uv run streamlit run frontend.py  
```

*Alternative (traditional):*
```bash  
cd agentic_ai/applications
streamlit run frontend.py  # venv must be activated
```

**Best for:** Simple agent testing, Autogen agents, quick demos

---

If you successfully completed all the steps, setup is complete and your agent should be running now!
  
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

## How It Works  
  
1. **Web UI (React or Streamlit):**    
   Users input messages and interact with the assistant. A unique session ID is generated for each chat session.  
  
2. **Backend (FastAPI):**    
   Receives user prompts via WebSocket or REST API, manages the session and chat history, and retrieves or creates an agent according to the environment setting.  
  
3. **Agent (specified by AGENT_MODULE):**    
   Processes the input using Azure OpenAI and optional MCP tools. The agent may operate in single, multi-agent, or collaborative modes, depending on configuration.
   - **Agent Framework agents** stream events via WebSocket callbacks for real-time UI updates
   - **Other agents** return complete responses via REST API  
  
4. **Chat History:**    
   Conversation history is stored per session and can be displayed in the frontend or reset as needed.
   
5. **WebSocket Streaming (React only):**
   Real-time events broadcast agent thinking, tool calls, orchestrator planning, and streaming tokens to the React UI.  
  
---  
  
## FastAPI Endpoints  
  
- `POST /chat`    
  Send a JSON payload with `{ "session_id": ..., "prompt": ... }`. Returns the assistant’s response.  
  
- `POST /reset_session`    
  Send a payload `{ "session_id": ... }` to clear the conversation history for that session.  
  
- `GET /history/{session_id}`    
  Fetches all previous messages for a given session.  
  
---  
  
## Notes & Best Practices  
  
- The current session store uses an in-memory Python dictionary; for production deployments, substitute this with a persistent store such as Redis or a database.  
- Ensure secrets in your `.env` file (like API keys) are never committed to version control.  
- The MCP server and Azure endpoint URLs must be accessible from the backend.  
- To experiment with different agent behaviors, adjust the `AGENT_MODULE` in `.env`.  
  
---  
  
## Credits  
  
- **[Microsoft Agent Framework](https://github.com/microsoft/agent-framework)** - Microsoft's latest agentic AI framework
- **Microsoft Azure OpenAI Service**  
- **MCP Project** - Model Context Protocol
- **AutoGen** - Multi-agent conversation framework
- **Semantic Kernel** - Microsoft's AI orchestration SDK
    
  
---    
## Acknowledgments  
  
- Microsoft Agent Framework Team
- Microsoft Azure OpenAI Service    
- MCP Project    
- AutoGen Community
- SDP CSA & SE Team - James Nguyen, Anil Dwarkanath, Nicole Serafino, Claire Rehfuss, Patrick O'Malley, Kirby Repko, Heena Ugale, Aditya Agrawal    