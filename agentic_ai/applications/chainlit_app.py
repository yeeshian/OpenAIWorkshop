import os, uuid, json, asyncio, webbrowser, urllib.parse
import chainlit as cl
import websockets
from dotenv import load_dotenv
import msal

load_dotenv()

BASE_BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:7000")
WS_URL = BASE_BACKEND_URL.replace("http", "ws") + "/ws/chat"
DISABLE_AUTH = os.getenv("DISABLE_AUTH", "false").lower() in ("1","true","yes")

async def msal_login() -> str:
    """Login via MSAL device code flow"""
    client_id = os.getenv("CLIENT_ID") or os.getenv("AZURE_AD_CLIENT_ID")
    if not client_id:
        await cl.Message(
            content="❌ **CLIENT_ID not configured**\n\n💡 Set `DISABLE_AUTH=true` for development mode",
            author="system"
        ).send()
        raise RuntimeError("CLIENT_ID must be set for authentication")
    
    authority = os.getenv("AUTHORITY") or "https://login.microsoftonline.com/common/v2.0"
    scopes = [f"{client_id}/.default"]
    
    cache = msal.SerializableTokenCache()
    app = msal.PublicClientApplication(client_id, authority=authority, token_cache=cache)
    
    # Try silent token acquisition first
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(scopes, account=accounts[0])
        if result and "access_token" in result:
            return result["access_token"]
    
    # Use device code flow
    flow = app.initiate_device_flow(scopes=scopes)
    if "user_code" not in flow:
        raise RuntimeError("Failed to create authentication flow")
    
    # ALWAYS show device code prominently
    await cl.Message(
        content=f"🔐 **DEVICE CODE AUTHENTICATION**\n\n"
                f"**📋 ENTER THIS CODE: `{flow['user_code']}`**\n\n"
                f"🌐 **Visit:** {flow['verification_uri']}\n\n"
                f"⏳ Waiting for you to complete authentication...",
        author="system"
    ).send()
    
    # Also try to open browser
    try:
        webbrowser.open(flow['verification_uri'])
        await cl.Message(content="✅ Browser opened automatically", author="system").send()
    except Exception:
        pass
    
    result = app.acquire_token_by_device_flow(flow)
    if not result or "access_token" not in result:
        error_msg = result.get("error_description", "Login failed") if result else "Login failed"
        await cl.Message(content=f"❌ Authentication failed: {error_msg}", author="system").send()
        raise RuntimeError(error_msg)
    
    await cl.Message(content="✅ Authentication successful!", author="system").send()
    return result["access_token"]

@cl.on_chat_start
async def start():
    session_id = str(uuid.uuid4())
    cl.user_session.set("session_id", session_id)
    
    # Handle authentication
    if DISABLE_AUTH:
        token = "dev-local-token"
        await cl.Message(content=f"� **Chat Ready!**\n\nSession: `{session_id}`\n\n🔓 Auth disabled (DEV mode)\n\nAsk me something to get started!").send()
    else:
        try:
            # Show immediate loading message
            loading_msg = await cl.Message(content="🔐 Initializing authentication...", author="system").send()
            
            token = await msal_login()
            
            # Remove loading message and show success
            await loading_msg.remove()
            await cl.Message(content=f"🚀 **Chat Ready!**\n\nSession: `{session_id}`\n\n✅ Authenticated successfully\n\nAsk me something to get started!").send()
            
        except Exception as e:
            await cl.Message(content=f"❌ Authentication failed: {e}\n\n💡 **Tip**: Set `DISABLE_AUTH=true` in your environment for development mode.", author="system").send()
            return
    
    cl.user_session.set("access_token", token)
    
    # open websocket connection and store
    try:
        headers = {}
        if token and token != "dev-local-token":
            headers['Authorization'] = f'Bearer {token}'
        ws = await websockets.connect(WS_URL, additional_headers=headers)
        cl.user_session.set("ws", ws)
        # register session
        await ws.send(json.dumps({"session_id": session_id, "access_token": token}))
        
        async def listener():
            try:
                async for raw in ws:
                    try:
                        data = json.loads(raw)
                        print(f"Received WS message: {data}")  # Debug logging
                    except Exception:
                        continue
                    t = data.get("type")
                    if t == "token":
                        await cl.Message(author="stream", content=data.get("content","")) .send()
                    elif t in ("message","final"):
                        await cl.Message(content=data.get("content",""), author="assistant").send()
                    # Skip tool calls, tool results, errors, and info messages
            except Exception as e:
                print(f"Listener error: {e}")

        asyncio.create_task(listener())
        
    except Exception as e:
        await cl.Message(content=f"❌ Failed to connect to backend: {e}\n\nPlease ensure the backend server is running at: `{BASE_BACKEND_URL}`", author="system").send()

@cl.on_message
async def on_message(msg: cl.Message):
    ws = cl.user_session.get("ws")
    session_id = cl.user_session.get("session_id")
    token = cl.user_session.get("access_token")
    if not ws:
        await cl.Message(content="No websocket.").send()
        return
    payload = {"session_id": session_id, "prompt": msg.content, "access_token": token}
    await ws.send(json.dumps(payload))

