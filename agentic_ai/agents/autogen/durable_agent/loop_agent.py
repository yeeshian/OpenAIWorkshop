import os  
from dotenv import load_dotenv  
from typing import Any, Dict
from autogen_agentchat.agents import AssistantAgent  
from autogen_agentchat.teams import RoundRobinGroupChat  
from autogen_agentchat.conditions import TextMessageTermination  
from autogen_core import CancellationToken  
from autogen_ext.models.openai import AzureOpenAIChatCompletionClient  
from autogen_ext.tools.mcp import StreamableHttpServerParams, mcp_server_tools  
from agents.base_agent import BaseAgent    
import threading, asyncio, uuid
from datetime import datetime,timezone  
from autogen_core.model_context import BufferedChatCompletionContext
import json

load_dotenv()  

# NEW imports
import asyncio, threading, time
from typing import Any, Dict



# ---------------------------------------------------------------------
# 1.  User-visible tool (LLM will call this)
# ---------------------------------------------------------------------
async def activate_new_line(customer_id: str, phone_number: str) -> str:
    """
    Handle the activation of a new line for a customer.

    The operation is long-running (a few minutes).  
    Immediately acknowledge that the task was scheduled; the customer will be
    notified once activation is complete.
    """
    # Body never executed – see wrapper registration further below.
# ───────────────────────────────────────────────────────────────────────
# 2)  internal helper – does the real scheduling
# ───────────────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------
# 2.  Internal helper, does the real scheduling
# ---------------------------------------------------------------------
async def _activate_new_line_impl(
    customer_id: str,
    phone_number: str,
    *,
    __session_id__: str,
    __state_store__: Dict[str, Any],
) -> str:
    """
    Internal helper invoked by wrapper; identical semantics but with context.
    """

    # ── background job that will run AFTER 20 s ──────────────────────


    async def _post_completion() -> None:
        await asyncio.sleep(20)                              # 1️⃣ simulate work

        # 2️⃣ Load the persisted TeamState dict
        team_state: dict[str, Any] | None = __state_store__.get(__session_id__)
        if team_state is None:
            return                                           # session was wiped

        # 3️⃣ Compute helper refs
        ai_ctx   = team_state["agent_states"]["ai_assistant"]["agent_state"]["llm_context"]["messages"]
        thread   = team_state["agent_states"]["RoundRobinGroupChatManager"]["message_thread"]

        # 4️⃣ Build a NEW tool-call id & arguments
        new_call_id = f"call_{uuid.uuid4().hex}"
        arguments_json = json.dumps(
            {"customer_id": customer_id, "phone_number": phone_number}
        )

        # 5️⃣ Tool-CALL message  (AssistantMessage / ToolCallRequestEvent)
        call_msg_assistant = {
            "content": [
                {
                    "id": new_call_id,
                    "arguments": arguments_json,
                    "name": "activate_new_line_result_update",
                }
            ],
            "thought": None,
            "source": "ai_assistant",
            "type": "AssistantMessage",
        }
        call_msg_thread = {
            "id": str(uuid.uuid4()),
            "source": "ai_assistant",
            "models_usage": None,
            "metadata": {},
            "created_at": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "content": call_msg_assistant["content"],
            "type": "ToolCallRequestEvent",
        }

        # 6️⃣ EXECUTION / result message
        exec_payload = {
            "content": (
                f"✅ Activation complete – customer {customer_id}, "
                f"phone {phone_number} is now live."
            ),
            "name": "activate_new_line_result_update",
            "call_id": new_call_id,
            "is_error": False,
        }
        exec_msg_assistant = {
            "content": [exec_payload],
            "type": "FunctionExecutionResultMessage",
        }
        exec_msg_thread = {
            "id": str(uuid.uuid4()),
            "source": "ai_assistant",
            "models_usage": None,
            "metadata": {},
            "created_at": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "content": [exec_payload],
            "type": "ToolCallExecutionEvent",
        }

        # 7️⃣ Append to assistant LLM context  (keeps order)
        ai_ctx.extend([call_msg_assistant, exec_msg_assistant])

        # 8️⃣ Append to group-chat message thread
        thread.extend([call_msg_thread, exec_msg_thread])

        # 9️⃣ Persist updated state
        __state_store__[__session_id__] = team_state
    # kick off background task in a daemon thread
    threading.Thread(
        target=lambda: asyncio.run(_post_completion()),
        daemon=True,
    ).start()

    # Immediate (first) response shown to the user
    return (
        "🔔 Background task scheduled. "
        "Activation will take a few minutes; you will be notified once it is done."
    )
