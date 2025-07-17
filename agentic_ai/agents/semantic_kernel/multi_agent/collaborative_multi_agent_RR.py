import asyncio
import logging
from typing import Optional

from semantic_kernel.agents import ChatCompletionAgent, GroupChatOrchestration
from semantic_kernel.agents.orchestration.group_chat import (
    BooleanResult,
    GroupChatManager,
    MessageResult,
    StringResult,
)
from semantic_kernel.agents.runtime import InProcessRuntime
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

    service: AzureChatCompletion
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

    def __init__(self, topic: str, service: AzureChatCompletion, **kwargs) -> None:
        super().__init__(topic=topic, service=service, **kwargs)
        settings_class = self.service.get_prompt_execution_settings_class()
        self._execution_settings = settings_class(extension_data={"max_tokens": 2000})

    async def _render_prompt(self, prompt: str, arguments: KernelArguments) -> str:
        prompt_template_config = PromptTemplateConfig(template=prompt)
        prompt_template = KernelPromptTemplate(prompt_template_config=prompt_template_config)
        return await prompt_template.render(Kernel(), arguments=arguments)

    async def should_request_user_input(self, chat_history: ChatHistory) -> BooleanResult:
        return BooleanResult(
            result=False,
            reason="This group chat manager does not require user input.",
        )

    async def should_terminate(self, chat_history: ChatHistory) -> BooleanResult:
        should_terminate = await super().should_terminate(chat_history)
        if should_terminate.result:
            return should_terminate

        # Inject the termination prompt for the last user message
        last_message = chat_history.messages[-1].content if chat_history.messages else ""
        chat_history.messages.insert(
            0,
            ChatMessageContent(
                role=AuthorRole.SYSTEM,
                content=await self._render_prompt(
                    self.termination_prompt,
                    KernelArguments(lastmessage=last_message),
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

    async def select_next_agent(
        self,
        chat_history: ChatHistory,
        participant_descriptions: dict[str, str],
    ) -> StringResult:
        last_message = chat_history.messages[-1].content if chat_history.messages else ""
        participants_str = "\n".join([f"{k}: {v}" for k, v in participant_descriptions.items()])
        chat_history.messages.insert(
            0,
            ChatMessageContent(
                role=AuthorRole.SYSTEM,
                content=await self._render_prompt(
                    self.selection_prompt,
                    KernelArguments(
                        lastmessage=last_message,
                        participants=participants_str,
                    ),
                ),
            ),
        )

        response = await self.service.get_chat_message_content(
            chat_history,
            settings=self._execution_settings,
        )

        content = response.content.lower().strip()

        for agent_name in participant_descriptions.keys():
            if content == agent_name or content.startswith(f"{agent_name}:"):
                return StringResult(
                    result=agent_name,
                    reason=f"Matched agent {agent_name}",
                )

        return StringResult(
            result="analysis_planning",
            reason="No clear specialist match - routing to orchestrator",
        )

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


class Agent:
    def __init__(
        self,
        azure_openai_key: str,
        azure_openai_endpoint: str,
        api_version: str,
        azure_deployment: str,
        mcp_server_uri: str,
        max_history_size: int = 10,
    ):
        self.azure_openai_key = azure_openai_key
        self.azure_openai_endpoint = azure_openai_endpoint
        self.api_version = api_version
        self.azure_deployment = azure_deployment
        self.mcp_server_uri = mcp_server_uri

        self.max_history_size = max_history_size

        self._orchestration: Optional[GroupChatOrchestration] = None
        self._group_chat_runtime: Optional[InProcessRuntime] = None
        self.chat_history = ChatHistory()
        self.tool_usage = []
        self._initialized = False

    async def _setup_team(self) -> None:
        if self._initialized:
            return

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
            from semantic_kernel.connectors.ai.function_choice_behavior import FunctionChoiceBehavior

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

        self._group_chat_runtime = InProcessRuntime()
        self._group_chat_runtime.start()
        self._initialized = True
        logger.info("Team setup completed successfully")

    def agent_response_callback(self, message: ChatMessageContent) -> None:
        try:
            if message.role == AuthorRole.ASSISTANT:
                logger.info(f"\n=== {message.name}'s Response ===\n{message.content}\n")

            if hasattr(message, "function_name") and message.function_name:
                tool_info = f"{message.name} -> {message.function_name}"
                self.tool_usage.append(tool_info)
                logger.info(
                    f"\n=== Tool Usage ===\nAgent: {message.name}\nTool: {message.function_name}\nArguments: {message.function_arguments}\nResponse: {message.content}\n"
                )
        except Exception as e:
            logger.debug(f"Error in agent_response_callback: {str(e)}")

    async def chat_async(self, user_input: str) -> str:
        try:
            if not self._initialized:
                self.chat_history = ChatHistory()
                await self._setup_team()

            self.chat_history.add_message(ChatMessageContent(role=AuthorRole.USER, content=user_input))

            self.tool_usage = []

            # Build a conversation context string from chat history
            conversation_text = ""
            for msg in self.chat_history.messages:
                prefix = "User: " if msg.role == AuthorRole.USER else "Assistant: "
                conversation_text += prefix + msg.content + "\n"

            # Pass this full conversation as the task to the orchestration
            result = await self._orchestration.invoke(
                task=conversation_text,
                runtime=self._group_chat_runtime
            )
            response = await result.get()
            final_response = str(response.content)

            self.chat_history.add_message(ChatMessageContent(role=AuthorRole.ASSISTANT, content=final_response))

            # Trim chat history
            if len(self.chat_history.messages) > self.max_history_size:
                self.chat_history.messages = self.chat_history.messages[-self.max_history_size:]

            if self.tool_usage:
                tools_summary = "\n\n=== Tools Used ===\n" + "\n".join(self.tool_usage)
                logger.info(tools_summary)

            return final_response

        except Exception as e:
            logger.error("Error in chat_async", exc_info=True)
            return f"I encountered an error while processing your request: {str(e)}"




import os
from dotenv import load_dotenv

# Load .env variables at the very top
load_dotenv()

# Later in __main__, create the Agent using env vars

if __name__ == "__main__":
    async def run_test():
        # Read all from environment variables
        azure_openai_key = os.getenv("AZURE_OPENAI_API_KEY")
        azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2023-05-15")
        azure_deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
        mcp_server_uri = os.getenv("MCP_SERVER_URI")

        # Validate required env vars
        missing = [
            var
            for var in [
                ("AZURE_OPENAI_API_KEY", azure_openai_key),
                ("AZURE_OPENAI_ENDPOINT", azure_openai_endpoint),
                ("AZURE_OPENAI_CHAT_DEPLOYMENT", azure_deployment),
                ("MCP_SERVER_URI", mcp_server_uri),
            ]
            if var[1] is None
        ]
        if missing:
            missing_vars = ", ".join([v[0] for v in missing])
            print(f"ERROR: Missing required environment variables: {missing_vars}")
            return

        agent = Agent(
            azure_openai_key=azure_openai_key,
            azure_openai_endpoint=azure_openai_endpoint,
            api_version=api_version,
            azure_deployment=azure_deployment,
            mcp_server_uri=mcp_server_uri,
        )

        print("You can ask questions continuously. Type 'exit' or 'end' to quit.\n")

        try:
            while True:
                user_input = input("You: ").strip()
                if user_input.lower() in ("exit", "end"):
                    print("Exiting chat...")
                    break

                response = await agent.chat_async(user_input)
                print("Assistant:", response)

        finally:
            await agent.cleanup()

    asyncio.run(run_test())

