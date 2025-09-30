"""
Optimized handoff pattern for domain-based multi-agent routing.

Architecture:
1. User chats directly with the assigned specialist agent (no middleman)
2. Lightweight intent classifier checks for domain changes
3. Only re-routes when user switches topics or requests help
4. Full streaming visibility via WebSocket

Key improvements over v2:
- No heavy Magentic orchestrator
- Direct agent-to-user communication
- Efficient intent detection using vanilla LLM calls
- Simple state management for current agent tracking
"""

import json
import logging
from typing import Any, Dict, List, Optional

from agent_framework import ChatAgent, ChatMessage, Role, MCPStreamableHTTPTool
from agent_framework.azure import AzureOpenAIChatClient

from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


# Domain definitions
DOMAINS = {
    "crm_billing": {
        "name": "CRM & Billing Specialist",
        "description": "Handles subscriptions, billing, invoices, payments, and account adjustments",
        "tools": [
            "get_all_customers",
            "get_customer_detail",
            "get_subscription_detail",
            "get_billing_summary",
            "get_invoice_payments",
            "pay_invoice",
            "get_data_usage",
            "update_subscription",
            "search_knowledge_base",
        ],
        "instructions": (
            "You are the CRM & Billing Specialist for Contoso support.\n\n"
            "**Your expertise:**\n"
            "- Customer accounts, subscriptions, billing, invoices, payments\n"
            "- Account adjustments, data usage, subscription updates\n\n"
            "**Critical rules:**\n"
            "- ALWAYS use your tools to retrieve factual data. NEVER guess or hallucinate.\n"
            "- If customer info is needed but not provided, ask the user directly for it.\n"
            "- If the user asks about products, promotions, or security issues, respond: "
            "'This is outside my area. Let me connect you with the right specialist.'\n"
            "- Be concise and professional. Provide specific details from tool responses.\n"
        ),
    },
    "product_promotions": {
        "name": "Product & Promotions Specialist",
        "description": "Handles product inquiries, plan changes, promotions, and eligibility",
        "tools": [
            "get_products",
            "get_product_detail",
            "get_promotions",
            "get_eligible_promotions",
            "get_customer_orders",
            "search_knowledge_base",
        ],
        "instructions": (
            "You are the Product & Promotions Specialist for Contoso support.\n\n"
            "**Your expertise:**\n"
            "- Product catalog, features, availability\n"
            "- Promotions, discounts, eligibility rules\n"
            "- Customer orders and product recommendations\n\n"
            "**Critical rules:**\n"
            "- ALWAYS use your tools to retrieve factual data. NEVER guess or hallucinate.\n"
            "- If the user asks about billing or security issues, respond: "
            "'This is outside my area. Let me connect you with the right specialist.'\n"
            "- Be enthusiastic and helpful. Highlight benefits and savings opportunities.\n"
        ),
    },
    "security_authentication": {
        "name": "Security & Authentication Specialist",
        "description": "Handles authentication failures, lockouts, security incidents, and remediation",
        "tools": [
            "get_security_logs",
            "unlock_account",
            "get_support_tickets",
            "create_support_ticket",
            "search_knowledge_base",
        ],
        "instructions": (
            "You are the Security & Authentication Specialist for Contoso support.\n\n"
            "**Your expertise:**\n"
            "- Account security, authentication issues, lockouts\n"
            "- Security logs, incident investigation, remediation\n"
            "- Support ticket management for security issues\n\n"
            "**Critical rules:**\n"
            "- ALWAYS use your tools to retrieve factual data. NEVER guess or hallucinate.\n"
            "- If the user asks about billing or products, respond: "
            "'This is outside my area. Let me connect you with the right specialist.'\n"
            "- Take security seriously. Verify user identity and flag suspicious activity.\n"
        ),
    },
}

