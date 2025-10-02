# Part 4: How the Microsoft AI Agentic Workshop Works  
  
## Pre-requisites  
- Complete setup of MCP server, backend, and frontend  
- Basic understanding of AI agents and multi-agent systems  
  
## Summary  
This guide explains the architecture and workflow of the Microsoft AI Agentic Workshop, including how the components interact, the available API endpoints, and best practices for deployment and experimentation.  
  
## Architecture Overview  
  
### 1. Component Flow  
  
The workshop follows this execution flow:  
  
1. **Web UI (React or Streamlit):** Users input messages and interact with the assistant. A unique session ID is generated for each chat session.  
  
2. **Backend (FastAPI):** Receives user prompts via WebSocket or REST API, manages the session and chat history, and retrieves or creates an agent according to the environment setting.  
  
3. **Agent (specified by AGENT_MODULE):** Processes the input using Azure OpenAI and optional MCP tools. The agent may operate in single, multi-agent, or collaborative modes, depending on configuration.  
  
4. **Chat History:** Conversation history is stored per session and can be displayed in the frontend or reset as needed.  
  
5. **WebSocket Streaming (React only):** Real-time events broadcast agent thinking, tool calls, orchestrator planning, and streaming tokens to the React UI.  
  
### 2. Agent Types and Streaming  
  
Different agent types have different streaming capabilities:  
  
- **Agent Framework agents:** Stream events via WebSocket callbacks for real-time UI updates  
- **Other agents (Autogen, Semantic Kernel):** Return complete responses via REST API  
  
## API Endpoints  
  
### FastAPI Backend Endpoints  
  
The backend provides these API endpoints for integration:  
  
- **`POST /chat`:** Send a JSON payload with `{ "session_id": ..., "prompt": ... }`. Returns the assistant's response.  
  
- **`POST /reset_session`:** Send a payload `{ "session_id": ... }` to clear the conversation history for that session.  
  
- **`GET /history/{session_id}`:** Fetches all previous messages for a given session.  
  
## Configuration and Best Practices  
  
### Environment Configuration  
  
Key configuration considerations:  
  
- The current session store uses an in-memory Python dictionary; for production deployments, substitute this with a persistent store such as Redis or a database.  
- Ensure secrets in your `.env` file (like API keys) are never committed to version control.  
- The MCP server and Azure endpoint URLs must be accessible from the backend.  
- To experiment with different agent behaviors, adjust the `AGENT_MODULE` in `.env`.  
  
### Production Considerations  
  
For production deployment:  
  
- Replace in-memory session storage with persistent storage (Redis, CosmosDB, etc.)  
- Implement proper authentication and authorization  
- Use Azure Key Vault for secrets management  
- Set up monitoring and logging  
- Configure load balancing for high availability  
  
## Success criteria  
- Understanding of the complete application architecture  
- Knowledge of available API endpoints  
- Awareness of configuration options and best practices  
- Ability to customize agent behavior and deployment settings  
  
## Credits and Acknowledgments  
  
**Technologies Used:**  
- **[Microsoft Agent Framework](https://github.com/microsoft/agent-framework)** - Microsoft's latest agentic AI framework  
- **Microsoft Azure OpenAI Service**  
- **MCP Project** - Model Context Protocol  
- **AutoGen** - Multi-agent conversation framework  
- **Semantic Kernel** - Microsoft's AI orchestration SDK  
  
**Team Acknowledgments:**  
- Microsoft Agent Framework Team  
- Microsoft Azure OpenAI Service Team  
- MCP Project Contributors  
- AutoGen Community  
- SDP CSA & SE Team - James Nguyen, Anil Dwarkanath, Nicole Serafino, Claire Rehfuss, Patrick O'Malley, Kirby Repko, Heena Ugale, Aditya Agrawal  
  
**Next Step**: Start experimenting with different agent configurations by modifying the `AGENT_MODULE` in your `.env` file, or explore the detailed [Agent Framework documentation](../agentic_ai/agents/agent_framework/README.md).
