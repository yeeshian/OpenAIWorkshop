# Copyright (c) Microsoft. All rights reserved.

import asyncio
import sys

from semantic_kernel.agents import Agent, ChatCompletionAgent, GroupChatOrchestration
from semantic_kernel.agents.orchestration.group_chat import BooleanResult, GroupChatManager, MessageResult, StringResult
from semantic_kernel.agents.runtime import InProcessRuntime
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.connectors.ai.prompt_execution_settings import PromptExecutionSettings
from semantic_kernel.contents import AuthorRole, ChatHistory, ChatMessageContent
from semantic_kernel.functions import KernelArguments
from semantic_kernel.kernel import Kernel
from semantic_kernel.prompt_template import KernelPromptTemplate, PromptTemplateConfig

if sys.version_info >= (3, 12):
    from typing import override  # pragma: no cover
else:
    from typing_extensions import override  # pragma: no cover


import asyncio
from typing import Dict, Any, List, Optional
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.functions import KernelArguments
from semantic_kernel.connectors.ai.prompt_execution_settings import (
    PromptExecutionSettings,
    FunctionChoiceBehavior,
)
from semantic_kernel.connectors.mcp import MCPSsePlugin  # replace with your actual import
from base_agent import BaseAgent  # Your BaseAgent as you shared


