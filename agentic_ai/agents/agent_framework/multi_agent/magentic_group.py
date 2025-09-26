import logging
from typing import Any, Dict, Iterable, List

from agent_framework import (
    ChatAgent,
    MagenticBuilder,
    MCPStreamableHTTPTool,
    WorkflowCheckpoint,
    WorkflowOutputEvent,
    CheckpointStorage,
)
from agent_framework.azure import AzureOpenAIChatClient  # type: ignore[import]

from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


class DictCheckpointStorage(CheckpointStorage):
    """Dictionary-backed checkpoint storage that persists across Agent instances."""

    _RETENTION = 5

    def __init__(self, backing_store: Dict[str, Any]) -> None:
        self._backing = backing_store
        self._checkpoints: Dict[str, Dict[str, Any]] = backing_store.setdefault("checkpoints", {})

    async def save_checkpoint(self, checkpoint: WorkflowCheckpoint) -> str:
        self._checkpoints[checkpoint.checkpoint_id] = checkpoint.to_dict()
        self._backing["latest_checkpoint"] = checkpoint.checkpoint_id
        self._backing["workflow_id"] = checkpoint.workflow_id

        if len(self._checkpoints) > self._RETENTION:
            sorted_ids = sorted(
                self._checkpoints.items(),
                key=lambda item: (item[1].get("timestamp", ""), item[1].get("iteration_count", 0)),
            )
            for checkpoint_id, _ in sorted_ids[:-self._RETENTION]:
                self._checkpoints.pop(checkpoint_id, None)
        return checkpoint.checkpoint_id

    async def load_checkpoint(self, checkpoint_id: str) -> WorkflowCheckpoint | None:
        data = self._checkpoints.get(checkpoint_id)
        if not data:
            return None
        return WorkflowCheckpoint.from_dict(data)

    async def list_checkpoint_ids(self, workflow_id: str | None = None) -> List[str]:
        if workflow_id is None:
            return list(self._checkpoints.keys())
        return [cid for cid, data in self._checkpoints.items() if data.get("workflow_id") == workflow_id]

    async def list_checkpoints(self, workflow_id: str | None = None) -> List[WorkflowCheckpoint]:
        ids = await self.list_checkpoint_ids(workflow_id)
        return [WorkflowCheckpoint.from_dict(self._checkpoints[cid]) for cid in ids]

    async def delete_checkpoint(self, checkpoint_id: str) -> bool:
        removed = self._checkpoints.pop(checkpoint_id, None)
        if removed and self._backing.get("latest_checkpoint") == checkpoint_id:
            self._backing.pop("latest_checkpoint", None)
        return removed is not None

    @property
    def latest_checkpoint_id(self) -> str | None:
        return self._backing.get("latest_checkpoint")

    def mark_pending_prompt(self, prompt: str) -> None:
        self._backing["pending_prompt"] = prompt

    def consume_pending_prompt(self) -> str | None:
        prompt = self._backing.get("pending_prompt")
        if prompt is not None:
            self._backing.pop("pending_prompt", None)
        return prompt

    def clear_all(self) -> None:
        self._checkpoints.clear()
        self._backing.pop("latest_checkpoint", None)
        self._backing.pop("workflow_id", None)
        self._backing.pop("pending_prompt", None)


