import asyncio
import inspect
import json
import logging
import os
from threading import Lock as ThreadLock
from typing import Any, Callable, Dict, Iterable, List, Optional, cast

from agent_framework import (
    ChatAgent,
    MagenticBuilder,
    MCPStreamableHTTPTool,
    WorkflowCheckpoint,
    WorkflowOutputEvent,
    CheckpointStorage,
    MagenticCallbackEvent,
    MagenticCallbackMode,
    MagenticOrchestratorMessageEvent,
    MagenticAgentDeltaEvent,
    MagenticAgentMessageEvent,
    MagenticFinalResultEvent,
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
        self._async_lock = asyncio.Lock()
        self._sync_lock = ThreadLock()

    async def save_checkpoint(self, checkpoint: WorkflowCheckpoint) -> str:
        async with self._async_lock:
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
        async with self._async_lock:
            data = self._checkpoints.get(checkpoint_id)
            if not data:
                return None
            return WorkflowCheckpoint.from_dict(data)

    async def list_checkpoint_ids(self, workflow_id: str | None = None) -> List[str]:
        async with self._async_lock:
            if workflow_id is None:
                return list(self._checkpoints.keys())
            return [cid for cid, data in self._checkpoints.items() if data.get("workflow_id") == workflow_id]

    async def list_checkpoints(self, workflow_id: str | None = None) -> List[WorkflowCheckpoint]:
        async with self._async_lock:
            if workflow_id is None:
                ids = list(self._checkpoints.keys())
            else:
                ids = [cid for cid, data in self._checkpoints.items() if data.get("workflow_id") == workflow_id]
            return [WorkflowCheckpoint.from_dict(self._checkpoints[cid]) for cid in ids]

    async def delete_checkpoint(self, checkpoint_id: str) -> bool:
        async with self._async_lock:
            removed = self._checkpoints.pop(checkpoint_id, None)
            if removed and self._backing.get("latest_checkpoint") == checkpoint_id:
                self._backing.pop("latest_checkpoint", None)
            return removed is not None

    @property
    def latest_checkpoint_id(self) -> str | None:
        with self._sync_lock:
            return self._backing.get("latest_checkpoint")

    def mark_pending_prompt(self, prompt: str) -> None:
        with self._sync_lock:
            self._backing["pending_prompt"] = prompt

    def consume_pending_prompt(self) -> str | None:
        with self._sync_lock:
            prompt = self._backing.get("pending_prompt")
            if prompt is not None:
                self._backing.pop("pending_prompt", None)
            return prompt

    def clear_all(self) -> None:
        with self._sync_lock:
            self._checkpoints.clear()
            self._backing.pop("latest_checkpoint", None)
            self._backing.pop("workflow_id", None)
            self._backing.pop("pending_prompt", None)


class Agent(BaseAgent):
    """Agent Framework implementation of the collaborative Magentic team."""

    DEFAULT_MANAGER_INSTRUCTIONS = (
        "You are the Analysis & Planning orchestrator for a team of specialists handling Contoso customer support. "
        "Break down the user's needs, decide which specialist should respond, and integrate their findings into the final answer. "
        "**IMPORTANT: Instruct participants to use their tools to retrieve factual data. Do not allow speculative or hallucinated answers.** "
        "Each participant MUST call the appropriate tool and cite the tool results (with IDs, timestamps, or specific data points) in their response. "
        "If no tool can answer the question, the participant should explicitly state this limitation. "
        "After gathering sufficient information from specialists (typically 1-3 rounds), synthesize their responses and "
        "deliver the final customer response prefixed with 'FINAL_ANSWER:'. "
        "**DO NOT loop indefinitely - once you have tool-backed answers from the relevant specialists, conclude with FINAL_ANSWER.**"
    )

    def __init__(
        self,
        state_store: Dict[str, Any],
        session_id: str,
        access_token: str | None = None,
        *,
        config: Optional[Dict[str, Any]] = None,
        checkpoint_storage_factory: Optional[
            Callable[[Dict[str, Any], str], CheckpointStorage]
        ] = None,
    ) -> None:
        super().__init__(state_store, session_id)
        self._access_token = access_token
        self._config = self._load_effective_config(config)
        self._checkpoint_storage_factory = (
            checkpoint_storage_factory
            or self.state_store.get("magentic_checkpoint_storage_factory")
        )
        storage_override = self.state_store.get("magentic_checkpoint_storage")
        self._checkpoint_storage_override: Optional[CheckpointStorage] = self._coerce_checkpoint_storage(
            storage_override
        )
        if storage_override and not self._checkpoint_storage_override:
            logger.warning(
                "[AgentFramework-Magentic] Ignoring checkpoint storage override because it does not implement CheckpointStorage."
            )
        self._participant_client: Optional[AzureOpenAIChatClient] = None
        self._manager_client: Optional[AzureOpenAIChatClient] = None
        self._workflow_event_logging_enabled = bool(self._config.get("log_workflow_events", False))
        self._enable_plan_review = bool(self._config.get("enable_plan_review", False))
        self._manager_instructions = self._config.get(
            "manager_instructions", self.DEFAULT_MANAGER_INSTRUCTIONS
        )
        self._max_round_count = int(self._config.get("max_round_count", 4))
        self._max_stall_count = int(self._config.get("max_stall_count", 2))
        self._max_reset_count = int(self._config.get("max_reset_count", 1))
        self._participant_overrides: Dict[str, Dict[str, Any]] = self._config.get("participant_overrides", {})
        self._pending_prompt_state_key = f"{self.session_id}_magentic_pending_prompt"
        self._in_memory_checkpoint_storage: Optional[DictCheckpointStorage] = None
        self._ws_manager = None  # Will be set from backend if available
        self._stream_agent_id: Optional[str] = None
        self._stream_line_open: bool = False

    def set_websocket_manager(self, manager: Any) -> None:
        """Allow backend to inject WebSocket manager for streaming events."""
        self._ws_manager = manager

    async def chat_async(self, prompt: str) -> str:
        self._validate_configuration()

        checkpoint_state = self.state_store.setdefault(f"{self.session_id}_magentic_checkpoint", {})
        checkpoint_storage = self._create_checkpoint_storage(checkpoint_state)

        headers = self._build_headers()
        tools = await self._maybe_create_tools(headers)

        # First resume any previous unfinished run before processing the new prompt
        resume_answer = await self._resume_previous_run(checkpoint_storage, tools)
        if resume_answer:
            logger.info("[AgentFramework-Magentic] Resumed unfinished workflow before handling new prompt.")

        participant_client = self._get_participant_client()
        manager_client = self._get_manager_client()

        task = self._render_task_with_history(prompt)
        await self._mark_pending_prompt(checkpoint_storage, prompt)

        workflow = await self._build_workflow(participant_client, manager_client, tools, checkpoint_storage)

        final_answer = await self._run_workflow(workflow, checkpoint_storage, task)
        if final_answer is None:
            logger.warning(
                "[AgentFramework-Magentic] No final answer produced; leaving checkpoint for potential resume."
            )
            return (
                "The agent team is still working through the previous request. Please try again in a moment so we "
                "can resume from the saved progress."
            )

        cleaned_answer = self._sanitize_final_answer(final_answer)
        if cleaned_answer is None:
            return (
                "The Magentic coordinator could not produce a final response. Please try again later or contact support."
            )

        self.append_to_chat_history(
            [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": cleaned_answer},
            ]
        )

        await self._reset_checkpoint_progress(checkpoint_storage)
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

        logger.info(f"[MCP SETUP] Creating MCP tool with URI: {self.mcp_server_uri}")
        request_headers = dict(headers)
        header_overrides = self._config.get("mcp_headers")
        if isinstance(header_overrides, dict):
            request_headers.update({str(key): str(value) for key, value in header_overrides.items()})

        logger.info(f"[MCP SETUP] Request headers: {list(request_headers.keys())}")
        timeout_seconds = int(self._config.get("mcp_timeout_seconds", 30))
        request_timeout_seconds = int(self._config.get("mcp_request_timeout_seconds", timeout_seconds))
        retry_attempts = max(1, int(self._config.get("mcp_startup_retries", 1)))
        retry_backoff = float(self._config.get("mcp_retry_backoff_seconds", 2.0))

        last_error: Exception | None = None
        for attempt in range(1, retry_attempts + 1):
            try:
                tool = MCPStreamableHTTPTool(
                    name="mcp-streamable",
                    url=self.mcp_server_uri,
                    headers=request_headers,
                    timeout=timeout_seconds,
                    request_timeout=request_timeout_seconds,
                )
                logger.info(f"[MCP SETUP] Successfully created MCP tool: {tool}")
                return [tool]
            except Exception as exc:  # pragma: no cover - defensive path
                last_error = exc
                if attempt < retry_attempts:
                    wait_time = retry_backoff * attempt
                    logger.warning(
                        "Failed to initialise MCP tool (attempt %s/%s): %s. Retrying in %.1fs.",
                        attempt,
                        retry_attempts,
                        exc,
                        wait_time,
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        "Failed to initialise MCP tool after %s attempts: %s",
                        retry_attempts,
                        exc,
                        exc_info=True,
                    )

        return None

    def _get_participant_client(self) -> AzureOpenAIChatClient:
        if self._participant_client is None:
            self._participant_client = self._build_chat_client()
        return self._participant_client

    def _get_manager_client(self) -> AzureOpenAIChatClient:
        if self._manager_client is None:
            self._manager_client = self._build_chat_client()
        return self._manager_client

    def _build_chat_client(self) -> AzureOpenAIChatClient:
        return AzureOpenAIChatClient(
            api_key=self.azure_openai_key,
            deployment_name=self.azure_deployment,
            endpoint=self.azure_openai_endpoint,
            api_version=self.api_version,
        )

    async def _resume_previous_run(
        self,
        checkpoint_storage: CheckpointStorage,
        tools: List[MCPStreamableHTTPTool] | None,
    ) -> str | None:
        resume_id = await self._get_latest_checkpoint_id(checkpoint_storage)
        if not resume_id:
            return None

        logger.info("[AgentFramework-Magentic] Attempting to resume workflow from checkpoint %s", resume_id)
        participant_client = self._get_participant_client()
        manager_client = self._get_manager_client()
        workflow = await self._build_workflow(participant_client, manager_client, tools, checkpoint_storage)

        try:
            final_answer = await self._run_workflow(workflow, checkpoint_storage, None, resume_id)
        except Exception as exc:  # pragma: no cover - defensive resume path
            logger.error("[AgentFramework-Magentic] Failed to resume workflow: %s", exc, exc_info=True)
            await self._reset_checkpoint_progress(checkpoint_storage)
            return None

        if final_answer is None:
            await self._reset_checkpoint_progress(checkpoint_storage)
            return None

        cleaned_answer = self._sanitize_final_answer(final_answer)
        if cleaned_answer is None:
            await self._reset_checkpoint_progress(checkpoint_storage)
            return None
        original_prompt = await self._consume_pending_prompt(checkpoint_storage)
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

        await self._reset_checkpoint_progress(checkpoint_storage)
        return cleaned_answer

    async def _build_workflow(
        self,
        participant_client: AzureOpenAIChatClient,
        manager_client: AzureOpenAIChatClient,
        tools: List[MCPStreamableHTTPTool] | None,
        checkpoint_storage: CheckpointStorage,
    ) -> Any:
        participants = await self._create_participants(participant_client, tools)

        builder = MagenticBuilder().participants(**participants)
        
        # Register streaming callback if WebSocket is available (MUST be before with_standard_manager)
        if self._ws_manager:
            logger.info(f"[STREAMING] Registering streaming callback for magentic events, session_id={self.session_id}")
            logger.info(f"[STREAMING] WebSocket manager type: {type(self._ws_manager)}")
            logger.info(f"[STREAMING] Callback function: {self._stream_magentic_event}")
            builder = builder.on_event(self._stream_magentic_event, mode=MagenticCallbackMode.STREAMING)
            logger.info("[STREAMING] Callback registered successfully")
        elif self._workflow_event_logging_enabled:
            logger.info("[STREAMING] Using workflow event logging instead of streaming")
            builder = builder.on_event(self._log_workflow_event)
        
        builder = (
            builder
            .with_standard_manager(
                chat_client=manager_client,
                instructions=self._manager_instructions,
                max_round_count=self._max_round_count,
                max_stall_count=self._max_stall_count,
                max_reset_count=self._max_reset_count,
            )
            .with_checkpointing(checkpoint_storage)
        )

        # Optional: enable plan review if available
        if self._enable_plan_review:
            enable_plan_review = getattr(builder, "enable_plan_review", None)
            if callable(enable_plan_review):
                try:
                    builder = enable_plan_review()
                except Exception as exc:
                    logger.warning(
                        "[AgentFramework-Magentic] Failed to enable plan review: %s", exc
                    )
            else:
                logger.debug(
                    "[AgentFramework-Magentic] Plan review requested but not available in this framework version."
                )

        return builder.build()

    async def _create_participants(
        self,
        participant_client: AzureOpenAIChatClient,
        tools: Iterable[MCPStreamableHTTPTool] | None,
    ) -> Dict[str, ChatAgent]:
        # CRITICAL: ChatAgent expects a single MCPStreamableHTTPTool, not a list
        shared_tool = tools[0] if tools else None
        logger.info(f"[MCP PARTICIPANTS] Creating participants with shared_tool: {shared_tool}")
        
        base_definitions: Dict[str, Dict[str, Any]] = {
            "crm_billing": {
                "name": "crm_billing",
                "description": (
                    "Agent specializing in customer account, subscription, billing inquiries, invoices, payments, and related policy checks."
                ),
                "instructions": (
                    "You are the CRM & Billing Agent.\n"
                    "**CRITICAL: You MUST use your tools to retrieve factual data. NEVER guess or hallucinate information.**\n"
                    "- For ANY customer-specific question, call the appropriate tool (get_customer_detail, get_billing_summary, etc.).\n"
                    "- Query structured CRM / billing systems for account, subscription, invoice, and payment information.\n"
                    "- Cross-check Knowledge Base articles on billing policies, payment processing, refund rules, and compliance.\n"
                    "- Reply with concise, structured information and flag any policy concerns you detect.\n"
                    "- Explicitly cite the tool results (customer ID, invoice numbers, amounts, timestamps) that back your answer.\n"
                    "- If no tool can answer the question, state 'I cannot answer this without the appropriate tool' instead of guessing."
                ),
            },
            "product_promotions": {
                "name": "product_promotions",
                "description": (
                    "Agent for retrieving and explaining product availability, promotions, discounts, eligibility, and terms."
                ),
                "instructions": (
                    "You are the Product & Promotions Agent.\n"
                    "**CRITICAL: You MUST use your tools to retrieve factual data. NEVER guess or hallucinate information.**\n"
                    "- For ANY product or promotion question, call the appropriate tool (get_products, get_promotions, get_eligible_promotions, etc.).\n"
                    "- Retrieve promotional offers, product availability, eligibility criteria, and discount information from structured sources.\n"
                    "- Cross-reference Knowledge Base FAQs, terms & conditions, and best practices in every response.\n"
                    "- Provide factual, up-to-date product/promo details, and cite the tool outputs or documents you referenced.\n"
                    "- If no tool can answer the question, state 'I cannot answer this without the appropriate tool' instead of guessing."
                ),
            },
            "security_authentication": {
                "name": "security_authentication",
                "description": (
                    "Agent focusing on security incidents, authentication issues, lockouts, and risk mitigation guidance."
                ),
                "instructions": (
                    "You are the Security & Authentication Agent.\n"
                    "**CRITICAL: You MUST use your tools to retrieve factual data. NEVER guess or hallucinate information.**\n"
                    "- For ANY security or authentication question, call the appropriate tool (get_security_logs, unlock_account, etc.).\n"
                    "- Investigate authentication logs, account lockouts, and security incidents using your tools.\n"
                    "- Always cross-reference Knowledge Base security policies and troubleshooting guides.\n"
                    "- Return clear risk assessments, list the log entries or tool findings you relied on, and recommend remediation steps grounded in those outputs.\n"
                    "- If no tool can answer the question, state 'I cannot answer this without the appropriate tool' instead of guessing."
                ),
            },
        }

        participants: Dict[str, ChatAgent] = {}
        for participant_id, defaults in base_definitions.items():
            agent_kwargs: Dict[str, Any] = {
                **defaults,
                "chat_client": participant_client,
                "model": self.openai_model_name,
            }
            if shared_tool is not None and "tools" not in agent_kwargs:
                agent_kwargs["tools"] = shared_tool
                logger.info(f"[MCP PARTICIPANTS] Assigning MCP tool to agent '{participant_id}'")

            merged_kwargs = self._apply_participant_overrides(participant_id, agent_kwargs)
            agent = ChatAgent(**merged_kwargs)
            
            # CRITICAL: Initialize the MCP tool session just like single_agent.py does
            if shared_tool is not None:
                try:
                    await agent.__aenter__()
                    logger.info(f"[MCP PARTICIPANTS] Initialized MCP session for agent '{participant_id}'")
                except Exception as exc:
                    logger.error(f"[MCP PARTICIPANTS] Failed to initialize MCP session for '{participant_id}': {exc}")
                    raise
            
            participants[participant_id] = agent

        return participants

    def _apply_participant_overrides(self, participant_id: str, defaults: Dict[str, Any]) -> Dict[str, Any]:
        overrides = self._participant_overrides.get(participant_id, {})
        if not overrides:
            return defaults

        merged = {**defaults, **overrides}

        if overrides.get("tools") == "inherit":
            merged["tools"] = defaults.get("tools")

        return merged

    async def _run_workflow(
        self,
        workflow: Any,
        checkpoint_storage: CheckpointStorage,
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

    async def _log_workflow_event(self, event: Any) -> None:
        if isinstance(event, WorkflowOutputEvent):
            logger.debug("[AgentFramework-Magentic] Workflow output event: %s", event.data)
        else:
            logger.debug("[AgentFramework-Magentic] Workflow event emitted: %s", getattr(event, "name", type(event).__name__))

    async def _stream_magentic_event(self, event: MagenticCallbackEvent) -> None:
        """Stream Magentic workflow events to WebSocket clients."""
        if not self._ws_manager:
            return

        try:
            if isinstance(event, MagenticOrchestratorMessageEvent):
                # Manager/orchestrator thinking or planning
                message_text = getattr(event.message, "text", "") if event.message else ""
                await self._ws_manager.broadcast(
                    self.session_id,
                    {
                        "type": "orchestrator",
                        "kind": event.kind,  # e.g., "plan", "progress", "result"
                        "content": message_text,
                    },
                )

            elif isinstance(event, MagenticAgentDeltaEvent):
                # Streaming token from participant agent
                if self._stream_agent_id != event.agent_id or not self._stream_line_open:
                    self._stream_agent_id = event.agent_id
                    self._stream_line_open = True
                    await self._ws_manager.broadcast(
                        self.session_id,
                        {
                            "type": "agent_start",
                            "agent_id": event.agent_id,
                        },
                    )

                await self._ws_manager.broadcast(
                    self.session_id,
                    {
                        "type": "agent_token",
                        "agent_id": event.agent_id,
                        "content": event.text,
                    },
                )

            elif isinstance(event, MagenticAgentMessageEvent):
                # Complete message from participant
                if self._stream_line_open:
                    self._stream_line_open = False

                msg = event.message
                if msg:
                    message_text = getattr(msg, "text", "")
                    role = getattr(msg, "role", None)
                    
                    # Store last agent message for deduplication with final result
                    self._last_agent_message = message_text
                    
                    await self._ws_manager.broadcast(
                        self.session_id,
                        {
                            "type": "agent_message",
                            "agent_id": event.agent_id,
                            "role": role.value if role else "assistant",
                            "content": message_text,
                        },
                    )

            elif isinstance(event, MagenticFinalResultEvent):
                # Final workflow result - skip if identical to last agent message
                final_text = getattr(event.message, "text", "") if event.message else ""
                
                # Only send if different from the last agent message
                if final_text != self._last_agent_message:
                    await self._ws_manager.broadcast(
                        self.session_id,
                        {
                            "type": "final_result",
                            "content": final_text,
                        },
                    )
                else:
                    logger.info("[STREAMING] Skipping duplicate final_result (same as last agent_message)")
                
                # Reset for next request
                self._last_agent_message = None

        except Exception as exc:
            logger.error("[AgentFramework-Magentic] Failed to stream event: %s", exc, exc_info=True)

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

    def _sanitize_final_answer(self, final_answer: Optional[str]) -> Optional[str]:
        if final_answer is None:
            return None

        marker = "FINAL_ANSWER:"
        if marker in final_answer:
            return final_answer.split(marker, maxsplit=1)[-1].strip()

        alternate_markers = ["FINAL ANSWER:", "FINALANSWER:"]
        for alt in alternate_markers:
            if alt in final_answer:
                return final_answer.split(alt, maxsplit=1)[-1].strip()

        logger.warning(
            "[AgentFramework-Magentic] Manager response missing FINAL_ANSWER prefix; returning raw text."
        )
        stripped = final_answer.strip()
        return stripped or None

    def _create_checkpoint_storage(self, checkpoint_state: Dict[str, Any]) -> CheckpointStorage:
        if self._checkpoint_storage_override:
            return self._checkpoint_storage_override

        if self._checkpoint_storage_factory:
            storage = self._checkpoint_storage_factory(checkpoint_state, self.session_id)
            if storage:
                if self._config.get("cache_factory_storage", True):
                    self.state_store["magentic_checkpoint_storage"] = storage
                    self._checkpoint_storage_override = storage
                return storage
            logger.warning(
                "[AgentFramework-Magentic] Provided checkpoint storage factory returned None; falling back to in-memory storage."
            )

        if self._in_memory_checkpoint_storage is None:
            self._in_memory_checkpoint_storage = DictCheckpointStorage(checkpoint_state)
        return self._in_memory_checkpoint_storage

    def _coerce_checkpoint_storage(self, candidate: Any) -> Optional[CheckpointStorage]:
        if candidate is None:
            return None

        required_methods = [
            "save_checkpoint",
            "load_checkpoint",
        ]

        for method_name in required_methods:
            method = getattr(candidate, method_name, None)
            if not callable(method):
                return None

        return cast(CheckpointStorage, candidate)

    def _load_effective_config(self, runtime_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        env_config = self._load_env_config()
        if env_config:
            merged.update(env_config)

        store_config = self.state_store.get("magentic_config")
        if isinstance(store_config, dict):
            merged.update(store_config)

        if runtime_config:
            merged.update(runtime_config)

        return merged

    def _load_env_config(self) -> Dict[str, Any]:
        env_config: Dict[str, Any] = {}

        manager_instructions = os.getenv("MAGENTIC_MANAGER_INSTRUCTIONS")
        if manager_instructions:
            env_config["manager_instructions"] = manager_instructions.strip()

        max_rounds = self._maybe_parse_int(os.getenv("MAGENTIC_MAX_ROUNDS"))
        if max_rounds is not None:
            env_config["max_round_count"] = max_rounds

        max_stalls = self._maybe_parse_int(os.getenv("MAGENTIC_MAX_STALLS"))
        if max_stalls is not None:
            env_config["max_stall_count"] = max_stalls

        max_resets = self._maybe_parse_int(os.getenv("MAGENTIC_MAX_RESETS"))
        if max_resets is not None:
            env_config["max_reset_count"] = max_resets

        log_events = self._maybe_parse_bool(os.getenv("MAGENTIC_LOG_WORKFLOW_EVENTS"))
        if log_events is not None:
            env_config["log_workflow_events"] = log_events

        plan_review = self._maybe_parse_bool(os.getenv("MAGENTIC_ENABLE_PLAN_REVIEW"))
        if plan_review is not None:
            env_config["enable_plan_review"] = plan_review

        mcp_timeout = self._maybe_parse_int(os.getenv("MAGENTIC_MCP_TIMEOUT_SECONDS"))
        if mcp_timeout is not None:
            env_config["mcp_timeout_seconds"] = mcp_timeout

        mcp_request_timeout = self._maybe_parse_int(os.getenv("MAGENTIC_MCP_REQUEST_TIMEOUT_SECONDS"))
        if mcp_request_timeout is not None:
            env_config["mcp_request_timeout_seconds"] = mcp_request_timeout

        mcp_retry_attempts = self._maybe_parse_int(os.getenv("MAGENTIC_MCP_STARTUP_RETRIES"))
        if mcp_retry_attempts is not None:
            env_config["mcp_startup_retries"] = mcp_retry_attempts

        mcp_retry_backoff = os.getenv("MAGENTIC_MCP_RETRY_BACKOFF_SECONDS")
        if mcp_retry_backoff is not None:
            try:
                env_config["mcp_retry_backoff_seconds"] = float(mcp_retry_backoff)
            except ValueError:
                logger.warning(
                    "[AgentFramework-Magentic] Invalid MAGENTIC_MCP_RETRY_BACKOFF_SECONDS value '%s'; expecting float.",
                    mcp_retry_backoff,
                )

        mcp_headers_raw = os.getenv("MAGENTIC_MCP_HEADERS")
        if mcp_headers_raw:
            try:
                parsed_headers = json.loads(mcp_headers_raw)
                if isinstance(parsed_headers, dict):
                    env_config["mcp_headers"] = parsed_headers
            except json.JSONDecodeError:
                logger.warning(
                    "[AgentFramework-Magentic] Failed to parse MAGENTIC_MCP_HEADERS as JSON; ignoring value.",
                    exc_info=True,
                )

        return env_config

    def _maybe_parse_int(self, value: Optional[str]) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            logger.warning(
                "[AgentFramework-Magentic] Expected integer value but received '%s'; ignoring.",
                value,
            )
            return None

    def _maybe_parse_bool(self, value: Optional[str]) -> Optional[bool]:
        if value is None:
            return None

        value_normalised = value.strip().lower()
        if value_normalised in {"1", "true", "yes", "y", "on"}:
            return True
        if value_normalised in {"0", "false", "no", "n", "off"}:
            return False

        logger.warning(
            "[AgentFramework-Magentic] Expected boolean value but received '%s'; ignoring.",
            value,
        )
        return None

    async def _mark_pending_prompt(self, storage: CheckpointStorage, prompt: str) -> None:
        self.state_store[self._pending_prompt_state_key] = prompt
        mark_fn = getattr(storage, "mark_pending_prompt", None)
        if callable(mark_fn):
            try:
                result = mark_fn(prompt)
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(
                    "[AgentFramework-Magentic] Failed to mark pending prompt on checkpoint storage: %s",
                    exc,
                    exc_info=True,
                )

    async def _consume_pending_prompt(self, storage: CheckpointStorage) -> Optional[str]:
        stored_prompt = self.state_store.get(self._pending_prompt_state_key)
        storage_prompt: Optional[str] = None

        consume_fn = getattr(storage, "consume_pending_prompt", None)
        if callable(consume_fn):
            try:
                result = consume_fn()
                storage_prompt = await result if inspect.isawaitable(result) else result
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(
                    "[AgentFramework-Magentic] Failed to consume pending prompt from checkpoint storage: %s",
                    exc,
                    exc_info=True,
                )

        if stored_prompt is not None or storage_prompt is not None:
            self.state_store.pop(self._pending_prompt_state_key, None)

        return storage_prompt or stored_prompt

    async def _reset_checkpoint_progress(self, storage: CheckpointStorage) -> None:
        await self._purge_checkpoint_storage(storage)
        self.state_store.pop(self._pending_prompt_state_key, None)

    async def _purge_checkpoint_storage(self, storage: CheckpointStorage) -> None:
        clear_fn = getattr(storage, "clear_all", None)
        if callable(clear_fn):
            try:
                result = clear_fn()
                if inspect.isawaitable(result):
                    await result
                return
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(
                    "[AgentFramework-Magentic] clear_all on checkpoint storage failed: %s",
                    exc,
                    exc_info=True,
                )

        list_fn = getattr(storage, "list_checkpoint_ids", None)
        delete_fn = getattr(storage, "delete_checkpoint", None)
        if callable(list_fn) and callable(delete_fn):
            try:
                checkpoint_ids = list_fn()
                checkpoint_ids = await checkpoint_ids if inspect.isawaitable(checkpoint_ids) else checkpoint_ids
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(
                    "[AgentFramework-Magentic] Unable to enumerate checkpoints for purge: %s",
                    exc,
                    exc_info=True,
                )
                return

            if checkpoint_ids:
                for checkpoint_id in checkpoint_ids:
                    try:
                        delete_result = delete_fn(checkpoint_id)
                        if inspect.isawaitable(delete_result):
                            await delete_result
                    except Exception as exc:  # pragma: no cover - defensive
                        logger.debug(
                            "[AgentFramework-Magentic] Failed to delete checkpoint %s: %s",
                            checkpoint_id,
                            exc,
                            exc_info=True,
                        )

    async def _get_latest_checkpoint_id(self, storage: CheckpointStorage) -> Optional[str]:
        latest_id_attr = getattr(storage, "latest_checkpoint_id", None)
        latest_id: Optional[str]

        if callable(latest_id_attr):
            try:
                result = latest_id_attr()
                latest_id = await result if inspect.isawaitable(result) else result
            except Exception:
                latest_id = None
        else:
            latest_id = latest_id_attr  # type: ignore[assignment]

        if isinstance(latest_id, str):
            return latest_id

        list_checkpoints_fn = getattr(storage, "list_checkpoints", None)
        if callable(list_checkpoints_fn):
            try:
                checkpoints = list_checkpoints_fn()
                checkpoints = await checkpoints if inspect.isawaitable(checkpoints) else checkpoints
                if checkpoints:
                    checkpoints = sorted(
                        checkpoints,
                        key=lambda cp: (
                            getattr(cp, "timestamp", ""),
                            getattr(cp, "iteration_count", 0),
                        ),
                    )
                    return checkpoints[-1].checkpoint_id
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(
                    "[AgentFramework-Magentic] Unable to determine latest checkpoint via list_checkpoints: %s",
                    exc,
                    exc_info=True,
                )

        list_ids_fn = getattr(storage, "list_checkpoint_ids", None)
        if callable(list_ids_fn):
            try:
                checkpoint_ids = list_ids_fn()
                checkpoint_ids = await checkpoint_ids if inspect.isawaitable(checkpoint_ids) else checkpoint_ids
                if checkpoint_ids:
                    return checkpoint_ids[-1]
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug(
                    "[AgentFramework-Magentic] Unable to determine latest checkpoint via list_checkpoint_ids: %s",
                    exc,
                    exc_info=True,
                )

        return None
