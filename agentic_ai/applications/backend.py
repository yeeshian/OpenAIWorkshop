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
import msal, jwt, requests  
from jwt import PyJWKClient, decode as jwt_decode  


# ------------------------------------------------------------------  
# Environment  
# ------------------------------------------------------------------  
load_dotenv()  # read .env if present  

# Azure AD / Entra tenant and expected audience for tokens hitting this backend
AAD_TENANT_ID = os.getenv("AAD_TENANT_ID") or os.getenv("TENANT_ID")
if not AAD_TENANT_ID:
    raise RuntimeError("AAD_TENANT_ID (or TENANT_ID) must be set.")

# Audience should be the App ID URI of the MCP API you're protecting via APIM, e.g. "api://<mcp-api-app-id>"
EXPECTED_AUDIENCE = (
    os.getenv("MCP_API_AUDIENCE")
    or os.getenv("API_AUDIENCE")
    or (f"api://{os.getenv('MCP_API_CLIENT_ID')}" if os.getenv("MCP_API_CLIENT_ID") else None)
)
if not EXPECTED_AUDIENCE:
    raise RuntimeError("Set MCP_API_AUDIENCE (e.g., api://<mcp-api-app-id>) for JWT validation.")

JWKS_URL = f"https://login.microsoftonline.com/{AAD_TENANT_ID}/discovery/v2.0/keys"
jwks_client = PyJWKClient(JWKS_URL)


def verify_token(auth: str = Header(...)):
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(401, "No bearer token")
    token = auth.split(" ", 1)[1]
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token).key
        decoded = jwt_decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=EXPECTED_AUDIENCE,
            options={"verify_exp": True},
        )
        required_scope = os.getenv("REQUIRED_SCOPE")  # optional, e.g. "contoso.mcp.fullaccess"
        if required_scope:
            scp = decoded.get("scp") or ""
            roles = decoded.get("roles") or []
            scopes = scp.split() if isinstance(scp, str) else scp
            has_scope = required_scope in scopes
            has_role = isinstance(roles, list) and required_scope in roles
            if not (has_scope or has_role):
                raise HTTPException(403, "Insufficient scope")
        return token  # pass-through original string
    except Exception as ex:
        raise HTTPException(401, f"Token invalid: {ex}")

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