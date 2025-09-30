import streamlit as st  
import requests  
import uuid  
import os  
import json, threading, time
from msal_streamlit import login  
from dotenv import load_dotenv  
try:
    import websocket  # websocket-client
except ImportError:
    websocket = None
  
load_dotenv()  
  
BASE_BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:7000")  
CHAT_URL = f"{BASE_BACKEND_URL}/chat"  
HISTORY_URL = f"{BASE_BACKEND_URL}/history"  
SESSION_RESET_URL = f"{BASE_BACKEND_URL}/reset_session"  
WS_URL = BASE_BACKEND_URL.replace("http", "ws") + "/ws/chat"
DISABLE_AUTH = os.getenv("DISABLE_AUTH", "true").lower() in ("1", "true", "yes")
  
# ───────────────── helpers ──────────────────  
def auth_headers() -> dict:  
    tok = st.session_state.get("token")  
    return {"Authorization": f"Bearer {tok}"} if tok else {}  
  
# ───────────────── Sidebar ──────────────────  
with st.sidebar:  
    if "token" not in st.session_state:
        st.session_state.token = None

    if DISABLE_AUTH:
        # Auto-provision a pseudo token so rest of UI works
        if not st.session_state.token:
            st.session_state.token = "dev-local-token"
        st.success("Auth disabled (DEV mode)")
    else:
        login_btn = st.button("🔐  Sign-in", disabled=bool(st.session_state.token))  
        if login_btn:  
            st.session_state.token = login()  
            st.write(st.session_state.get("token"))  
        st.write("Signed-in" if st.session_state.token else "Not signed-in")  
        if st.button("🚪 Sign out", disabled=not st.session_state.token):  
            st.session_state.token = None  
            if "session_id" in st.session_state:  
                st.session_state["session_id"] = str(uuid.uuid4())  
            st.success("Signed out.")  

    st.title("⚙️  Controls")  
    if st.button("🗘  New chat", key="new_chat") and st.session_state.get("session_id"):  
        requests.post(  
            SESSION_RESET_URL,  
            json={"session_id": st.session_state["session_id"]},  
            headers=auth_headers(),  
            timeout=20,  
        )  
  
# ───────────────── Page title ────────────────  
st.markdown(  
    "<h1 style='display:flex; align-items:center;'>🤖 AI Multi-Agent Assistant</h1>",  
    unsafe_allow_html=True,  
)  
  
# ───────────── Load or initialize session ────────────────  
if "session_id" not in st.session_state:  
    st.session_state["session_id"] = str(uuid.uuid4())  
  
conversation_history = []  
  
# Fetch existing history from backend  
if st.session_state.token:  
    try:  
        response = requests.get(  
            f"{HISTORY_URL}/{st.session_state['session_id']}",  
            headers=auth_headers(),  
            timeout=20,  
        )  
        if response.status_code == 200:  
            history_data = response.json()  
            conversation_history = history_data.get("history", [])  
    except Exception:  
        pass  
  
# ───────────────── Chat history ─────────────  
for msg in conversation_history:  
    with st.chat_message(msg["role"]):  
        st.markdown(msg["content"])  
  
# ───────────────── WebSocket state ─────────────
if "ws_events" not in st.session_state:
    st.session_state.ws_events = []
if "ws_connected" not in st.session_state:
    st.session_state.ws_connected = False
if "ws" not in st.session_state:
    st.session_state.ws = None
if "ws_started" not in st.session_state:
    st.session_state.ws_started = False
if "magentic_state" not in st.session_state:
    st.session_state.magentic_state = {
        "orchestrator_messages": [],
        "agent_outputs": {},
        "current_agent": None,
    }

def _ensure_ws():
    if websocket is None:
        return False
    if st.session_state.ws_connected:
        return True
    if st.session_state.ws_started:
        return True
    def on_message(ws, message):
        try:
            data = json.loads(message)
            st.session_state.ws_events.append(data)
        except Exception:
            pass
    def on_open(ws):
        st.session_state.ws_connected = True
        payload = {
            "session_id": st.session_state["session_id"],
            "access_token": st.session_state.get("token"),
        }
        ws.send(json.dumps(payload))
    def on_error(ws, error):
        pass
    def on_close(ws, close_code, reason):
        st.session_state.ws_connected = False

    st.session_state.ws_started = True
    st.session_state.ws = websocket.WebSocketApp(
        WS_URL,
        on_message=on_message,
        on_open=on_open,
        on_error=on_error,
        on_close=on_close,
    )
    threading.Thread(target=st.session_state.ws.run_forever, daemon=True).start()
    time.sleep(0.5)
    return st.session_state.ws_connected

def send_ws_prompt(prompt: str) -> bool:
    if not _ensure_ws():
        return False
    if not st.session_state.ws_connected:
        return False
    try:
        st.session_state.ws_events.clear()
        st.session_state.magentic_state = {
            "orchestrator_messages": [],
            "agent_outputs": {},
            "current_agent": None,
        }
        payload = {
            "session_id": st.session_state["session_id"],
            "prompt": prompt,
            "access_token": st.session_state.get("token"),
        }
        st.session_state.ws.send(json.dumps(payload))
        return True
    except Exception:
        return False

