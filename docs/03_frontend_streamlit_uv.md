# Part 3: Frontend Setup with Streamlit (uv Method)

## Pre-requisites
- Complete [Part 0](../SETUP.md)
- Complete [Part 1: MCP Setup (uv)](01_mcp_uv.md)
- Complete [Part 2: Backend Setup (uv)](02_backend_uv.md)
- Backend service running on `http://localhost:7000`
- MCP server running on `http://localhost:8000/mcp`
- uv installed

## Summary
In this part, you will set up and run the Streamlit frontend for the Microsoft AI Agentic Workshop using uv. The Streamlit frontend provides a clean, simple chat interface ideal for quick prototyping, demos, and simple agent testing.

**Best for:** Simple agent testing, Autogen agents, quick demos, and situations where you need a lightweight interface.

## Steps
[1. Run Streamlit frontend](#1-run-streamlit-frontend)

### 1. Run Streamlit frontend

> **Action Items:**
> Open a new terminal window separate than the one running the MCP server and backend.
> ![new terminal](media/01_mcp_new_terminal.png)
> Navigate to the applications directory and start Streamlit with uv:
> ```bash  
> cd agentic_ai/applications
> uv run streamlit run frontend.py  
> ```

## Success criteria
- Streamlit frontend is running on `http://localhost:8501`
- Backend is running on `http://localhost:7000`
- You can interact with the AI agent through the Streamlit chat interface

The application URLs:
- Backend: [http://localhost:7000](http://localhost:7000)
- Streamlit Frontend: [http://localhost:8501](http://localhost:8501)

**Next Step**: If you successfully completed all the steps, setup is complete and your agent should be running! Read more about [how it works →](04_how_it_works.md)

