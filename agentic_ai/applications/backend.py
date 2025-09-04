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
from typing import Dict, List, Any, Optional
  
import uvicorn  
from fastapi import FastAPI  
from pydantic import BaseModel  
from dotenv import load_dotenv  
from fastapi import FastAPI, Depends, Header, WebSocket, WebSocketDisconnect

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


def verify_token(authorization: str | None = Header(None, alias="Authorization")):
    pass
    # Minimal check: ensure bearer token present; delegate validation & scopes to MCP/APIM backend.
    # if not authorization or not authorization.startswith("Bearer "):
    #     raise HTTPException(401, "No bearer token")
    # return authorization.split(" ", 1)[1]

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
# ──────────────────────────────────────────────────────────────
# NEW: WebSocket streaming endpoint
#   - Wraps agent.run_stream
#   - Streams tokens, messages, tool calls, and side-channel progress
# ──────────────────────────────────────────────────────────────
@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket):
    # Accept without auth first; if you need auth, read header:
    # auth = ws.headers.get("Authorization")
    await ws.accept()
    try:
        while True:
            # Expect {"session_id": "...", "prompt": "...", "access_token": "..."} (token optional)
            data = await ws.receive_json()
            session_id = data.get("session_id")
            prompt = data.get("prompt")
            token = data.get("access_token")  # optional

            if not session_id or not prompt:
                await ws.send_json({"type": "error", "message": "Missing session_id or prompt"})
                continue

            # Create agent for this session
            try:
                agent = Agent(STATE_STORE, session_id, access_token=token)
            except TypeError:
                agent = Agent(STATE_STORE, session_id)

            # Side-channel progress sink
            async def progress_sink(ev: dict):
                # ev = {"type":"progress","tool":"...","percent": int, "message": "..."}
                await ws.send_json(ev)

            agent.set_progress_sink(progress_sink)

            # Stream events from Autogen
            try:
                async for event in agent.chat_stream(prompt):
                    print("event: \n", event)
                    # Serialize and forward
                    evt = await serialize_autogen_event(event)
                    if evt:
                        await ws.send_json(evt)
                # Indicate done for this prompt
                await ws.send_json({"type": "done"})
            except Exception as e:
                await ws.send_json({"type": "error", "message": str(e)})
    except WebSocketDisconnect:
        pass


# Helper: serialize Autogen streaming events to JSON
async def serialize_autogen_event(event: Any) -> Optional[dict]:
    """
    Convert Autogen streaming event (BaseChatMessage | BaseAgentEvent | Response) to a JSON-friendly dict.
    """
    try:
        # Lazy imports to avoid hard dep here
        from autogen_agentchat.messages import TextMessage, ToolCallSummaryMessage, HandoffMessage, StructuredMessage
        from autogen_agentchat.messages import ModelClientStreamingChunkEvent, ThoughtEvent, ToolCallRequestEvent, ToolCallExecutionEvent
        from autogen_agentchat.base import Response

        if isinstance(event, ModelClientStreamingChunkEvent):
            return {"type": "token", "content": event.content}
        if isinstance(event, TextMessage):
            if event.source != "user":
                return {"type": "message", "role": "assistant", "content": event.content}
        if isinstance(event, ThoughtEvent):
            return {"type": "thought", "content": event.content}
        if isinstance(event, ToolCallRequestEvent):
            # includes FunctionCall list
            calls = []

            for c in event.content:
                try:
                    calls.append({"name": c.name, "arguments": c.arguments})
                except Exception:
                    pass
            return {"type": "tool_call", "calls": calls}
        if isinstance(event, ToolCallExecutionEvent):
            # results list
            results = []
            for r in event.content:
                try:
                    results.append({"is_error": r.is_error, "content": r.content, "name": r.name})
                except Exception:
                    pass
            return {"type": "tool_result", "results": results}
        if isinstance(event, ToolCallSummaryMessage):
            return {"type": "tool_summary", "content": event.content}
        if isinstance(event, HandoffMessage):
            return {"type": "handoff", "target": event.target, "content": getattr(event, "content", "")}
        if isinstance(event, StructuredMessage):
            return {"type": "structured", "content": getattr(event, "content", {})}
        if isinstance(event, Response):
            print("final response message", event.content)

            # Final assistant message in Response.chat_message
            msg = event.chat_message
            if hasattr(msg, "content"):
                return {"type": "final", "content": getattr(msg, "content")}
            return {"type": "final"}
        # Fallthrough: ignore unknown types
        return None
    except Exception:
        return None

  
  
if __name__ == "__main__":  
    uvicorn.run(app, host="0.0.0.0", port=7000)