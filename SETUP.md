![alt text](image-1.png)
# Microsoft AI Agentic Workshop Setup

This document describes how to setup and run your AI Agents for the workshop
    
## Setup & Installation
  
### 1. Clone the Repository

Open VS Code terminal 

```bash 
git clone <repo_url> # from folder where you want clone to reside
```
### 2. Install Python dependencies  
  
It is recommended to use a virtual environment.  

```bash 
# Creating and activating virtual environment on Mac 
python -m venv venv
source venv/bin/activate
```
```sh
# Creating and activating virtual environment on Windows
python -m venv venv
venv\Scripts\activate
```
```sh
# Install dependencies from `agentic_ai\applications`
pip install -r requirements.txt  
```

#### Example `requirements.txt` includes:  
  
- `flask`  
- `faker`  
- `python-dotenv`  
- `tenacity`  
- `openai`  
- `flasgger`  
- `fastmcp`  
- `autogen-ext[mcp]`  
- `autogen-agentchat`  
- `uvicorn`  
- `fastapi`  
- `streamlit`  
- `requests`  
- `pydantic`  
- *(Add others as needed for your specific environment)*  
  
---  

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
# AGENT_MODULE="agents.autogen.multi_agent.handoff_multi_agent_domain"
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
#### Make sure your Azure resources are configured to use the correct model deployment names, endpoints, and API versions.  
  
---  
  
### 5. Run MCP Server 

Navigate to ```agentic_ai/backend_services``` folder, and in terminal window with virtual environment activated, run MCP server

```bash
python mcp_service.py  
# Keep this terminal open; open another terminal for the next step.  

```

### 6. Run application  
Navigate to ```agentic_ai/applications```

The common backend application runs the agent selected in the .env file and connects to the frontend UI. 
  
### Option 1: Run Both Backend and Frontend Together  
  
```bash  
bash run_application.sh  
```
This script will start the FastAPI backend (`backend.py`) and the Streamlit frontend (`frontend.py`) simultaneously.  
  
- The backend will listen on [http://localhost:7000](http://localhost:7000).  
- The Streamlit user interface will open (usually at [http://localhost:8501](http://localhost:8501)).

### Option 2: Run Backend and Frontend Separately

### 1. Start the FastAPI Backend  
  
```bash  
python backend.py  
# Keep this terminal open; open another terminal for the frontend.  
```
The backend will be available at `http://localhost:7000/chat`.  
  
### 2. Start the Streamlit Frontend  
  
```bash  
streamlit run frontend.py  
```
Navigate to the address Streamlit provides (typically http://localhost:8501) to use the chat interface.  
Streamlit should popup a chat window for the Agent in a new Edge tab. 

If you successfully completed all the steps, setup is complete and your agent should be running now !
  
## How It Works  
  
1. **Web UI (Streamlit):**    
   Users input messages and interact with the assistant. A unique session ID is generated for each chat session.  
  
2. **Backend (FastAPI):**    
   Receives user prompts, manages the session and in-memory chat history, and retrieves or creates an agent according to the environment setting.  
  
3. **Agent (specified by AGENT_MODULE):**    
   Processes the input using Azure OpenAI and optional MCP tools. The agent may operate in single, multi-agent, or collaborative modes, depending on configuration.  
  
4. **Chat History:**    
   Conversation history is stored per session and can be displayed in the frontend or reset as needed.  
  
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
  
- **Microsoft Azure OpenAI Service**  
- **MCP Project**  
- **AutoGen**  
    
  
---    
## Acknowledgments  
  
- Microsoft Azure OpenAI Service    
- MCP Project    
- AutoGen
- SDP CSA & SE Team - James Nguyen, Anil Dwarkanath, Nicole Serafino, Claire Rehfuss, Patrick O'Malley, Kirby Repko, Heena Ugale, Aditya Agrawal    