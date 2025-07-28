

# System Architecture  
```mermaid

graph TB  
  %% Layers  
  subgraph Frontend  
    FE[Streamlit Chat UI]  
  end  
  subgraph Backend  
    BE[FastAPI Backend]  
  end  
  subgraph AgentServiceLayer  
    AS[Agent Service - Single or Multi Agent]  
  end  
  subgraph StatePersistence  
    SS[State Store]  
    MEM[In-Memory Dict]  
    COSMOS[Azure Cosmos DB]  
  end  
  subgraph Databases  
    SQL[(SQL Database)]  
    VEC[(Vector Database)]  
  end  
  subgraph MCP  
    MCP[MCP API Server]  
  end  
  
  %% Connections  
  FE --> BE  
  BE --> AS  
  AS --> MCP  
  MCP -- semantic search --> VEC  
  MCP --> SQL  
  BE --> SS  
  AS --> SS  
  SS --> MEM  
  SS --> COSMOS  

  ```  
This document outlines the architecture for the Microsoft AI Agentic Workshop platform. The architecture is modular and designed to support a wide variety of agent design patterns, allowing you to focus on agent implementation and experimentation without changing the core infrastructure.  
  
---  
  
# High-Level Overview  
  
The system is organized into four primary layers plus a state-persistence component:  
  
- **Front End** – User-facing chat interface.  
- **Backend** – Orchestrates conversation flow, session routing, and mediates between the front end and agent logic.  
- **Agent Service Layer** – Loads, instantiates, and operates agent implementations (single-agent, multi-agent, multi-domain, etc.).  
- **Model Context Protocol (MCP) API Server** – Exposes structured business operations and tools via API endpoints for agent use.  
- **Agent State Persistence** – Stores per-session memory and conversation history, backed by either an in-memory Python dict (default) or an Azure Cosmos DB container for durable storage.  
  
**Supporting databases include:**  
- **SQL Database** – Core business/transactional data (customers, subscriptions, invoices, etc.).  
- **Vector Database** – Embedding-based semantic retrieval over internal documents and knowledge.  
  
---  
  
# Component Breakdown  
  
## 1. Frontend  
  
**Technology:** Streamlit (Python)  
  
**Functionality:**  
- Presents an interactive chat interface.  
- Maintains a unique, persistent session for each user.  
- Displays real-time chat history.  
- Sends prompts to, and receives responses from, the backend via HTTP.  
  
---  
  
## 2. Backend  
  
**Technology:** FastAPI (asynchronous Python)  
  
**Responsibilities:**  
- Exposes HTTP API endpoints for frontend communication.  
- Routes requests to the appropriate agent instance in the Agent Service layer.  
- Mediates agent tool calls to the MCP API server.  
- Persists session data and chat history via the Agent State Persistence component.  
  
**Endpoints:**  
- `/chat` – Processes chat requests and returns agent responses.  
- `/reset_session` – Clears session memory and context state.  
- `/history/{session_id}` – Retrieves conversation history.  
  
---  
  
## 3. Agent Service Layer  
  
**Design:** Pluggable and modular—enables loading different agent design patterns:  
- Intelligent Single Agent  
- Multi-Domain Agent  
- Collaborative Multi-Agent System  
  
**Capabilities:**  
- Tool invocation via structured MCP API calls.  
- Retrieval-Augmented Generation (RAG) using the vector knowledge base.  
- Short-term session memory stored through the Agent State Persistence component; optional long-term memory strategies.  
  
**Implementation:**  
- Built with frameworks such as Semantic Kernel, AutoGen, or Azure Agent-Service.  
- Swap behaviors by changing the `AGENT_MODULE` environment variable.  
  
---  
  
## 4. Model Context Protocol (MCP) API Server  
  
**Technology:** FastAPI/asyncio, Pydantic for JSON-schema validation.  
  
**Purpose:** Provides realistic enterprise APIs for agent tool usage.  
  
**Key Endpoint Categories:**  
- Customer/account management  
- Subscription, invoice, and payment processing  
- Data-usage reporting  
- Product and promotion queries  
- Support ticket workflows  
- Security log review and remediation  
- Semantic search over the knowledge base  
  
---  
  
## 5. Agent State Persistence  
  
**Options:**  
- **In-Memory Dict (default):** Fast, ephemeral; data is lost on process exit.  
- **Azure Cosmos DB:** Durable, horizontally scalable; hierarchical partition key (`/tenant_id` + `/id`) for multi-tenant scenarios.  
  
**Selection Logic:**  
- If Cosmos DB connection settings (`COSMOSDB_ENDPOINT` plus either `COSMOSDB_KEY` or AAD credentials) are present, the system auto-switches to Cosmos DB.  
- Otherwise, it silently falls back to the in-memory store.  
  
**Used By:**  
- Backend – to save and fetch conversation history.  
- Agent Service Layer – to store and recall per-session memory or scratch-pad state.  
  
---  
  
## Databases  
  
- **SQL Database:** Stores structured business data (customers, subscriptions, invoices, orders, etc.).  
- **Vector Database:** Stores embeddings for semantic search and RAG workflows.  
  
---  
  
# Summary  
  
The architecture cleanly separates concerns across user interaction, backend orchestration, agent reasoning, data/tool access, and session persistence. By making state persistence pluggable, the platform supports quick local experimentation (in-memory) and production-grade durability (Cosmos DB) without code changes—unlocking flexible, enterprise-ready agentic solutions.  