class SKAgent(BaseAgent):
    def __init__(
        self,
        state_store: Dict[str, Any],
        session_id: str,
        name: str,
        instructions: str,
        description: str,
        included_tools: Optional[List[str]] = None,
    ):
        super().__init__(state_store, session_id)

        self.kernel = Kernel()
        self.kernel.add_service(
            AzureChatCompletion(
                api_key=self.azure_openai_key,
                endpoint=self.azure_openai_endpoint,
                api_version=self.api_version,
                deployment_name=self.azure_deployment,
            )
        )
        chat_deployment_name = "gpt-4o-mini"
        self.contoso_plugin = MCPSsePlugin(
            name="ContosoMCP",
            description="Contoso MCP Plugin",
            url=self.mcp_server_uri,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        # Note: Connect asynchronously outside constructor
        # await self.contoso_plugin.connect()  # call this before using agent
        self.kernel.add_plugin(self.contoso_plugin, plugin_name="ContosoMCP")

        # Setup prompt execution settings and filter included tools if specified
        settings = self.kernel.get_prompt_execution_settings_from_service_id("default")
        if included_tools:
            settings.function_choice_behavior = FunctionChoiceBehavior.Auto(
                filters={"included_functions": included_tools}
            )

        self.agent = ChatCompletionAgent(
            kernel=self.kernel,
            name=name,
            instructions=instructions,
            arguments=KernelArguments(settings=settings),
        )
        self.agent.description = description
        
    async def chat_async(self, prompt: str) -> str:
        # Proxy to underlying agent
        response = await self.agent.invoke_async(prompt)
        return response.text

    def get_agent(self) -> ChatCompletionAgent:
        return self.agent


def get_agents(state_store: Dict[str, Any], session_id: str) -> List[ChatCompletionAgent]:
    crm_billing = SKAgent(
        state_store,
        session_id,
        name="crm_billing",
        description="Accesses CRM & billing systems for account, subscription, invoice, and payment status queries.", 
        instructions=(
            "You are the CRM & Billing Agent.\n"
            "- Query structured CRM / billing systems for account, subscription, "
            "invoice, and payment information as needed.\n"
            "- For each response you **MUST** cross‑reference relevant *Knowledge Base* articles on billing policies, payment "
            "processing, refund rules, etc., to ensure responses are accurate "
            "and policy‑compliant.\n"
            "- Reply with concise, structured information and flag any policy "
            "concerns you detect.\n"
            "Only respond with data you retrieve using your tools.\n"
            "DO NOT respond to anything out of your domain."
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
    )

    product_promotions = SKAgent(
        state_store,
        session_id,
        name="product_promotions",
        description="Provides product catalogue details, current promotions, discount eligibility rules, and T&Cs.", 
        instructions=(
            "You are the Product & Promotions Agent.\n"
            "- Retrieve promotional offers, product availability, eligibility "
            "criteria, and discount information from structured sources.\n"
            "- For each response you **MUST** cross‑reference relevant *Knowledge Base* FAQs, terms & conditions, "
            "and best practices.\n"
            "- Provide factual, up‑to‑date product/promo details.\n"
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
    )

    security_authentication = SKAgent(
        state_store,
        session_id,
        name="security_authentication",
        description="Handles security logs, account lockouts, and authentication incidents with cross-referencing policies.",
        instructions=(
            "You are the Security & Authentication Agent.\n"
            "- Investigate authentication logs, account lockouts, and security "
            "incidents in structured security databases.\n"
            "- For each response you **MUST** cross‑reference relevant *Knowledge Base* security policies and "
            "lockout troubleshooting guides.\n"
            "- Return clear risk assessments and recommended remediation steps.\n"
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
    )

    return [
        crm_billing.get_agent(),
        product_promotions.get_agent(),
        security_authentication.get_agent(),
    ]




class ContosoGroupChatManager(GroupChatManager):
    """A simple chat completion base group chat manager.

    This chat completion service requires a model that supports structured output.
    """

    service: ChatCompletionClientBase

    topic: str

    termination_prompt: str = (
        "You are a Contoso support mediator managing conversations with customer service agents.\n"
        "Review the conversation history and determine if:\n"
        "1. The user's original question '{{$topic}}' has been fully answered\n"
        "2. All necessary information has been gathered\n"
        "3. A clear resolution has been provided\n"
        "Return True if all these conditions are met, False otherwise."
    )

    selection_prompt: str = (
        "You are a Contoso support mediator. Based on the user's question and conversation so far, select the most appropriate specialist:\n\n"
        "Original question: {{$topic}}\n\n"
        "Available specialists:\n"
        "{{$participants}}\n\n"
        "Rules:\n"
        "1. If this is a new conversation about billing/invoices/payments, select 'crm_billing'\n"
        "2. If this is about products/services/promotions, select 'product_promotions'\n"
        "3. If this is about security/authentication/access, select 'security_authentication'\n"
        "4. If the question has been fully answered, reply with 'FINAL_ANSWER'\n"
        "5. Respond with ONLY the specialist name or 'FINAL_ANSWER', no other text"
    )

    result_filter_prompt: str = (
        "Return ONLY the concrete facts from the specialist's response.\n"
        "If there are specific numbers (amounts, IDs), include them exactly as given.\n"
        "Make sure you **ALWAYS** include information to the specific customer ID, you will get this info from specialized agents \n"
        "For example, if you see dollar amounts or invoice numbers or percentage numbers or specific promotional plans and such, those **MUST** be in the final response.\n"
        "Format: In addition to the specifics, your response needs to be empathetic and helpful to customer concerns.\n"
    )


    def __init__(self, topic: str, service: ChatCompletionClientBase, **kwargs) -> None:
        """Initialize the group chat manager."""
        super().__init__(topic=topic, service=service, **kwargs)

    async def _render_prompt(self, prompt: str, arguments: KernelArguments) -> str:
        """Helper to render a prompt with arguments."""
        prompt_template_config = PromptTemplateConfig(template=prompt)
        prompt_template = KernelPromptTemplate(prompt_template_config=prompt_template_config)
        return await prompt_template.render(Kernel(), arguments=arguments)

    @override
    async def should_request_user_input(self, chat_history: ChatHistory) -> BooleanResult:
        """Provide concrete implementation for determining if user input is needed.

        The manager will check if input from human is needed after each agent message.
        """
        return BooleanResult(
            result=False,
            reason="This group chat manager does not require user input.",
        )

    @override
    async def should_terminate(self, chat_history: ChatHistory) -> BooleanResult:
        """Provide concrete implementation for determining if the discussion should end.

        The manager will check if the conversation should be terminated after each agent message
        or human input (if applicable).
        """
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
        chat_history.add_message(
            ChatMessageContent(role=AuthorRole.USER, content="Determine if the discussion should end."),
        )

        response = await self.service.get_chat_message_content(
            chat_history,
            settings=PromptExecutionSettings(response_format=BooleanResult),
        )

        termination_with_reason = BooleanResult.model_validate_json(response.content)

        print("*********************")
        print(f"Should terminate: {termination_with_reason.result}\nReason: {termination_with_reason.reason}.")
        print("*********************")

        return termination_with_reason

    @override
    async def select_next_agent(
        self,
        chat_history: ChatHistory,
        participant_descriptions: dict[str, str],
    ) -> StringResult:
        """Provide concrete implementation for selecting the next agent to speak.

        The manager will select the next agent to speak after each agent message
         if the conversation is not terminated.
        """
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
        chat_history.add_message(
            ChatMessageContent(role=AuthorRole.USER, content="Now select the next participant to speak."),
        )

        response = await self.service.get_chat_message_content(
            chat_history,
            settings=PromptExecutionSettings(response_format=StringResult),
        )

        participant_name_with_reason = StringResult.model_validate_json(response.content)

        print("*********************")
        print(
            f"Next participant: {participant_name_with_reason.result}\nReason: {participant_name_with_reason.reason}."
        )
        print("*********************")

        result = participant_name_with_reason.result.strip()
        
        if result == "FINAL_ANSWER":
            return StringResult(result=result, reason="Conversation goal has been achieved.")
        elif result in participant_descriptions:
            return StringResult(result=result, reason=f"Delegating to {result} specialist.")
        else:
            raise RuntimeError(f"Unknown participant selected: {result}")

    @override
    async def filter_results(
        self,
        chat_history: ChatHistory,
    ) -> MessageResult:
        """Provide concrete implementation for filtering the results of the discussion.

        The manager will filter the results of the conversation after the conversation is terminated.
        """
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
        chat_history.add_message(
            ChatMessageContent(role=AuthorRole.USER, content="Please summarize the discussion."),
        )

        response = await self.service.get_chat_message_content(
            chat_history,
            settings=PromptExecutionSettings(response_format=StringResult),
        )
        string_with_reason = StringResult.model_validate_json(response.content)

        return MessageResult(
            result=ChatMessageContent(role=AuthorRole.ASSISTANT, content=string_with_reason.result),
            reason=string_with_reason.reason,
        )


def agent_response_callback(message: ChatMessageContent) -> None:
    """Callback function to retrieve agent responses."""
    print(f"**{message.name}**\n{message.content}")


async def main():
    dummy_state = {}
    session_id = "demo"

    agents = get_agents(dummy_state, session_id)

    group_chat_orchestration = GroupChatOrchestration(
        members=agents,
        manager=ContosoGroupChatManager(
            topic="Why is my internet bill so high for customer ID 101?",
            service=AzureChatCompletion(
                # your azure config here or environment variables
            ),
            max_rounds=10,
        ),
        agent_response_callback=agent_response_callback,
    )

    runtime = InProcessRuntime()
    runtime.start()

    orchestration_result = await group_chat_orchestration.invoke(
        task="Please start the discussion.",
        runtime=runtime,
    )

    value = await orchestration_result.get()
    print(value)

    await runtime.stop_when_idle()

if __name__ == "__main__":
    asyncio.run(main())