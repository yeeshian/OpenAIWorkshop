## How It All Works  
  
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
