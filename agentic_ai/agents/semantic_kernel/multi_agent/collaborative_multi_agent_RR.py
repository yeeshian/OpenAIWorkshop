import asyncio
import logging
from typing import Optional, Dict, List, override
from collections import defaultdict

from base_agent import BaseAgent
from semantic_kernel import Kernel
from semantic_kernel.agents import Agent, ChatCompletionAgent, GroupChatOrchestration
from semantic_kernel.agents.orchestration.group_chat import BooleanResult, GroupChatManager, MessageResult, StringResult
from semantic_kernel.agents.runtime import InProcessRuntime
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.connectors.ai.function_choice_behavior import FunctionChoiceBehavior
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.connectors.mcp import MCPSsePlugin
from semantic_kernel.contents import AuthorRole, ChatHistory, ChatMessageContent
from semantic_kernel.functions import KernelArguments
from semantic_kernel.kernel import Kernel
from semantic_kernel.prompt_template import KernelPromptTemplate, PromptTemplateConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

class ContosoGroupChatManager(GroupChatManager):
    """Custom group chat manager for Contoso agents."""

    service: ChatCompletionClientBase
    topic: str

    termination_prompt: str = (
        "You are a Contoso support mediator. Check if the message contains a final answer.\n"
        "Return True if the message starts with 'FINAL ANSWER:', False otherwise.\n"
        "\nMessage: {{$lastmessage}}"
    )

    selection_prompt: str = (
        "You are a Contoso support mediator. Select the next participant based on these rules:\n"
        "- If message starts with anything relating to billing, crm-billing, select crm_billing\n"
        "- If message starts with 'product_promotions:', select product_promotions\n"
        "- If message starts with 'security_authentication:', select security_authentication\n"
        "- Otherwise, select analysis_planning\n"
        "\nParticipants: {{$participants}}\n"
        "Message: {{$lastmessage}}\n"
        "\nRespond with participant name only."
    )

    result_filter_prompt: str = (
        "Return ONLY the concrete facts from the specialist's response.\n"
        "If there are specific numbers (amounts, IDs), include them exactly as given.\n"
        "Make sure you **ALWAYS** include information to the specific customer ID, you will get this info from specialized agents \n"
        "For example, if you see dollar amounts or invoice numbers or percentage numbers or specific promotional plans and such, those **MUST** be in the final response.\n"
        "Format: In addition to the specifics, your response needs to be empathetic and helpful to customer concerns.\n"
    )

    def __init__(self, topic: str, service: ChatCompletionClientBase, **kwargs) -> None:
        super().__init__(topic=topic, service=service, **kwargs)
        # Create execution settings with max tokens
        settings_class = self.service.get_prompt_execution_settings_class()
        self._execution_settings = settings_class(extension_data={"max_tokens": 2000})

    async def _render_prompt(self, prompt: str, arguments: KernelArguments) -> str:
        prompt_template_config = PromptTemplateConfig(template=prompt)
        prompt_template = KernelPromptTemplate(prompt_template_config=prompt_template_config)
        return await prompt_template.render(Kernel(), arguments=arguments)

    @override
    async def should_request_user_input(self, chat_history: ChatHistory) -> BooleanResult:
        return BooleanResult(
            result=False,
            reason="This group chat manager does not require user input.",
        )

    @override
    async def should_terminate(self, chat_history: ChatHistory) -> BooleanResult:
        should_terminate = await super().should_terminate(chat_history)
        if should_terminate.result:
            return should_terminate

        chat_history.messages.insert(
            0,
            ChatMessageContent(
                role=AuthorRole.SYSTEM,
                content=await self._render_prompt(
                    self.termination_prompt,
                    KernelArguments(topic=self.topic),
                ),
            ),
        )
        
        response = await self.service.get_chat_message_content(
            chat_history,
            settings=self._execution_settings,
        )

        return BooleanResult(
            result=response.content.lower().startswith("final answer:"),
            reason="Checking for FINAL ANSWER prefix",
        )

    @override
    async def select_next_agent(
        self,
        chat_history: ChatHistory,
        participant_descriptions: dict[str, str],
    ) -> StringResult:
        chat_history.messages.insert(
            0,
            ChatMessageContent(
                role=AuthorRole.SYSTEM,
                content=await self._render_prompt(
                    self.selection_prompt,
                    KernelArguments(
                        topic=self.topic,
                        participants="\n".join([f"{k}: {v}" for k, v in participant_descriptions.items()]),
                    ),
                ),
            ),
        )

        response = await self.service.get_chat_message_content(
            chat_history,
            settings=self._execution_settings,
        )

        # Process the response content to get the next agent
        content = response.content.lower().strip()
        
        # Check for exact agent name or delegation format (e.g., "crm_billing: task")
        for agent_name in participant_descriptions.keys():
            if content == agent_name or content.startswith(f"{agent_name}:"):
                return StringResult(
                    result=agent_name,
                    reason=f"Matched agent {agent_name}"
                )
        
        # Default to analysis_planning for orchestration
        return StringResult(
            result="analysis_planning",
            reason="No clear specialist match - routing to orchestrator"
        )

    @override
    async def filter_results(
        self,
        chat_history: ChatHistory,
    ) -> MessageResult:
        if not chat_history.messages:
            raise RuntimeError("No messages in the chat history.")

        chat_history.messages.insert(
            0,
            ChatMessageContent(
                role=AuthorRole.SYSTEM,
                content=await self._render_prompt(
                    self.result_filter_prompt,
                    KernelArguments(topic=self.topic),
                ),
            ),
        )

        response = await self.service.get_chat_message_content(
            chat_history,
            settings=self._execution_settings,
        )

        return MessageResult(
            result=ChatMessageContent(
                role=AuthorRole.ASSISTANT,
                content=response.content.replace("FINAL ANSWER:", "").strip(),
            ),
            reason="Final response summarized from discussion",
        )

