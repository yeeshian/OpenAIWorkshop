# ui/chainlit_backend_stream.py
import os
import uuid
import json
import asyncio
import chainlit as cl
import websockets

# Backend URL, e.g., ws://localhost:7000
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:7000")
# Convert to ws:// if http:// given
if BACKEND_URL.startswith("http://"):
    WS_BASE = "ws://" + BACKEND_URL[len("http://"):]
elif BACKEND_URL.startswith("https://"):
    WS_BASE = "wss://" + BACKEND_URL[len("https://"):]
else:
    WS_BASE = BACKEND_URL

WS_CHAT_URL = f"{WS_BASE}/ws/chat"

@cl.on_chat_start
async def on_chat_start():
    # per-user session id
    session_id = str(uuid.uuid4())
    cl.user_session.set("session_id", session_id)
    await cl.Message(f"Session: {session_id}\nHow can I help you?").send()

@cl.on_message
async def on_message(message: cl.Message):
    session_id = cl.user_session.get("session_id")

    # Prepare messages
    progress_msg = cl.Message(content="")
    assistant_msg = cl.Message(content="")
    await progress_msg.send()  # create placeholder
    await assistant_msg.send()

    # Optional: If your backend WS requires token, set it here
    # headers = [("Authorization", f"Bearer {YOUR_TOKEN}")]
    headers = None

    async def send_prompt():
        async with websockets.connect(WS_CHAT_URL, additional_headers=headers) as ws:
            payload = {
                "session_id": session_id,
                "prompt": message.content,
                # "access_token": "...",  # include if your backend forwards to MCP
            }
            await ws.send(json.dumps(payload))

            while True:
                try:
                    raw = await ws.recv()
                except websockets.ConnectionClosed:
                    break

                try:
                    data = json.loads(raw)
                except Exception:
                    continue

                typ = data.get("type")
                if typ == "progress":
                    # side-channel MCP tool progress
                    line = f"[{data.get('percent', 0)}%] {data.get('message', '')}\n"
                    await progress_msg.stream_token(line)
                elif typ == "token":
                    await assistant_msg.stream_token(data.get("content", ""))
                elif typ == "message":
                    await assistant_msg.stream_token("\n" + data.get("content", ""))
                elif typ == "final":
                    # Final assistant message
                    content = data.get("content", "")
                    if content:
                        await assistant_msg.stream_token("\n" + content)
                elif typ == "done":
                    # finish
                    break
                elif typ == "error":
                    await assistant_msg.stream_token(f"\n[Error] {data.get('message','')}")
                    break

    await send_prompt()

    # finalize messages
    await progress_msg.update()
    await assistant_msg.update()