# Intent classification prompt
INTENT_CLASSIFIER_PROMPT = """You are an intent classifier for Contoso customer support.

Available domains:
1. crm_billing: subscriptions, billing, invoices, payments, account adjustments
2. product_promotions: products, plans, promotions, eligibility, orders
3. security_authentication: security issues, lockouts, authentication failures

Analyze the user's message and determine:
1. Which domain it belongs to
2. Whether it's a domain change from the current context

Current domain: {current_domain}
User message: {user_message}

Respond with JSON:
{{
    "domain": "crm_billing|product_promotions|security_authentication",
    "is_domain_change": true|false,
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}}

Rules:
- If uncertain, default to current domain with low confidence
- Detect explicit requests to "talk to someone else" or "get help with X" as domain changes
- Consider context: billing questions stay in billing unless user explicitly changes topic
"""


class Agent(BaseAgent):
    """
    Optimized handoff pattern using vanilla workflow and direct agent communication.
    
    Flow:
    1. Intent classifier determines which domain specialist to route to
    2. User communicates directly with assigned specialist
    3. On domain change detection, seamlessly transfer to new specialist
    4. Specialists have filtered tool access and clear boundaries
    """

    def __init__(self, state_store: Dict[str, Any], session_id: str, access_token: str | None = None) -> None:
        super().__init__(state_store, session_id)
        self._access_token = access_token
        self._ws_manager = None
        
        # Track current agent and conversation history per domain
        self._current_domain = state_store.get(f"{session_id}_current_domain", None)
        self._domain_agents: Dict[str, ChatAgent] = {}
        self._domain_threads: Dict[str, Any] = {}
        self._initialized = False
        
        # Turn tracking for tool grouping
        self._turn_key = f"{session_id}_handoff_turn"
        self._current_turn = state_store.get(self._turn_key, 0)
        
        # Context transfer configuration: -1 = all history, 0 = none, N = last N turns
        import os
        self._context_transfer_turns = int(os.getenv("HANDOFF_CONTEXT_TRANSFER_TURNS", "-1"))

    def set_websocket_manager(self, manager: Any) -> None:
        """Allow backend to inject WebSocket manager for streaming events."""
        self._ws_manager = manager
        logger.info(f"[HANDOFF] WebSocket manager set for handoff agent, session_id={self.session_id}")

    async def _setup_agents(self) -> None:
        """Initialize all domain specialist agents."""
        if self._initialized:
            return

        if not all([self.azure_openai_key, self.azure_deployment, self.azure_openai_endpoint, self.api_version]):
            raise RuntimeError(
                "Azure OpenAI configuration is incomplete. Ensure AZURE_OPENAI_API_KEY, "
                "AZURE_OPENAI_CHAT_DEPLOYMENT, AZURE_OPENAI_ENDPOINT, and AZURE_OPENAI_API_VERSION are set."
            )

        headers = self._build_headers()
        mcp_tool = await self._create_mcp_tool(headers)

        chat_client = AzureOpenAIChatClient(
            api_key=self.azure_openai_key,
            deployment_name=self.azure_deployment,
            endpoint=self.azure_openai_endpoint,
            api_version=self.api_version,
        )

        # Create all domain specialist agents
        for domain_id, domain_config in DOMAINS.items():
            agent = ChatAgent(
                name=domain_id,
                chat_client=chat_client,
                instructions=domain_config["instructions"],
                tools=mcp_tool,
                model=self.openai_model_name,
            )
            
            # Enter agent context
            await agent.__aenter__()
            self._domain_agents[domain_id] = agent
            
            # Create or restore thread for this domain
            thread_state_key = f"{self.session_id}_thread_{domain_id}"
            thread_state = self.state_store.get(thread_state_key)
            
            if thread_state:
                self._domain_threads[domain_id] = await agent.deserialize_thread(thread_state)
            else:
                self._domain_threads[domain_id] = agent.get_new_thread()

        self._initialized = True
        logger.info(f"[HANDOFF] Initialized {len(self._domain_agents)} domain specialists")

    def _build_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    async def _create_mcp_tool(self, headers: Dict[str, str]) -> MCPStreamableHTTPTool | None:
        if not self.mcp_server_uri:
            logger.warning("MCP_SERVER_URI is not configured; agents will run without MCP tools.")
            return None

        tool = MCPStreamableHTTPTool(
            name="mcp-streamable",
            url=self.mcp_server_uri,
            headers=headers,
            timeout=30,
            request_timeout=30,
        )
        
        return tool

    async def _build_context_prefix(self, from_domain: str, to_domain: str) -> str | None:
        """
        Build a context prefix to prepend to the user's prompt on handoff.
        
        Args:
            from_domain: Previous domain specialist
            to_domain: New domain specialist
            
        Returns:
            Context prefix string or None if no context to transfer
        """
        if self._context_transfer_turns == 0:
            logger.info(f"[HANDOFF] Context transfer disabled (HANDOFF_CONTEXT_TRANSFER_TURNS=0)")
            return None
            
        # Get chat history
        history = self.chat_history
        if not history:
            logger.info(f"[HANDOFF] No chat history to transfer")
            return None
        
        # Determine how much history to transfer
        if self._context_transfer_turns == -1:
            # Transfer all history
            context_messages = history
            logger.info(f"[HANDOFF] Transferring all {len(history)} messages to {to_domain}")
        else:
            # Transfer last N turns (each turn = user + assistant pair)
            turns_to_transfer = self._context_transfer_turns * 2  # Each turn has 2 messages
            context_messages = history[-turns_to_transfer:] if len(history) > turns_to_transfer else history
            logger.info(f"[HANDOFF] Transferring last {self._context_transfer_turns} turns ({len(context_messages)} messages) to {to_domain}")
        
        # Build context summary
        context_parts = []
        for msg in context_messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if role == "user":
                context_parts.append(f"User: {content}")
            elif role == "assistant":
                context_parts.append(f"Previous Specialist: {content}")
        
        context_summary = "\n".join(context_parts)
        
        # Build context prefix
        context_prefix = (
            f"[CONTEXT FROM PREVIOUS CONVERSATION]\n"
            f"The user was previously speaking with the {DOMAINS[from_domain]['name']}.\n"
            f"Here is the recent conversation history for your reference:\n\n"
            f"{context_summary}\n\n"
            f"[END OF CONTEXT]\n"
            f"Now, please address their current request:"
        )
        
        logger.info(f"[HANDOFF] Built context prefix with {len(context_messages)} messages for {to_domain}")
        return context_prefix

    async def _classify_intent(self, user_message: str, current_domain: str | None) -> Dict[str, Any]:
        """
        Use a vanilla LLM call to classify user intent and detect domain changes.
        
        Returns:
            {
                "domain": str,
                "is_domain_change": bool,
                "confidence": float,
                "reasoning": str
            }
        """
        # If no current domain, default to crm_billing
        if not current_domain:
            return {
                "domain": "crm_billing",
                "is_domain_change": True,
                "confidence": 1.0,
                "reasoning": "First message, routing to CRM & Billing"
            }

        # Build classification prompt
        prompt = INTENT_CLASSIFIER_PROMPT.format(
            current_domain=current_domain,
            user_message=user_message
        )

        # Make direct chat client call (no agent wrapper needed)
        chat_client = AzureOpenAIChatClient(
            api_key=self.azure_openai_key,
            deployment_name=self.azure_deployment,
            endpoint=self.azure_openai_endpoint,
            api_version=self.api_version,
        )

        try:
            messages = [ChatMessage(role=Role.USER, text=prompt)]
            response = await chat_client.get_response(messages, model=self.openai_model_name)
            
            # Parse JSON response
            response_text = response.messages[0].text
            result = json.loads(response_text)
            
            logger.info(f"[HANDOFF] Intent classification: {result}")
            return result
            
        except Exception as exc:
            logger.error(f"[HANDOFF] Intent classification failed: {exc}", exc_info=True)
            # Default to current domain on error
            return {
                "domain": current_domain,
                "is_domain_change": False,
                "confidence": 0.5,
                "reasoning": "Classification error, staying in current domain"
            }

    async def chat_async(self, prompt: str) -> str:
        """
        Main chat entry point with intelligent routing.
        
        Flow:
        1. Classify user intent
        2. If domain change detected, announce handoff
        3. Route to appropriate specialist agent
        4. Stream response back to user
        """
        await self._setup_agents()

        # Increment turn counter
        self._current_turn += 1
        self.state_store[self._turn_key] = self._current_turn

        # Classify intent to determine routing
        intent = await self._classify_intent(prompt, self._current_domain)
        target_domain = intent["domain"]
        is_domain_change = intent["is_domain_change"]

        # Announce handoff if domain changed
        if is_domain_change and self._current_domain:
            handoff_message = (
                f"I'll connect you with our {DOMAINS[target_domain]['name']} "
                f"who can better assist with that."
            )
            
            if self._ws_manager:
                await self._ws_manager.broadcast(
                    self.session_id,
                    {
                        "type": "handoff_announcement",
                        "from_domain": self._current_domain,
                        "to_domain": target_domain,
                        "message": handoff_message,
                    },
                )
            
            logger.info(f"[HANDOFF] Domain change: {self._current_domain} -> {target_domain}")

        # Update current domain
        previous_domain = self._current_domain
        self._current_domain = target_domain
        self.state_store[f"{self.session_id}_current_domain"] = target_domain

        # Get the specialist agent and thread
        agent = self._domain_agents[target_domain]
        thread = self._domain_threads[target_domain]
        
        # Prepare the prompt with context if this is a handoff
        actual_prompt = prompt
        if is_domain_change and previous_domain and previous_domain != target_domain:
            context_prefix = await self._build_context_prefix(previous_domain, target_domain)
            if context_prefix:
                actual_prompt = f"{context_prefix}\n\n{prompt}"
                logger.info(f"[HANDOFF] Added context prefix to prompt for {target_domain}")

        # Notify UI that agent started
        if self._ws_manager:
            await self._ws_manager.broadcast(
                self.session_id,
                {
                    "type": "agent_start",
                    "agent_id": target_domain,
                    "agent_name": DOMAINS[target_domain]["name"],
                    "show_message_in_internal_process": is_domain_change,  # Show handoff in left panel
                },
            )

        # Stream response from specialist agent
        full_response = []
        
        try:
            async for chunk in agent.run_stream(actual_prompt, thread=thread):
                # Process contents in the chunk
                if hasattr(chunk, 'contents') and chunk.contents:
                    for content in chunk.contents:
                        # Check for tool/function calls
                        if content.type == "function_call":
                            if self._ws_manager:
                                await self._ws_manager.broadcast(
                                    self.session_id,
                                    {
                                        "type": "tool_called",
                                        "agent_id": target_domain,
                                        "tool_name": content.name,
                                        "turn": self._current_turn,
                                    },
                                )
                
                # Extract text from chunk
                if hasattr(chunk, 'text') and chunk.text:
                    full_response.append(chunk.text)
                    
                    # Broadcast token to WebSocket
                    if self._ws_manager:
                        await self._ws_manager.broadcast(
                            self.session_id,
                            {
                                "type": "agent_token",
                                "agent_id": target_domain,
                                "content": chunk.text,
                            },
                        )
                        
        except Exception as exc:
            logger.error(f"[HANDOFF] Error during agent streaming: {exc}", exc_info=True)
            raise

        assistant_response = ''.join(full_response)

        # Send final result
        if self._ws_manager:
            await self._ws_manager.broadcast(
                self.session_id,
                {
                    "type": "final_result",
                    "content": assistant_response,
                },
            )

        # Update chat history
        messages = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": assistant_response},
        ]
        self.append_to_chat_history(messages)

        # Save thread state for this domain
        thread_state_key = f"{self.session_id}_thread_{target_domain}"
        new_state = await thread.serialize()
        self.state_store[thread_state_key] = new_state

        # Save overall state
        self._setstate({
            "mode": "handoff_multi_domain",
            "current_domain": target_domain,
        })

        return assistant_response