class Agent(BaseAgent):
    def __new__(cls, state_store: dict, session_id: str):
        if session_id in state_store:
            return state_store[session_id]
        instance = super().__new__(cls)
        state_store[session_id] = instance
        return instance

    def __init__(self, state_store: dict, session_id: str) -> None:
        if hasattr(self, "_constructed"):
            return
        self._constructed = True
        super().__init__(state_store, session_id)
        self._orchestration: Optional[GroupChatOrchestration] = None
        self._group_chat_runtime: Optional[InProcessRuntime] = None
        self.chat_history = ChatHistory()  # Use SDK's ChatHistory
        self.max_history_size = 10
        self.session_id = session_id
        self._initialized = False  # Initialize the flag used in setup and chat

    def agent_response_callback(self, message: ChatMessageContent) -> None:
        """Callback function to retrieve agent responses and log tool usage."""
        try:
            # Log regular messages
            if message.role == AuthorRole.ASSISTANT:
                logger.info(f"\n=== {message.name}'s Response ===\n{message.content}\n")
            
            # Log tool usage with details if it's a tool call
            if hasattr(message, 'function_name') and message.function_name:
                tool_info = f"{message.name} -> {message.function_name}"
                if hasattr(self, 'tool_usage'):
                    self.tool_usage.append(tool_info)
                logger.info(
                    f"\n=== Tool Usage ===\n"
                    f"Agent: {message.name}\n"
                    f"Tool: {message.function_name}\n"
                    f"Arguments: {message.function_arguments}\n"
                    f"Response: {message.content}\n"
                )
        except Exception as e:
            # Log the error but don't raise it to allow the conversation to continue
            logger.debug(f"Error in agent_response_callback: {str(e)}")

    def get_chat_history(self) -> ChatHistory:
        """Get the chat history."""
        return self.chat_history

    async def _setup_team(self) -> None:
        if getattr(self, "_initialized", False):
            return

        try:
            service = AzureChatCompletion(
                api_key=self.azure_openai_key,
                endpoint=self.azure_openai_endpoint,
                api_version=self.api_version,
                deployment_name=self.azure_deployment,
            )

            self.contoso_plugin = MCPSsePlugin(
                name="ContosoMCP",
                description="Contoso MCP Plugin",
                url=self.mcp_server_uri,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            await self.contoso_plugin.connect()

            specialist_kernel = Kernel()
            specialist_kernel.add_service(service)
            specialist_kernel.add_plugin(self.contoso_plugin, plugin_name="ContosoMCP")

            def make_agent(name, description, instructions, included_tools=[]):
                function_choice_behavior = FunctionChoiceBehavior.Auto(
                    filters={"included_functions": included_tools} if included_tools else None
                )
                return ChatCompletionAgent(
                    name=name,
                    description=description,
                    instructions=instructions,
                    service=specialist_kernel.get_service("default"),
                    function_choice_behavior=function_choice_behavior,
                    kernel=specialist_kernel,
                )

            participants = [
                make_agent(
                    name="crm_billing",
                    description="CRM & Billing Agent",
                    instructions=(
                        "You are the CRM & Billing Agent. For billing queries:\n"
                        "1. Use get_invoice_payments to check current invoice status\n"
                        "2. Use get_billing_summary to get total amounts\n"
                        "3. In your response, ALWAYS include:\n"
                        "   - The exact total amount due\n"
                        "   - The specific invoice ID with outstanding balance\n"
                        "   - Only state facts from the tools\n"
                        "4. Format your response like this:\n"
                        "   Total due: $X.XX\n"
                        "   Outstanding on Invoice ID: XXXX\n"
                        "   Status: <paid/unpaid>"
                    ),
                    included_tools=[
                        "ContosoMCP-get_all_customers",
                        "ContosoMCP-get_customer_detail",
                        "ContosoMCP-get_subscription_detail",
                        "ContosoMCP-get_invoice_payments",
                        "ContosoMCP-pay_invoice",
                        "ContosoMCP-get_data_usage",
                        "ContosoMCP-search_knowledge_base",
                        "ContosoMCP-get_customer_orders",
                        "ContosoMCP-update_subscription",
                        "ContosoMCP-get_billing_summary",
                    ],
                ),
                make_agent(
                    name="product_promotions",
                    description="Product & Promo Agent",
                    instructions=(
                        "You are the Product & Promotions Agent.\n"
                        "- Retrieve promotional offers, product availability, eligibility "
                        "criteria, and discount information from structured sources.\n"
                        "- For each response you **MUST** cross‑reference relevant *Knowledge Base* FAQs, terms & conditions, "
                        "and best practices.\n"
                        "- Provide factual, up‑to‑date product/promo details."
                        "Only respond with data you retrieve using your tools.\n"
                        "DO NOT respond to anything out of your domain."
                    ),
                    included_tools=[
                        "ContosoMCP-get_all_customers",
                        "ContosoMCP-get_customer_detail",
                        "ContosoMCP-get_promotions",
                        "ContosoMCP-get_eligible_promotions",
                        "ContosoMCP-search_knowledge_base",
                        "ContosoMCP-get_products",
                        "ContosoMCP-get_product_detail",
                    ],
                ),
                make_agent(
                    name="security_authentication",
                    description="Security & Authentication Agent",
                    instructions=(
                        "You are the Security & Authentication Agent.\n"
                        "- Investigate authentication logs, account lockouts, and security "
                        "incidents in structured security databases.\n"
                        "- For each response you **MUST** cross‑reference relevant *Knowledge Base* security policies and "
                        "lockout troubleshooting guides.\n"
                        "- Return clear risk assessments and recommended remediation steps."
                        "Only respond with data you retrieve using your tools.\n"
                        "DO NOT respond to anything out of your domain."
                    ),
                    included_tools=[
                        "ContosoMCP-get_all_customers",
                        "ContosoMCP-get_customer_detail",
                        "ContosoMCP-get_security_logs",
                        "ContosoMCP-search_knowledge_base",
                        "ContosoMCP-unlock_account",
                    ],
                ),
                make_agent(
                    name="analysis_planning",
                    description="Analysis & Planning Agent",
                    instructions=(
                        "You are the Analysis & Planning Agent (the planner/orchestrator).\n"
                        "\n"
                        "1. First, check if this is a basic interaction:\n"
                        "   - For greetings (hi, hello, hey), thank you messages, or simple acknowledgments\n"
                        "   - Respond directly with either asking if any help is needed and if not, send a friendly reply: FINAL ANSWER: <your friendly reply>\n"
                        "\n"
                        "2. For all other requests, analyze the query and route to specialists and leverage right tools they have to answer the the query:\n"
                         "It is possible that it is a query that only needs response from one specialist, in that case, don't route to multiple specialists.\n"
                         "understand the question to see if it needs to be routed to multiple specialists.\n"
                        "   Route to crm_billing if query involves:\n"
                        "   - Billing, invoices, payments, subscriptions, account status, usage, refunds\n"
                        "\n"
                        "   Route to product_promotions if query involves:\n"
                        "   - Products, promotions, offers, discounts, pricing, eligibility, deals\n"
                        "\n"
                        "   Route to security_authentication if query involves:\n"
                        "   - Security, login issues, authentication, account access, lockouts\n"
                        "\n"
                        "   Delegation format (strict):\n"
                        "   <specialist_name>: <describe what information is needed>\n"
                        "   - One task per turn, wait for response\n"
                        "\n"
                        "3. After specialists provide information:\n"
                        "   FINAL ANSWER: <synthesized response>\n"
                        "\n"
                        "4. If query is unclear, like ID is not provided:\n"
                        "   FINAL ANSWER: <your clarifying question>\n"
                        "\n"
                        "STRICT RULES:\n"
                        "- Handle greetings and basic interactions yourself\n"
                        "- For all other queries, route to appropriate specialist based on keywords\n"
                        "- Let specialists use their tools - don't specify which tools they should use\n"
                        "- Never show routing decisions or specialist names to the user\n"
                        "- Never include 'FINAL ANSWER' when talking to specialists\n"
                    ),
                ),
            ]

            self._orchestration = GroupChatOrchestration(
                members=participants,
                manager=ContosoGroupChatManager(
                    topic="Handle user request",
                    service=service,
                    max_rounds=1,
                ),
                agent_response_callback=self.agent_response_callback,
            )

            # Create and start the runtime
            self._group_chat_runtime = InProcessRuntime()
            self._group_chat_runtime.start()
            self._initialized = True
            logger.info("Team setup completed successfully")

        except Exception as e:
            logger.error(f"Error in team setup: {str(e)}", exc_info=True)
            raise

    async def chat_async(self, user_input: str) -> str:
        try:
            # One-time initialization when first starting
            if not self._initialized:
                self.chat_history = ChatHistory()  # Create fresh history only on first use
                await self._setup_team()

            # Add user message to chat history
            self.chat_history.add_message(
                ChatMessageContent(
                    role=AuthorRole.USER,
                    content=user_input
                )
            )

            try:
                # Create lists to track tool usage during this conversation
                self.tool_usage = []
                
                # Use invoke with the chat history
                result = await self._orchestration.invoke(
                    task=user_input,
                    runtime=self._group_chat_runtime,
                )
                
                response = await result.get()
                final_response = str(response.content)

                # Create a summary of tool usage
                if hasattr(self, 'tool_usage') and self.tool_usage:
                    tools_summary = "\n\n=== Tools Used ===\n"
                    for tool in self.tool_usage:
                        tools_summary += f"- {tool}\n"
                    logger.info(tools_summary)

                # Add assistant response to chat history
                self.chat_history.add_message(
                    ChatMessageContent(
                        role=AuthorRole.ASSISTANT,
                        content=final_response
                    )
                )

                # Limit history size if needed
                if len(self.chat_history.messages) > self.max_history_size:
                    self.chat_history.messages = self.chat_history.messages[-self.max_history_size:]

                return final_response

            except Exception as chat_error:
                logger.error("Chat orchestration error", exc_info=True)
                raise

        except Exception as e:
            logger.error("Error in chat_async", exc_info=True)
            return f"I encountered an error while processing your request. Please try again or start a new conversation. Error: {str(e)}"

    async def cleanup(self):
        """Cleanup method to properly stop the runtime"""
        if self._group_chat_runtime:
            try:
                await self._group_chat_runtime.stop()
            except Exception as e:
                logger.error(f"Error stopping runtime: {str(e)}")
        
        if hasattr(self, 'contoso_plugin'):
            try:
                await self.contoso_plugin.close()
            except Exception as e:
                logger.error(f"Error closing plugin: {str(e)}")

if __name__ == "__main__":
    async def run_test():
        dummy_state = {}
        session_id = "demo_session"
        agent = Agent(dummy_state, session_id=session_id)

        try:
            print("You can ask questions continuously. Type 'exit' or 'end' to quit.\n")
            while True:
                user_input = input("You: ").strip()
                if user_input.lower() in ("exit", "end"):
                    print("Exiting chat...")
                    break

                response = await agent.chat_async(user_input)
                print("Assistant:", response)

        finally:
            # Ensure proper cleanup
            await agent.cleanup()

    asyncio.run(run_test())
