"""  
FastAPI entry-point.  
  
Only two lines changed compared with your original file:  
    from utils.state_store import get_state_store  
    STATE_STORE = get_state_store()  
Everything else is untouched.  
"""  
  
import os  
import sys  
from pathlib import Path  
from typing import Dict, List  
  
import uvicorn  
from fastapi import FastAPI  
from pydantic import BaseModel  
from dotenv import load_dotenv  
  
# ------------------------------------------------------------------  
# Environment  
# ------------------------------------------------------------------  
load_dotenv()  # read .env if present  
  
# ------------------------------------------------------------------  
# Bring project root onto the path & load your agent dynamically  
# ------------------------------------------------------------------  
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  
agent_module_path = os.getenv("AGENT_MODULE")  
agent_module = __import__(agent_module_path, fromlist=["Agent"])  
Agent = getattr(agent_module, "Agent")  
  
# ------------------------------------------------------------------  
# Get the correct state-store implementation  
# ------------------------------------------------------------------  
from utils import get_state_store  
  
STATE_STORE = get_state_store()  # either dict or CosmosDBStateStore  
  
# ------------------------------------------------------------------  
# FastAPI app  
# ------------------------------------------------------------------  
app = FastAPI()  
  
  
class ChatRequest(BaseModel):  
    session_id: str  
    prompt: str  
  
  
class ChatResponse(BaseModel):  
    response: str  
  
  
class ConversationHistoryResponse(BaseModel):  
    session_id: str  
    history: List[Dict[str, str]]  
  
  
class SessionResetRequest(BaseModel):  
    session_id: str  
  
  
@app.post("/chat", response_model=ChatResponse)  
async def chat(req: ChatRequest):  
    agent = Agent(STATE_STORE, req.session_id)  
    answer = await agent.chat_async(req.prompt)  
    return ChatResponse(response=answer)  
  
  
@app.post("/reset_session")  
async def reset_session(req: SessionResetRequest):  
    if req.session_id in STATE_STORE:  
        del STATE_STORE[req.session_id]  
    hist_key = f"{req.session_id}_chat_history"  
    if hist_key in STATE_STORE:  
        del STATE_STORE[hist_key]  
  
  
@app.get("/history/{session_id}", response_model=ConversationHistoryResponse)  
async def get_conversation_history(session_id: str):  
    history = STATE_STORE.get(f"{session_id}_chat_history", [])  
    return ConversationHistoryResponse(session_id=session_id, history=history)  
  
  
if __name__ == "__main__":  
    uvicorn.run(app, host="0.0.0.0", port=7000)  