# ---------------------------------------------------------------------------
class Agent(BaseAgent):  
    def __init__(self, state_store, session_id, access_token: str | None = None) -> None:  
        super().__init__(state_store, session_id)  
        self.loop_agent = None  
        self._initialized = False  
        self._access_token = access_token
  
    async def _setup_loop_agent(self) -> None:  
        """Initialize the assistant and tools once."""  
        if self._initialized:  
            return  
  
        headers = {"Content-Type": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
  
        server_params = StreamableHttpServerParams(  
            url=self.mcp_server_uri,  
            headers=headers,  
            timeout=30  
        )  
  
        # Fetch tools (async)  
        tools = await mcp_server_tools(server_params)  

        async def _activate_wrapper(customer_id: str, phone_number: str) -> str:
            # Call internal helper with conversation context
            return await _activate_new_line_impl(
                customer_id,
                phone_number,
                __session_id__=self.session_id,
                __state_store__=self.state_store,
            )

        # Copy metadata so AssistantAgent sees the right signature/docs
        _activate_wrapper.__name__ = activate_new_line.__name__
        _activate_wrapper.__doc__  = activate_new_line.__doc__
        _activate_wrapper.__annotations__ = activate_new_line.__annotations__

        tools.append(_activate_wrapper)     # AFTER tools = await mcp_server_tools()
        # Set up the OpenAI/Azure model client  
        model_client = AzureOpenAIChatCompletionClient(  
            api_key=self.azure_openai_key,  
            azure_endpoint=self.azure_openai_endpoint,  
            api_version=self.api_version,  
            azure_deployment=self.azure_deployment,  
            model=self.openai_model_name,  
        )  
  
        # Set up the assistant agent
        model_context = BufferedChatCompletionContext(buffer_size=10)  
        agent = AssistantAgent(  
            name="ai_assistant",  
            model_client=model_client,  
            model_context=model_context,
            tools=tools,  
            system_message=(  
                "You are a helpful assistant. You can use multiple tools to find information and answer questions. "  
                "Review the tools available to you and use them as needed. You can also ask clarifying questions if "  
                "the user is not clear."  
            )  
        )  
  
        # Set the termination condition: stop when agent answers as itself  
        termination_condition = TextMessageTermination("ai_assistant")  
  
        self.loop_agent = RoundRobinGroupChat( 
            [agent],  
            termination_condition=termination_condition,  
        )  
  
        if self.state:  
            await self.loop_agent.load_state(self.state)  
        self._initialized = True  
  
    async def chat_async(self, prompt: str) -> str:  
        """Ensure agent/tools are ready and process the prompt."""  
        await self._setup_loop_agent()  
  
        response = await self.loop_agent.run(task=prompt, cancellation_token=CancellationToken())  
        assistant_response = response.messages[-1].content  
  
        messages = [  
            {"role": "user", "content": prompt},  
            {"role": "assistant", "content": assistant_response}  
        ]  
        self.append_to_chat_history(messages)  
  
        # Update/store latest agent state  
        new_state = await self.loop_agent.save_state()  
        print(f"Updated state for session {self.session_id}: {new_state}")
        self._setstate(new_state)  
  
        return assistant_response