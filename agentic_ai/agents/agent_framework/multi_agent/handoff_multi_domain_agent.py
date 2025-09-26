import logging
from typing import Any, Dict, Iterable, List

from agent_framework import (
    ChatAgent,
    MagenticBuilder,
    MCPStreamableHTTPTool,
    WorkflowOutputEvent,
)
from agent_framework.azure import AzureOpenAIChatClient  # type: ignore[import]

from agents.base_agent import BaseAgent
from .magentic_group import DictCheckpointStorage

logger = logging.getLogger(__name__)


class Agent(BaseAgent):
    """Agent Framework implementation of the domain handoff multi-agent workflow."""

    def __init__(self, state_store: Dict[str, Any], session_id: str, access_token: str | None = None) -> None:
        super().__init__(state_store, session_id)
        self._access_token = access_token

    async def chat_async(self, prompt: str) -> str:
        self._validate_configuration()

        checkpoint_state = self.state_store.setdefault(f"{self.session_id}_handoff_checkpoint", {})
        checkpoint_storage = DictCheckpointStorage(checkpoint_state)

        headers = self._build_headers()
        tools = await self._maybe_create_tools(headers)

        resume_answer = await self._resume_previous_run(checkpoint_storage, tools)
        if resume_answer:
            logger.info(
                "[AgentFramework-Handoff] Resumed unfinished workflow before handling new prompt."
            )

        participant_client = self._build_chat_client()
        manager_client = self._build_chat_client()

        task = self._render_task_with_history(prompt)
        checkpoint_storage.mark_pending_prompt(prompt)

        workflow = self._build_workflow(participant_client, manager_client, tools, checkpoint_storage)

        final_answer = await self._run_workflow(workflow, checkpoint_storage, task)
        if final_answer is None:
            logger.warning(
                "[AgentFramework-Handoff] No final answer produced; leaving checkpoint for potential resume."
            )
            return (
                "The agent team is still working through the previous request."
                " Please try again shortly so we can resume from the saved progress."
            )

        cleaned_answer = final_answer.replace("FINAL_ANSWER:", "").strip()

        self.append_to_chat_history(
            [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": cleaned_answer},
            ]
        )

        checkpoint_storage.clear_all()
        self._setstate({"mode": "handoff_multi_domain"})

        return cleaned_answer

    def _validate_configuration(self) -> None:
        if not all([self.azure_openai_key, self.azure_deployment, self.azure_openai_endpoint, self.api_version]):
            raise RuntimeError(
                "Azure OpenAI configuration is incomplete. Ensure AZURE_OPENAI_API_KEY, "
                "AZURE_OPENAI_CHAT_DEPLOYMENT, AZURE_OPENAI_ENDPOINT, and AZURE_OPENAI_API_VERSION are set."
            )

    def _build_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    async def _maybe_create_tools(self, headers: Dict[str, str]) -> List[MCPStreamableHTTPTool] | None:
        if not self.mcp_server_uri:
            logger.warning("MCP_SERVER_URI is not configured; multi-agent team will run without MCP tools.")
            return None

        tool = MCPStreamableHTTPTool(
            name="mcp-streamable",
            url=self.mcp_server_uri,
            headers=headers,
            timeout=30,
            request_timeout=30,
        )
        return [tool]

    def _build_chat_client(self) -> AzureOpenAIChatClient:
        return AzureOpenAIChatClient(
            api_key=self.azure_openai_key,
            deployment_name=self.azure_deployment,
            endpoint=self.azure_openai_endpoint,
            api_version=self.api_version,
        )

    async def _resume_previous_run(
        self,
        checkpoint_storage: DictCheckpointStorage,
        tools: List[MCPStreamableHTTPTool] | None,
    ) -> str | None:
        resume_id = checkpoint_storage.latest_checkpoint_id
        if not resume_id:
            return None

        logger.info("[AgentFramework-Handoff] Attempting to resume workflow from checkpoint %s", resume_id)
        participant_client = self._build_chat_client()
        manager_client = self._build_chat_client()
        workflow = self._build_workflow(participant_client, manager_client, tools, checkpoint_storage)

        try:
            final_answer = await self._run_workflow(workflow, checkpoint_storage, None, resume_id)
        except Exception as exc:  # pragma: no cover - defensive resume path
            logger.error("[AgentFramework-Handoff] Failed to resume workflow: %s", exc, exc_info=True)
            checkpoint_storage.clear_all()
            return None

        if final_answer is None:
            checkpoint_storage.clear_all()
            return None

        cleaned_answer = final_answer.replace("FINAL_ANSWER:", "").strip()
        original_prompt = checkpoint_storage.consume_pending_prompt()
        if original_prompt:
            self.append_to_chat_history(
                [
                    {"role": "user", "content": original_prompt},
                    {"role": "assistant", "content": cleaned_answer},
                ]
            )
        else:
            self.append_to_chat_history([
                {"role": "assistant", "content": cleaned_answer},
            ])

        checkpoint_storage.clear_all()
        return cleaned_answer

    def _build_workflow(
        self,
        participant_client: AzureOpenAIChatClient,
        manager_client: AzureOpenAIChatClient,
        tools: List[MCPStreamableHTTPTool] | None,
        checkpoint_storage: DictCheckpointStorage,
    ) -> Any:
        participants = self._create_participants(participant_client, tools)

        manager_instructions = (
            "You coordinate a Contoso support handoff workflow. Engage the coordinator first to clarify the user's"
            " goals and determine the best specialist to help. Explicitly hand the work to exactly one specialist"
            " at a time, allowing them to leverage tools and respond before deciding whether to loop back."
            " Only the coordinator should deliver the final customer-facing response prefixed with 'FINAL_ANSWER:'."
            " Ensure specialists do not produce FINAL_ANSWER unless resolving the case directly."
        )

        return (
            MagenticBuilder()
            .participants(**participants)
            .with_standard_manager(
                chat_client=manager_client,
                instructions=manager_instructions,
                max_round_count=12,
                max_stall_count=3,
                max_reset_count=2,
            )
            .with_checkpointing(checkpoint_storage)
            .build()
        )

    def _create_participants(
        self,
        participant_client: AzureOpenAIChatClient,
        tools: Iterable[MCPStreamableHTTPTool] | None,
    ) -> Dict[str, ChatAgent]:
        shared_tools = list(tools) if tools else None

        return {
            "coordinator": ChatAgent(
                name="coordinator",
                description=(
                    "Coordinator who greets customers, clarifies intent, routes to specialists, and synthesizes FINAL_ANSWER responses."
                ),
                instructions=(
                    "You are the Coordinator Agent.\n"
                    "- Begin each interaction by confirming the user's intent and required outcome.\n"
                    "- Decide which specialist (crm_billing, product_promotions, security_authentication) should take over.\n"
                    "- When delegating, clearly call on the specialist by name and provide context.\n"
                    "- Specialists may return the task to you when they require routing elsewhere or when they need you to deliver the summary.\n"
                    "- Only provide FINAL_ANSWER when you are closing the conversation with the user.\n"
                    "- Encourage tool usage by specialists and integrate their findings into a concise wrap-up."
                ),
                chat_client=participant_client,
                tools=None,
                model=self.openai_model_name,
            ),
            "crm_billing": ChatAgent(
                name="crm_billing",
                description=(
                    "Specialist for subscriptions, billing, invoices, payments, and account adjustments."
                ),
                instructions=(
                    "You are the CRM & Billing Agent.\n"
                    "- Investigate account, subscription, invoice, and payment details using the available tools.\n"
                    "- Reference Knowledge Base policy guidance to ensure compliant answers.\n"
                    "- If the request is outside billing, notify the coordinator so another specialist can assist.\n"
                    "- Provide structured findings and recommended next steps. Do not use FINAL_ANSWER unless solving the issue directly."
                ),
                chat_client=participant_client,
                tools=shared_tools,
                model=self.openai_model_name,
            ),
            "product_promotions": ChatAgent(
                name="product_promotions",
                description=(
                    "Specialist covering product availability, plan changes, promotions, and eligibility requests."
                ),
                instructions=(
                    "You are the Product & Promotions Agent.\n"
                    "- Retrieve product availability, promotional offers, and eligibility requirements via the provided tools.\n"
                    "- Augment answers with relevant Knowledge Base details and surface policy caveats.\n"
                    "- Stay within your scope; if another domain is needed, hand the task back to the coordinator.\n"
                    "- Share findings clearly and avoid FINAL_ANSWER unless directly resolving the user's request."
                ),
                chat_client=participant_client,
                tools=shared_tools,
                model=self.openai_model_name,
            ),
            "security_authentication": ChatAgent(
                name="security_authentication",
                description=(
                    "Specialist for authentication failures, lockouts, security incidents, and remediation guidance."
                ),
                instructions=(
                    "You are the Security & Authentication Agent.\n"
                    "- Analyze authentication logs, lockout records, and security incidents using the tools.\n"
                    "- Cross-reference security and compliance guidance in the Knowledge Base.\n"
                    "- Flag risks, confirm mitigations, and escalate urgent threats.\n"
                    "- Return the task to the coordinator when additional routing is required. Do not use FINAL_ANSWER unless closing the issue yourself."
                ),
                chat_client=participant_client,
                tools=shared_tools,
                model=self.openai_model_name,
            ),
        }

    async def _run_workflow(
        self,
        workflow: Any,
        checkpoint_storage: DictCheckpointStorage,
        task: str | None,
        checkpoint_id: str | None = None,
    ) -> str | None:
        final_answer: str | None = None

        try:
            if checkpoint_id:
                async for event in workflow.run_stream_from_checkpoint(checkpoint_id, checkpoint_storage):
                    if isinstance(event, WorkflowOutputEvent):
                        final_answer = self._extract_text_from_event(event)
            else:
                async for event in workflow.run_stream(task):
                    if isinstance(event, WorkflowOutputEvent):
                        final_answer = self._extract_text_from_event(event)
        except Exception as exc:
            logger.error("[AgentFramework-Handoff] workflow failure: %s", exc, exc_info=True)
            return None

        return final_answer

    @staticmethod
    def _extract_text_from_event(event: WorkflowOutputEvent) -> str:
        data = event.data
        if hasattr(data, "text") and getattr(data, "text"):
            return str(getattr(data, "text"))
        return str(data)

    def _render_task_with_history(self, prompt: str) -> str:
        if not self.chat_history:
            return prompt

        formatted_turns = []
        for turn in self.chat_history:
            role = turn.get("role", "user").lower()
            speaker = "User" if role == "user" else "Assistant"
            content = turn.get("content", "")
            formatted_turns.append(f"{speaker}: {content}")

        formatted_turns.append(f"User: {prompt}")
        formatted_turns.append(
            "System: Provide an updated response that respects the prior conversation while focusing on the latest user message."
        )
        return "\n".join(formatted_turns)


__all__ = ["Agent", "DictCheckpointStorage"]
