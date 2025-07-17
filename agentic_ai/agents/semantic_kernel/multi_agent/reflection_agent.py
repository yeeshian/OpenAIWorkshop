import asyncio
import re

from semantic_kernel.agents import (
    ChatCompletionAgent,
    GroupChatOrchestration,
    RoundRobinGroupChatManager,
)
from semantic_kernel.agents.runtime import InProcessRuntime
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.connectors.mcp import MCPSsePlugin
from semantic_kernel.contents import ChatMessageContent

from agents.base_agent import BaseAgent  # adjust path


class Agent(BaseAgent):
    def __init__(self, state_store, session_id) -> None:
        super().__init__(state_store, session_id)
        self._agents = None
        self._mcp_plugin = None
        self._initialized = False
        self._customer_id = None

        # ✅ store past turns
        self._conversation_history: list[str] = []

        self._orchestration: GroupChatOrchestration | None = None

    async def setup_agents(self) -> None:
        if self._initialized:
            return

        self._mcp_plugin = MCPSsePlugin(
            name="ContosoMCP",
            description="Contoso MCP Plugin",
            url=self.mcp_server_uri,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        await self._mcp_plugin.connect()

        primary_agent = ChatCompletionAgent(
            service=AzureChatCompletion(deployment_name=self.azure_deployment),
            name="PrimaryAgent",
            description="You are a helpful assistant answering customer questions for internet provider Contosso.",
            instructions=(
                "You are a helpful assistant. Use the available MCP tools to find info and answer questions. "
                "You send your response to the secondary agent for review before replying to the user."
                "If there was context from previous turns such as customer ID, include it to find best answer in your response."
                "If you couldn't find customer ID from previous context, and the response from secondary agent is not sure about it, **ONLY THEN** ask user to provide it."
                "Again don't assume ID, only pay close attention to previous chat context and secondary agent's response to see if user provided it"
                "You only ask the user to provide ID, if none of the conversation context with user or secondary has it."
                "Respond to the user whatever was final answer from the secondary agent."
            ),
            plugins=[self._mcp_plugin],
        )

        secondary_agent = ChatCompletionAgent(
            service=AzureChatCompletion(deployment_name=self.azure_deployment),
            name="SecondaryAgent",
            description="You are a supervisor assistant who the primary agent reports to before answering user",
            instructions=(
                "Make sure you double check the primary agent's response for accuracy and completeness, you can provide improvement feedback if needed."
                "If you are not sure of customer ID, use the one from primary agent's response."
                "Ask clarifying questions if the user is not clear, like if unsure about customer ID, see if primary agent used any ID to answer the question first time, if yes use that ID."
                "If primary agent also has been unsure and you can't find it either from previous context **ONLY THEN** ask user to provide it."
                "After reviewing, suggest the primary response what to answer to the user finally and include details on specifics such as invoice, bill, refund, etc promotion offers."
            ),
            plugins=[self._mcp_plugin],
        )

        self._agents = [primary_agent, secondary_agent]
        self._initialized = True

        if self._orchestration is None:
            def agent_response_callback(message: ChatMessageContent) -> None:
                print(f"**{message.name}**\n{message.content}")

            self._orchestration = GroupChatOrchestration(
                members=self._agents,
                manager=RoundRobinGroupChatManager(max_rounds=3),
                agent_response_callback=agent_response_callback,
            )

    def get_agents(self):
        if not self._initialized:
            raise RuntimeError("Call setup_agents() first!")
        return self._agents

    async def cleanup(self):
        if self._mcp_plugin:
            try:
                await self._mcp_plugin.close()
            except Exception:
                pass
        self._mcp_plugin = None
        self._initialized = False
        self._agents = None

    async def chat_async(self, user_input: str) -> str:
        match = re.search(r"customer\s*id[:\s]*([0-9]+)", user_input, re.IGNORECASE)
        if match:
            self._customer_id = match.group(1)

        if self._customer_id and "customer id" not in user_input.lower():
            user_input = f"Customer ID: {self._customer_id}\n{user_input}"

        await self.setup_agents()

        # ✅ Append new user input to the stored history
        self._conversation_history.append(f"User: {user_input}")

        # ✅ Combine whole history into a single task string
        task_text = "\n".join(self._conversation_history)

        runtime = InProcessRuntime()
        runtime.start()

        final_result = ""
        try:
            orchestration_result = await self._orchestration.invoke(
                task=task_text,
                runtime=runtime
            )
            final_result = await orchestration_result.get()
        except Exception as e:
            final_result = f"Error during orchestration: {e}"
        finally:
            await runtime.stop_when_idle()

        # ✅ Store assistant response in the history too
        self._conversation_history.append(f"Assistant: {final_result}")
        # # Fallback if orchestrator did not produce final answer
        # if not final_answer:
        #     final_answer = "Sorry, the team could not reach a conclusion within the allotted turns."



        # ✅ Also store for UI purposes if needed by your frontend
        self.append_to_chat_history([
            {"role": "user", "content": str (user_input)},
            {"role": "assistant", "content": str (final_result)},
        ])

        return str(final_result)


# # --------------------------- Manual test helper --------------------------- #
# if __name__ == "__main__":
#     async def _demo():
#         dummy_state = {}
#         agent = Agent(dummy_state, session_id="demo")
#         while True:
#             question = input(">>> ")
#             if question.lower() in {"exit", "quit"}:
#                 break
#             answer = await agent.chat_async(question)
#             print("\n>>> Assistant reply:\n", answer)

#     asyncio.run(_demo())