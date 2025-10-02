## Streamlit Frontend (Simple & Fast)** 🚀
The common backend application runs the agent selected in the .env file and connects to the frontend UI.

The Streamlit frontend provides a **clean, simple chat interface** ideal for:
- Quick prototyping and demos
- Simple interaction without streaming visualization
- All agent types (Autogen, Semantic Kernel, Agent Framework)

**Best for:** Simple agent testing, Autogen agents, quick demos

1. Activate virtual environment:

**Windows:**

```bash
venv\Scripts\activate
```

**macOS/Linux:**
```bash 
source venv/bin/activate
```

2. Run Streamlit:
```bash  
cd agentic_ai/applications
streamlit run frontend.py  # venv must be activated
```

The backend and frontend are running and hosted at:
- Backend: [http://localhost:7000](http://localhost:7000)
- Streamlit: [http://localhost:8501](http://localhost:8501)

Navigate to the Streamlit URL in your browser to interact with the agent.

--- 
If you successfully completed all the steps, setup is complete and your agent should be running now!

Read more about [how it works →](04_how_it_works.md)