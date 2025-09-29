import json
import logging
from typing import Any, Dict, List

from agent_framework import AgentThread, ChatAgent, MCPStreamableHTTPTool
from agent_framework.azure import AzureOpenAIChatClient

from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class Agent(BaseAgent):
    """Agent Framework implementation of a single assistant loop."""

    def __init__(self, state_store: Dict[str, Any], session_id: str, access_token: str | None = None) -> None:
        super().__init__(state_store, session_id)
        self._agent: ChatAgent | None = None
        self._thread: AgentThread | None = None
        self._initialized = False
        self._access_token = access_token

    async def _setup_single_agent(self) -> None:
        if self._initialized:
            return

        if not all([self.azure_openai_key, self.azure_deployment, self.azure_openai_endpoint, self.api_version]):
            raise RuntimeError(
                "Azure OpenAI configuration is incomplete. Ensure AZURE_OPENAI_API_KEY, "
                "AZURE_OPENAI_CHAT_DEPLOYMENT, AZURE_OPENAI_ENDPOINT, and AZURE_OPENAI_API_VERSION are set."
            )

        headers = self._build_headers()
        mcp_tools = await self._maybe_create_tools(headers)

        chat_client = AzureOpenAIChatClient(
            api_key=self.azure_openai_key,
            deployment_name=self.azure_deployment,
            endpoint=self.azure_openai_endpoint,
            api_version=self.api_version,
        )

        instructions = (
            "You are a helpful assistant. You can use multiple tools to find information and answer questions. "
            "Review the tools available to you and use them as needed. You can also ask clarifying questions if "
            "the user is not clear. If customer ask any operations that there's no tool to support, said that you cannot do it. "
            "Never hallunicate any operation that you do not actually do."
        )

        tools = mcp_tools[0] if mcp_tools else None

        self._agent = ChatAgent(
            name="ai_assistant",
            chat_client=chat_client,
            instructions=instructions,
            tools=tools,
            model=self.openai_model_name,
        )

        try:
            await self._agent.__aenter__()
        except Exception:
            self._agent = None
            raise

        await self._log_mcp_tool_details()

        if self.state:
            self._thread = await self._agent.deserialize_thread(self.state)
        else:
            self._thread = self._agent.get_new_thread()

        self._initialized = True

    def _build_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    async def _maybe_create_tools(self, headers: Dict[str, str]) -> List[MCPStreamableHTTPTool] | None:
        if not self.mcp_server_uri:
            logger.warning("MCP_SERVER_URI is not configured; agent will run without MCP tools.")
            return None

        tool = MCPStreamableHTTPTool(
            name="mcp-streamable",
            url=self.mcp_server_uri,
            headers=headers,
            timeout=30,
            request_timeout=30,
        )

        return [tool]

    async def _log_mcp_tool_details(self) -> None:
        # if not self._agent:
        #     return

        mcp_tools = getattr(self._agent, "_local_mcp_tools", None)
        if not mcp_tools:
            logger.debug("No MCP tools registered on the agent; skipping tool inspection.")
            return

        mcp_tool = mcp_tools[0]
        session = getattr(mcp_tool, "session", None)
        print("session ", session)
        if session is None:
            logger.debug("MCP tool session is not available; cannot list tools for debugging.")
            return

        try:
            tool_list = await session.list_tools()
        except Exception as exc:
            logger.exception("Failed to fetch MCP tool metadata: %s", exc)
            return

        if not tool_list or not getattr(tool_list, "tools", None):
            logger.debug("No tools returned from MCP server during inspection.")
            return

        for tool_info in tool_list.tools:
            print(tool_info)
            if tool_info.name == "get_customer_detail":
                try:
                    serialized = tool_info.model_dump()
                except Exception:
                    serialized = {
                        "name": tool_info.name,
                        "description": getattr(tool_info, "description", ""),
                        "inputSchema": getattr(tool_info, "inputSchema", {}),
                    }

                logger.debug(
                    "MCP tool 'get_customer_detail' metadata: %s",
                    json.dumps(serialized, indent=2, sort_keys=True),
                )
                break
        else:
            logger.debug("MCP tool 'get_customer_detail' not found in server tool list.")

    async def chat_async(self, prompt: str) -> str:
        await self._setup_single_agent()

        if not self._agent or not self._thread:
            raise RuntimeError("Agent Framework single agent failed to initialize correctly.")

        response = await self._agent.run(prompt, thread=self._thread)
        assistant_response = response.text

        messages = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": assistant_response},
        ]
        self.append_to_chat_history(messages)

        new_state = await self._thread.serialize()
        self._setstate(new_state)

        return assistant_response
