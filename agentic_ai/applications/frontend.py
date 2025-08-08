import streamlit as st
import requests, uuid, os
from msal_streamlit import login  # small helper shown right after this block  
SCOPE = st.secrets["MCP_SCOPE"]  

BASE_BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:7000")
CHAT_URL = f"{BASE_BACKEND_URL}/chat"
HISTORY_URL = f"{BASE_BACKEND_URL}/history"
SESSION_RESET_URL = f"{BASE_BACKEND_URL}/reset_session"

# ───────────────── helpers ──────────────────
def auth_headers() -> dict:
    tok = st.session_state.get("token")
    return {"Authorization": f"Bearer {tok}"} if tok else {}

# ───────────────── Sidebar ──────────────────
with st.sidebar:
    if "token" not in st.session_state:  
        st.session_state.token = None  
    login_btn = st.button("🔐  Sign-in", disabled=bool(st.session_state.token))  
    if login_btn:  
        st.session_state.token = login(SCOPE)   # ← pops Entra login  
    st.write("Signed-in" if st.session_state.token else "Not signed-in")  

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
    "<h1 style='display:flex; align-items:center;'>AI Chat Assistant 🤖</h1>",
    unsafe_allow_html=True,
)

# ───────────── Load or initialize session ────────────────
if "session_id" not in st.session_state:
    st.session_state["session_id"] = str(uuid.uuid4())
conversation_history = []

# Fetch existing history from backend (only if authenticated)
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

# ───────────────── Chat interaction ─────────────
prompt = st.chat_input("Type a message..." if st.session_state.token else "Sign-in to chat…")
if prompt and st.session_state.token:  
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.spinner("Assistant is thinking..."):
        r = requests.post(
            CHAT_URL,
            json={"session_id": st.session_state["session_id"], "prompt": prompt},
            headers=auth_headers(),
            timeout=60,
        )
        r.raise_for_status()
        answer = r.json()["response"]

    with st.chat_message("assistant"):
        st.markdown(answer)