# ───────────────── Event display helpers ─────────────
def render_magentic_events(events):
    """Render Magentic workflow events with collapsible sections."""
    state = st.session_state.magentic_state
    
    for ev in events:
        t = ev.get("type")
        
        if t == "orchestrator":
            # Orchestrator planning/thinking
            kind = ev.get("kind", "message")
            content = ev.get("content", "")
            if content:
                state["orchestrator_messages"].append({"kind": kind, "content": content})
        
        elif t == "agent_start":
            # Participant agent starting
            agent_id = ev.get("agent_id")
            state["current_agent"] = agent_id
            if agent_id not in state["agent_outputs"]:
                state["agent_outputs"][agent_id] = {"tokens": [], "messages": []}
        
        elif t == "agent_token":
            # Streaming token from participant
            agent_id = ev.get("agent_id")
            token = ev.get("content", "")
            if agent_id in state["agent_outputs"]:
                state["agent_outputs"][agent_id]["tokens"].append(token)
        
        elif t == "agent_message":
            # Complete message from participant
            agent_id = ev.get("agent_id")
            role = ev.get("role", "assistant")
            content = ev.get("content", "")
            if agent_id in state["agent_outputs"]:
                state["agent_outputs"][agent_id]["messages"].append({
                    "role": role,
                    "content": content
                })
        
        elif t == "final_result":
            # Final workflow output
            pass  # Handled separately
    
    # Render orchestrator section
    if state["orchestrator_messages"]:
        with st.expander("🧠 Orchestrator Planning", expanded=True):
            for msg in state["orchestrator_messages"]:
                kind = msg["kind"]
                icon = "📋" if kind == "plan" else "📊" if kind == "progress" else "✅"
                st.markdown(f"{icon} **{kind.upper()}**")
                st.markdown(msg["content"])
                st.divider()
    
    # Render participant agent sections
    for agent_id, data in state["agent_outputs"].items():
        agent_name = agent_id.replace("_", " ").title()
        is_current = (agent_id == state["current_agent"])
        
        with st.expander(f"🤖 {agent_name}" + (" (active)" if is_current else ""), expanded=is_current):
            # Show streaming tokens if active
            if data["tokens"]:
                st.markdown("**Thinking...**")
                st.write("".join(data["tokens"]))
            
            # Show complete messages
            for msg in data["messages"]:
                role_icon = "👤" if msg["role"] == "user" else "🔧" if "tool" in msg["role"] else "💬"
                st.markdown(f"{role_icon} **{msg['role'].upper()}**")
                st.markdown(msg["content"])
                st.divider()

# ───────────────── Main event rendering ─────────────
def render_stream_events():
    """Render real-time events from WebSocket."""
    events = st.session_state.ws_events
    if not events:
        return None
    
    # Separate Magentic events from legacy events
    magentic_events = [e for e in events if e.get("type") in (
        "orchestrator", "agent_start", "agent_token", "agent_message", "final_result"
    )]
    other_events = [e for e in events if e.get("type") not in (
        "orchestrator", "agent_start", "agent_token", "agent_message", "final_result"
    )]
    
    # Render Magentic workflow visualization
    if magentic_events:
        render_magentic_events(magentic_events)
    
    # Handle legacy/simple events
    final_answer = None
    for ev in other_events:
        t = ev.get("type")
        if t == "token":
            pass  # Handled in agent streaming
        elif t == "message":
            r = ev.get("role", "assistant")
            if r == "assistant":
                final_answer = ev.get("content", "")
        elif t == "final":
            final_answer = ev.get("content")
        elif t == "error":
            st.error(ev.get("message"))
        elif t == "info":
            st.caption(ev.get("message"))
    
    # Check for final result in Magentic events
    for ev in magentic_events:
        if ev.get("type") == "final_result":
            final_answer = ev.get("content", "")
    
    return final_answer

st.divider()

# ───────────────── Chat interaction (WS preferred, REST fallback) ─────────────  
prompt = st.chat_input("Type a message..." if st.session_state.token else "Sign-in to chat…")  
if prompt and st.session_state.token:  
    with st.chat_message("user"):  
        st.markdown(prompt)
    
    used_ws = send_ws_prompt(prompt)
    if not used_ws:
        # REST fallback
        with st.spinner("Assistant (REST)…"):
            r = requests.post(
                CHAT_URL,
                json={"session_id": st.session_state["session_id"], "prompt": prompt},
                headers=auth_headers(),
                timeout=180,  # Increased from 60s to 180s for multi-agent workflows
            )
            r.raise_for_status()
            answer = r.json()["response"]
        with st.chat_message("assistant"):
            st.markdown(answer)
    else:
        # WebSocket streaming
        placeholder = st.empty()
        with placeholder.container():
            with st.spinner("🔄 Multi-agent workflow in progress..."):
                timeout = time.time() + 180
                while time.time() < timeout:
                    answer = render_stream_events()
                    if answer:
                        break
                    done = any(e.get("type") == "done" for e in st.session_state.ws_events)
                    if done:
                        answer = render_stream_events()
                        break
                    time.sleep(0.3)
                    st.rerun()
        
        # Final answer display
        if answer:
            with st.chat_message("assistant"):
                st.markdown(answer)