class Agent(BaseAgent):
    """Agent Framework implementation of the collaborative Magentic team."""

    def __init__(self, state_store: Dict[str, Any], session_id: str, access_token: str | None = None) -> None:
        super().__init__(state_store, session_id)
        self._access_token = access_token

    async def chat_async(self, prompt: str) -> str:
        self._validate_configuration()

        checkpoint_state = self.state_store.setdefault(f"{self.session_id}_magentic_checkpoint", {})
        checkpoint_storage = DictCheckpointStorage(checkpoint_state)

        headers = self._build_headers()
        tools = await self._maybe_create_tools(headers)

        # First resume any previous unfinished run before processing the new prompt
        resume_answer = await self._resume_previous_run(checkpoint_storage, tools)
        if resume_answer:
            logger.info("[AgentFramework-Magentic] Resumed unfinished workflow before handling new prompt.")

        participant_client = self._build_chat_client()
        manager_client = self._build_chat_client()

        task = self._render_task_with_history(prompt)
        checkpoint_storage.mark_pending_prompt(prompt)

        workflow = self._build_workflow(participant_client, manager_client, tools, checkpoint_storage)

        final_answer = await self._run_workflow(workflow, checkpoint_storage, task)
        if final_answer is None:
            logger.warning(
                "[AgentFramework-Magentic] No final answer produced; leaving checkpoint for potential resume."
            )
            return (
                "The agent team is still working through the previous request. Please try again in a moment so we "
                "can resume from the saved progress."
            )

        cleaned_answer = final_answer.replace("FINAL_ANSWER:", "").strip()

        self.append_to_chat_history(
            [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": cleaned_answer},
            ]
        )

        checkpoint_storage.clear_all()
        self._setstate({"mode": "magentic_collaboration"})

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

        logger.info("[AgentFramework-Magentic] Attempting to resume workflow from checkpoint %s", resume_id)
        participant_client = self._build_chat_client()
        manager_client = self._build_chat_client()
        workflow = self._build_workflow(participant_client, manager_client, tools, checkpoint_storage)

        try:
            final_answer = await self._run_workflow(workflow, checkpoint_storage, None, resume_id)
        except Exception as exc:  # pragma: no cover - defensive resume path
            logger.error("[AgentFramework-Magentic] Failed to resume workflow: %s", exc, exc_info=True)
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
            self.append_to_chat_history(
                [
                    {"role": "assistant", "content": cleaned_answer},
                ]
            )

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
            "You are the Analysis & Planning orchestrator for a team of specialists handling Contoso customer support. "
            "Break down the user's needs, decide which specialist should respond, and integrate their findings into the final answer. "
            "Encourage tool usage, avoid speculative answers, and when satisfied deliver the final customer response prefixed with 'FINAL_ANSWER:'."
        )

        return (
            MagenticBuilder()
            .participants(**participants)
            .with_standard_manager(
                chat_client=manager_client,
                instructions=manager_instructions,
                max_round_count=10,
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
        return {
            "crm_billing": ChatAgent(
                name="crm_billing",
                description=(
                    "Agent specializing in customer account, subscription, billing inquiries, invoices, payments, and related policy checks."
                ),
                instructions=(
                    "You are the CRM & Billing Agent.\n"
                    "- Query structured CRM / billing systems for account, subscription, invoice, and payment information as needed.\n"
                    "- Cross-check Knowledge Base articles on billing policies, payment processing, refund rules, and compliance before answering.\n"
                    "- Reply with concise, structured information and flag any policy concerns you detect.\n"
                    "Only respond within your domain and prefer citing tool-derived facts over assumptions."
                ),
                chat_client=participant_client,
                tools=list(tools) if tools else None,
                model=self.openai_model_name,
            ),
            "product_promotions": ChatAgent(
                name="product_promotions",
                description=(
                    "Agent for retrieving and explaining product availability, promotions, discounts, eligibility, and terms."
                ),
                instructions=(
                    "You are the Product & Promotions Agent.\n"
                    "- Retrieve promotional offers, product availability, eligibility criteria, and discount information from structured sources.\n"
                    "- Cross-reference Knowledge Base FAQs, terms & conditions, and best practices in every response.\n"
                    "- Provide factual, up-to-date product/promo details and stay within your scope."
                ),
                chat_client=participant_client,
                tools=list(tools) if tools else None,
                model=self.openai_model_name,
            ),
            "security_authentication": ChatAgent(
                name="security_authentication",
                description=(
                    "Agent focusing on security incidents, authentication issues, lockouts, and risk mitigation guidance."
                ),
                instructions=(
                    "You are the Security & Authentication Agent.\n"
                    "- Investigate authentication logs, account lockouts, and security incidents.\n"
                    "- Always cross-reference Knowledge Base security policies and troubleshooting guides.\n"
                    "- Return clear risk assessments and recommended remediation steps grounded in tool outputs."
                ),
                chat_client=participant_client,
                tools=list(tools) if tools else None,
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
            logger.error("[AgentFramework-Magentic] workflow failure: %s", exc, exc_info=True)
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
