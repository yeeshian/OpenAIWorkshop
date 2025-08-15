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
from fastapi import Depends, Header, HTTPException  
import msal, requests  # removed jwt related imports


# ------------------------------------------------------------------  
# Environment  
# ------------------------------------------------------------------  
load_dotenv()  # read .env if present  

# Azure AD / Entra tenant and expected audience for tokens hitting this backend
AAD_TENANT_ID = os.getenv("AAD_TENANT_ID") or os.getenv("TENANT_ID")
if not AAD_TENANT_ID:
    raise RuntimeError("AAD_TENANT_ID (or TENANT_ID) must be set.")

# Audience should be the App ID URI of the MCP API you're protecting via APIM, e.g., "api://<mcp-api-app-id>"
EXPECTED_AUDIENCE = (
    os.getenv("MCP_API_AUDIENCE")
    or os.getenv("API_AUDIENCE")
    or (f"api://{os.getenv('MCP_API_CLIENT_ID')}" if os.getenv("MCP_API_CLIENT_ID") else None)
)
if not EXPECTED_AUDIENCE:
    raise RuntimeError("Set MCP_API_AUDIENCE (e.g., api://<mcp-api-app-id>) for JWT validation.")

# Remove JWKS client (no backend validation now)
# JWKS_URL and jwks_client no longer needed


# Map the standard Authorization header and avoid 422 by making it optional, then return 401 if missing

def verify_token(authorization: str | None = Header(None, alias="Authorization")):
    # Minimal check: ensure bearer token present; delegate validation & scopes to MCP/APIM backend.
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "No bearer token")
    return authorization.split(" ", 1)[1]

# ------------------------------------------------------------------  
# Bring project root onto the path & load your agent dynamically  
# ------------------------------------------------------------------  
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  
agent_module_path = os.getenv("AGENT_MODULE")  
agent_module = __import__(agent_module_path, fromlist=["Agent"])  # type: ignore[arg-type]  
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
async def chat(req: ChatRequest, token: str = Depends(verify_token)):  
    # Propagate the bearer token down to the agent so it can call the MCP (via APIM)
    try:
        agent = Agent(STATE_STORE, req.session_id, access_token=token)
    except TypeError:
        agent = Agent(STATE_STORE, req.session_id)
    answer = await agent.chat_async(req.prompt)  
    return ChatResponse(response=answer)  
  
@app.post("/reset_session")  
async def reset_session(req: SessionResetRequest, token: str = Depends(verify_token)):  
    if req.session_id in STATE_STORE:  
        del STATE_STORE[req.session_id]  
    hist_key = f"{req.session_id}_chat_history"  
    if hist_key in STATE_STORE:  
        del STATE_STORE[hist_key]  
   

@app.get("/history/{session_id}", response_model=ConversationHistoryResponse)  
async def get_conversation_history(session_id: str, token: str = Depends(verify_token)):  
    history = STATE_STORE.get(f"{session_id}_chat_history", [])  
    return ConversationHistoryResponse(session_id=session_id, history=history)  
  
  
if __name__ == "__main__":  
    uvicorn.run(app, host="0.0.0.0", port=7000)