@cl.on_stop
async def on_stop():
    ws = cl.user_session.get("ws")
    if ws:
        try:
            await ws.close()
        except Exception:
            pass
import os, uuid, json, asyncio, webbrowser
import chainlit as cl
import websockets
from dotenv import load_dotenv
import msal

load_dotenv()

BASE_BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:7000")
WS_URL = BASE_BACKEND_URL.replace("http", "ws") + "/ws/chat"
DISABLE_AUTH = os.getenv("DISABLE_AUTH", "false").lower() in ("1","true","yes")

async def msal_login() -> str:
    """Login via MSAL device code flow"""
    client_id = os.getenv("CLIENT_ID") or os.getenv("AZURE_AD_CLIENT_ID")
    if not client_id:
        await cl.Message(
            content="❌ **CLIENT_ID not configured**\n\n"
                    "💡 Set `DISABLE_AUTH=true` for development mode",
            author="system"
        ).send()
        raise RuntimeError("CLIENT_ID must be set for authentication")
    
    authority = os.getenv("AUTHORITY") or "https://login.microsoftonline.com/common/v2.0"
    scopes = [f"{client_id}/.default"]
    
    cache = msal.SerializableTokenCache()
    app = msal.PublicClientApplication(client_id, authority=authority, token_cache=cache)
    
    # Try silent token acquisition first
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(scopes, account=accounts[0])
        if result and "access_token" in result:
            return result["access_token"]
    
    # Use device code flow
    flow = app.initiate_device_flow(scopes=scopes)
    if "user_code" not in flow:
        raise RuntimeError("Failed to create authentication flow")
    
    # Show device code and auto-open browser
    try:
        webbrowser.open(flow['verification_uri'])
        await cl.Message(
            content=f"🔐 **Authentication Required**\n\n"
                    f"✅ Browser opened automatically\n\n"
                    f"📋 **Enter this code**: **`{flow['user_code']}`**\n\n"
                    f"🌐 URL: {flow['verification_uri']}\n\n"
                    f"⏳ Waiting for authentication...",
            author="system"
        ).send()
    except Exception:
        await cl.Message(
            content=f"🔐 **Authentication Required**\n\n"
                    f"📱 Visit: {flow['verification_uri']}\n\n"
                    f"📋 **Enter this code**: **`{flow['user_code']}`**\n\n"
                    f"⏳ Waiting for authentication...",
            author="system"
        ).send()
    
    result = app.acquire_token_by_device_flow(flow)
    if not result or "access_token" not in result:
        error_msg = result.get("error_description", "Login failed") if result else "Login failed"
        await cl.Message(content=f"❌ Authentication failed: {error_msg}", author="system").send()
        raise RuntimeError(error_msg)
    
    await cl.Message(content="✅ Authentication successful!", author="system").send()
    return result["access_token"]

@cl.on_chat_start
async def start():
    session_id = str(uuid.uuid4())
    cl.user_session.set("session_id", session_id)
    
    # Handle authentication
    if DISABLE_AUTH:
        token = "dev-local-token"
        await cl.Message(content=f"🚀 **Chat Ready!**\n\nSession: `{session_id}`\n\n🔓 Auth disabled (DEV mode)\n\nAsk me something to get started!").send()
    else:
        try:
            token = await msal_login()
            await cl.Message(content=f"🚀 **Chat Ready!**\n\nSession: `{session_id}`\n\n✅ Authenticated successfully\n\nAsk me something to get started!").send()
        except Exception as e:
            await cl.Message(content=f"❌ Authentication failed: {e}\n\n💡 Set `DISABLE_AUTH=true` for development mode.", author="system").send()
            return
    
    cl.user_session.set("access_token", token)
    
    # open websocket connection and store
    try:
        headers = {}
        if token and token != "dev-local-token":
            headers['Authorization'] = f'Bearer {token}'
        ws = await websockets.connect(WS_URL, extra_headers=headers)
        cl.user_session.set("ws", ws)
        # register session
        await ws.send(json.dumps({"session_id": session_id, "access_token": token}))
        
        async def listener():
            try:
                async for raw in ws:
                    try:
                        data = json.loads(raw)
                    except Exception:
                        continue
                    t = data.get("type")
                    if t == "token":
                        await cl.Message(author="stream", content=data.get("content","")) .send()
                    elif t in ("message","final"):
                        await cl.Message(content=data.get("content",""), author="assistant").send()
                    # Skip tool calls, tool results, errors, and info messages
            except Exception as e:
                print(f"Listener error: {e}")

        asyncio.create_task(listener())
        
    except Exception as e:
        await cl.Message(content=f"❌ Failed to connect to backend: {e}\n\nPlease ensure the backend server is running at: `{BASE_BACKEND_URL}`", author="system").send()

@cl.on_message
async def on_message(msg: cl.Message):
    ws = cl.user_session.get("ws")
    session_id = cl.user_session.get("session_id")
    token = cl.user_session.get("access_token")
    if not ws:
        await cl.Message(content="No websocket.").send()
        return
    payload = {"session_id": session_id, "prompt": msg.content, "access_token": token}
    await ws.send(json.dumps(payload))

@cl.on_stop
async def on_stop():
    ws = cl.user_session.get("ws")
    if ws:
        try:
            await ws.close()
        except Exception:
            pass
