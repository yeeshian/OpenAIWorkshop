import logging
from typing import Any, Dict

from agent_framework import AgentThread, ChatAgent, MCPStreamableHTTPTool
from agent_framework.azure import AzureOpenAIChatClient

from agents.base_agent import BaseAgent


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

        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"

        mcp_tool = None
        if self.mcp_server_uri:
            mcp_tool = MCPStreamableHTTPTool(
                name="mcp-streamable",
                url=self.mcp_server_uri,
                headers=headers,
                timeout=30,
                request_timeout=30,
            )
        else:
            logging.warning("MCP_SERVER_URI is not configured; agent will run without MCP tools.")

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

        tools = [mcp_tool] if mcp_tool else None

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

        if self.state:
            self._thread = await self._agent.deserialize_thread(self.state)
        else:
            self._thread = self._agent.get_new_thread()

        self._initialized = True

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
