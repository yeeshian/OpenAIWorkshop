# Copyright (c) Microsoft. All rights reserved.

"""
Contoso Fraud Detection & Escalation Workflow

Business Context:
Contoso's automated systems flag suspicious account activity, but certain cases require
a fraud analyst to review before taking action (e.g., locking account, reversing charges).

Flow:
1. Event Trigger: Backend monitoring system sends "Suspicious Activity Alert"
2. AlertRouterExecutor → routes alert to multiple analysis executors:
   - UsagePatternExecutor → checks recent usage against historical baseline (uses MCP tools)
   - LocationAnalysisExecutor → checks geolocation anomalies (uses MCP tools)
   - BillingChargeExecutor → checks for unusual purchases or charges (uses MCP tools)
3. Fan-In to FraudRiskAggregatorExecutor (LLM-based agent):
   - Produces FraudRiskScore and recommended action (lock account, refund charges, ignore)
4. SwitchCaseEdgeRunner:
   - If risk score ≥ threshold → route to RequestInfoExecutor for human fraud analyst review
   - Else → route to AutoClearExecutor
5. RequestInfoExecutor → sends "Fraud Case Review Request" to analyst with full context
6. Workflow pauses — checkpoint saved
7. Analyst decides (approve lock/refund or clear)
8. Workflow resumes:
   - FraudActionExecutor → performs chosen action (e.g., lock account, reverse charges)
9. FinalNotificationExecutor → informs customer and logs audit trail

Demonstrates:
- Event-driven workflow triggered by backend system
- Fan-out pattern to multiple specialist agents with MCP tools
- Fan-in aggregation to produce single risk assessment
- LLM-based risk scoring
- Human-in-the-loop for high-risk cases
- Checkpointing for workflow pause/resume
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from dotenv import load_dotenv

load_dotenv()

from agent_framework import (
    Case,
    ChatAgent,
    Default,
    Executor,
    ExecutorCompletedEvent,
    ExecutorInvokedEvent,
    FileCheckpointStorage,
    MCPStreamableHTTPTool,
    RequestInfoEvent,
    RequestInfoExecutor,
    RequestInfoMessage,
    RequestResponse,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowOutputEvent,
    WorkflowStatusEvent,
    handler,
)
from agent_framework.azure import AzureOpenAIChatClient
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(force=True, level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# ============================================================================
# Message Models
# NOTE: Using dataclasses instead of Pydantic for checkpoint compatibility
# The framework's checkpoint serialization doesn't support Pydantic v2's
# model_dump()/model_dump_json() methods yet (it looks for to_dict/to_json).
# ============================================================================


@dataclass
class SuspiciousActivityAlert:
    """Initial alert from monitoring system."""

    alert_id: str
    customer_id: int
    alert_type: str  # "multi_country_login", "data_spike", "unusual_charges"
    description: str
    timestamp: str
    severity: str  # "low", "medium", "high"


@dataclass
class UsageAnalysisResult:
    """Result from usage pattern analysis."""

    alert_id: str
    customer_id: int
    analysis_type: str = "usage_pattern"
    findings: str = ""
    risk_indicators: list[str] = field(default_factory=list)
    risk_score: float = 0.5  # 0-1 risk score


@dataclass
class LocationAnalysisResult:
    """Result from location analysis."""

    alert_id: str
    customer_id: int
    analysis_type: str = "location"
    findings: str = ""
    risk_indicators: list[str] = field(default_factory=list)
    risk_score: float = 0.5  # 0-1 risk score


@dataclass
class BillingAnalysisResult:
    """Result from billing charge analysis."""

    alert_id: str
    customer_id: int
    analysis_type: str = "billing"
    findings: str = ""
    risk_indicators: list[str] = field(default_factory=list)
    risk_score: float = 0.5  # 0-1 risk score


@dataclass
class FraudRiskAssessment:
    """Aggregated fraud risk assessment."""

    alert_id: str
    customer_id: int
    overall_risk_score: float  # 0-1 risk score
    risk_level: str  # "low", "medium", "high", "critical"
    recommended_action: str  # "clear", "lock_account", "refund_charges", "both"
    reasoning: str
    analysis_summaries: list[str] = field(default_factory=list)


@dataclass
class AnalystReviewRequest(RequestInfoMessage):
    """Request for analyst review sent to RequestInfoExecutor."""

    assessment: FraudRiskAssessment | None = None
    prompt: str = ""


@dataclass
class AnalystDecision:
    """Decision from human fraud analyst."""

    alert_id: str
    customer_id: int
    approved_action: str  # "clear", "lock_account", "refund_charges", "both"
    analyst_notes: str
    analyst_id: str


@dataclass
class ActionResult:
    """Result of fraud action execution."""

    alert_id: str
    customer_id: int
    action_taken: str
    success: bool
    details: str
    timestamp: str


@dataclass
class FinalNotification:
    """Final notification to customer and audit log."""

    alert_id: str
    customer_id: int
    resolution: str
    customer_notified: bool
    audit_logged: bool


# ============================================================================
# Executors
# ============================================================================


class AlertRouterExecutor(Executor):
    """Routes suspicious activity alerts to multiple analysis executors (fan-out)."""

    def __init__(self, id: str = "alert_router") -> None:
        super().__init__(id=id)

    @handler
    async def handle_alert(
        self,
        alert: SuspiciousActivityAlert,
        ctx: WorkflowContext[SuspiciousActivityAlert],
    ) -> None:
        try:
            logger.info(f"[AlertRouter] Processing alert {alert.alert_id} for customer {alert.customer_id}")
            logger.info(f"[AlertRouter] Alert type: {alert.alert_type}, Severity: {alert.severity}")
            
            print(f"\n[DEBUG] AlertRouter: Fan-out alert to all connected analysts")
            print(f"[DEBUG] Alert data: {alert}")
            print(f"[DEBUG] Context type: {type(ctx)}")

            # Fan-out: Send the same alert to all three analysis executors
            # The add_fan_out_edges in the workflow builder will automatically route this
            # message to all connected downstream executors
            result = await ctx.send_message(alert)
            print(f"[DEBUG] send_message result: {result}")

            logger.info(f"[AlertRouter] Alert {alert.alert_id} sent for fan-out routing")
            print(f"[DEBUG] AlertRouter: Message sent (fan-out edges will handle distribution)")
        except Exception as e:
            print(f"[ERROR] Exception in AlertRouter: {e}")
            import traceback
            traceback.print_exc()
            raise


class UsagePatternExecutor(Executor):
    """Analyzes usage patterns using MCP tools."""

    def __init__(self, mcp_tool: MCPStreamableHTTPTool, chat_client: AzureOpenAIChatClient, model: str, id: str = "usage_pattern_executor") -> None:

        super().__init__(id=id)
        self._agent: ChatAgent | None = None
        self._mcp_tool = mcp_tool
        self._chat_client = chat_client
        self._model = model
        self._allowed_tools = {
            "get_customer_detail",
            "get_subscription_detail",
            "get_data_usage",
            "search_knowledge_base",
        }

    async def _ensure_agent(self) -> None:
        if self._agent is not None:
            return

        logger.info("[UsagePatternExecutor] Initializing agent...")
        filtered_functions = [func for func in self._mcp_tool.functions if func.name in self._allowed_tools]
        self._agent = ChatAgent(
            name="UsagePatternAnalyst",
            chat_client=self._chat_client,
            model=self._model,
            instructions=(
                "You are a usage pattern fraud analyst for Contoso. "
                "Analyze customer data usage patterns to detect anomalies that may indicate fraud. "
                "Use the provided tools to retrieve customer details, subscription info, and data usage history. "
                "Look for: sudden spikes in data usage, usage patterns inconsistent with subscription tier, "
                "usage from unusual times/locations. "
                "Provide a risk score (0.0-1.0) and specific risk indicators."
            ),
            tools=filtered_functions,
        )
        await self._agent.__aenter__()
        logger.info("[UsagePatternExecutor] Agent initialized with filtered MCP tools")

    @handler
    async def handle_alert(
        self, alert: SuspiciousActivityAlert, ctx: WorkflowContext[UsageAnalysisResult]
    ) -> None:
        logger.info(f"[UsagePatternExecutor] Analyzing alert {alert.alert_id}")

        await self._ensure_agent()
        assert self._agent is not None

        # Create analysis prompt
        prompt = f"""Analyze potential fraud for customer ID {alert.customer_id}.

Alert Details:
- Type: {alert.alert_type}
- Description: {alert.description}
- Severity: {alert.severity}

Tasks:
1. Retrieve customer details and subscription information
2. Get recent data usage history (last 30 days if available)
3. Identify any unusual patterns or anomalies
4. Provide risk indicators and a risk score (0.0-1.0)

Respond in this format:
FINDINGS: [Your detailed findings]
RISK_INDICATORS: [List specific red flags]
RISK_SCORE: [0.0-1.0]
"""

        # Run agent to analyze
        thread = self._agent.get_new_thread()
        response_parts = []
        async for chunk in self._agent.run_stream(prompt, thread=thread):
            if hasattr(chunk, "text") and chunk.text:
                response_parts.append(chunk.text)

        response = "".join(response_parts)
        logger.info(f"[UsagePatternExecutor] Analysis complete: {response[:200]}...")

        # Parse response (simple parsing - in production use structured output)
        risk_score = 0.5  # Default
        risk_indicators = []
        findings = response

        if "RISK_SCORE:" in response:
            try:
                score_line = [line for line in response.split("\n") if "RISK_SCORE:" in line][0]
                risk_score = float(score_line.split("RISK_SCORE:")[1].strip())
            except (IndexError, ValueError):
                pass

        if "RISK_INDICATORS:" in response:
            try:
                indicators_line = [line for line in response.split("\n") if "RISK_INDICATORS:" in line][0]
                indicators_text = indicators_line.split("RISK_INDICATORS:")[1].strip()
                risk_indicators = [ind.strip() for ind in indicators_text.split(",")]
            except IndexError:
                pass

        # Send result to aggregator
        result = UsageAnalysisResult(
            alert_id=alert.alert_id,
            customer_id=alert.customer_id,
            findings=findings,
            risk_indicators=risk_indicators,
            risk_score=risk_score,
        )

        await ctx.send_message(result)
        logger.info(f"[UsagePatternExecutor] Sent analysis result (risk_score={risk_score})")


class LocationAnalysisExecutor(Executor):
    """Analyzes location anomalies using MCP tools."""

    def __init__(self, mcp_tool: MCPStreamableHTTPTool, chat_client: AzureOpenAIChatClient, model: str, id: str = "location_analysis_executor") -> None:
        super().__init__(id=id)
        print("[LocationAnalysisExecutor] Initializing...")
        self._agent: ChatAgent | None = None
        self._mcp_tool = mcp_tool
        self._chat_client = chat_client
        self._model = model
        self._allowed_tools = {
            "get_customer_detail",
            "get_security_logs",
            "search_knowledge_base",
        }

    async def _ensure_agent(self) -> None:
        if self._agent is not None:
            return

        logger.info("[LocationAnalysisExecutor] Initializing agent...")
        filtered_functions = [func for func in self._mcp_tool.functions if func.name in self._allowed_tools]
        self._agent = ChatAgent(
            name="LocationAnalyst",
            chat_client=self._chat_client,
            model=self._model,
            instructions=(
                "You are a geolocation fraud analyst for Contoso. "
                "Analyze customer security logs and authentication patterns to detect location-based fraud. "
                "Use the provided tools to retrieve customer details and security logs. "
                "Look for: logins from multiple countries in short timeframes, impossible travel scenarios, "
                "access from high-risk regions, VPN/proxy usage patterns. "
                "Provide a risk score (0.0-1.0) and specific risk indicators."
            ),
            tools=filtered_functions,
        )
        await self._agent.__aenter__()
        logger.info("[LocationAnalysisExecutor] Agent initialized")

    @handler
    async def handle_alert(
        self, alert: SuspiciousActivityAlert, ctx: WorkflowContext[LocationAnalysisResult]
    ) -> None:
        logger.info(f"[LocationAnalysisExecutor] Analyzing alert {alert.alert_id}")

        await self._ensure_agent()
        assert self._agent is not None

        prompt = f"""Analyze location-based fraud indicators for customer ID {alert.customer_id}.

Alert Details:
- Type: {alert.alert_type}
- Description: {alert.description}

Tasks:
1. Retrieve customer details
2. Get security logs (authentication events, login locations)
3. Identify suspicious location patterns
4. Provide risk indicators and a risk score (0.0-1.0)

Respond in this format:
FINDINGS: [Your detailed findings]
RISK_INDICATORS: [List specific red flags]
RISK_SCORE: [0.0-1.0]
"""

        thread = self._agent.get_new_thread()
        response_parts = []
        async for chunk in self._agent.run_stream(prompt, thread=thread):
            if hasattr(chunk, "text") and chunk.text:
                response_parts.append(chunk.text)

        response = "".join(response_parts)
        logger.info(f"[LocationAnalysisExecutor] Analysis complete")

        # Parse response
        risk_score = 0.5
        risk_indicators = []
        findings = response

        if "RISK_SCORE:" in response:
            try:
                score_line = [line for line in response.split("\n") if "RISK_SCORE:" in line][0]
                risk_score = float(score_line.split("RISK_SCORE:")[1].strip())
            except (IndexError, ValueError):
                pass

        if "RISK_INDICATORS:" in response:
            try:
                indicators_line = [line for line in response.split("\n") if "RISK_INDICATORS:" in line][0]
                indicators_text = indicators_line.split("RISK_INDICATORS:")[1].strip()
                risk_indicators = [ind.strip() for ind in indicators_text.split(",")]
            except IndexError:
                pass

        result = LocationAnalysisResult(
            alert_id=alert.alert_id,
            customer_id=alert.customer_id,
            findings=findings,
            risk_indicators=risk_indicators,
            risk_score=risk_score,
        )

        await ctx.send_message(result)
        logger.info(f"[LocationAnalysisExecutor] Sent analysis result (risk_score={risk_score})")


class BillingChargeExecutor(Executor):
    """Analyzes billing and charge anomalies using MCP tools."""

    def __init__(self, mcp_tool: MCPStreamableHTTPTool, chat_client: AzureOpenAIChatClient, model: str, id: str = "billing_charge_executor") -> None:
        super().__init__(id=id)
        self._agent: ChatAgent | None = None
        self._mcp_tool = mcp_tool
        self._chat_client = chat_client
        self._model = model
        self._allowed_tools = {
            "get_customer_detail",
            "get_billing_summary",
            "get_subscription_detail",
            "get_customer_orders",
            "search_knowledge_base",
        }

    async def _ensure_agent(self) -> None:
        if self._agent is not None:
            return

        logger.info("[BillingChargeExecutor] Initializing agent...")
        filtered_functions = [func for func in self._mcp_tool.functions if func.name in self._allowed_tools]
        self._agent = ChatAgent(
            name="BillingAnalyst",
            chat_client=self._chat_client,
            model=self._model,
            instructions=(
                "You are a billing fraud analyst for Contoso. "
                "Analyze customer billing patterns and charges to detect fraudulent activity. "
                "Use the provided tools to retrieve customer details, billing summaries, and order history. "
                "Look for: unusual charge amounts, unexpected subscription changes, "
                "orders inconsistent with customer profile, rapid succession of charges. "
                "Provide a risk score (0.0-1.0) and specific risk indicators."
            ),
            tools=filtered_functions,
        )
        await self._agent.__aenter__()
        logger.info("[BillingChargeExecutor] Agent initialized")

    @handler
    async def handle_alert(
        self, alert: SuspiciousActivityAlert, ctx: WorkflowContext[BillingAnalysisResult]
    ) -> None:
        logger.info(f"[BillingChargeExecutor] Analyzing alert {alert.alert_id}")

        await self._ensure_agent()
        assert self._agent is not None

        prompt = f"""Analyze billing fraud indicators for customer ID {alert.customer_id}.

Alert Details:
- Type: {alert.alert_type}
- Description: {alert.description}

Tasks:
1. Retrieve customer details and subscription information
2. Get billing summary and recent orders
3. Identify unusual billing patterns or charges
4. Provide risk indicators and a risk score (0.0-1.0)

Respond in this format:
FINDINGS: [Your detailed findings]
RISK_INDICATORS: [List specific red flags]
RISK_SCORE: [0.0-1.0]
"""

        thread = self._agent.get_new_thread()
        response_parts = []
        async for chunk in self._agent.run_stream(prompt, thread=thread):
            if hasattr(chunk, "text") and chunk.text:
                response_parts.append(chunk.text)

        response = "".join(response_parts)
        logger.info(f"[BillingChargeExecutor] Analysis complete")

        # Parse response
        risk_score = 0.5
        risk_indicators = []
        findings = response

        if "RISK_SCORE:" in response:
            try:
                score_line = [line for line in response.split("\n") if "RISK_SCORE:" in line][0]
                risk_score = float(score_line.split("RISK_SCORE:")[1].strip())
            except (IndexError, ValueError):
                pass

        if "RISK_INDICATORS:" in response:
            try:
                indicators_line = [line for line in response.split("\n") if "RISK_INDICATORS:" in line][0]
                indicators_text = indicators_line.split("RISK_INDICATORS:")[1].strip()
                risk_indicators = [ind.strip() for ind in indicators_text.split(",")]
            except IndexError:
                pass

        result = BillingAnalysisResult(
            alert_id=alert.alert_id,
            customer_id=alert.customer_id,
            findings=findings,
            risk_indicators=risk_indicators,
            risk_score=risk_score,
        )

        await ctx.send_message(result)
        logger.info(f"[BillingChargeExecutor] Sent analysis result (risk_score={risk_score})")


class FraudRiskAggregatorExecutor(Executor):
    """
    LLM-based agent that aggregates analysis results and produces final fraud risk assessment.
    This is a fan-in executor that waits for all three analysis results.
    """

    def __init__(self, chat_client: AzureOpenAIChatClient, model: str, id: str = "fraud_risk_aggregator") -> None:
        super().__init__(id=id)
        self._agent: ChatAgent | None = None
        self._chat_client = chat_client
        self._model = model
    async def _ensure_agent(self) -> None:
        if self._agent is not None:
            return

        logger.info("[FraudRiskAggregator] Initializing agent...")
        self._agent = ChatAgent(
            name="FraudRiskAggregator",
            chat_client=self._chat_client,
            model=self._model,
            instructions=(
                "You are the lead fraud risk aggregator for Contoso. "
                "You receive analysis results from three specialist agents: "
                "usage pattern analyst, location analyst, and billing analyst. "
                "Your job is to synthesize their findings into a single fraud risk assessment. "
                "Calculate an overall risk score (0.0-1.0) based on the three input scores. "
                "Determine risk level (low, medium, high, critical) and recommend action: "
                "- clear: No fraud detected, close alert "
                "- lock_account: Lock customer account to prevent further activity "
                "- refund_charges: Reverse fraudulent charges "
                "- both: Lock account AND refund charges "
                "Provide clear reasoning for your decision."
            ),
        )
        await self._agent.__aenter__()
        logger.info("[FraudRiskAggregator] Agent initialized")

    @handler
    async def handle_analysis_results(
        self,
        results: list[UsageAnalysisResult | LocationAnalysisResult | BillingAnalysisResult],
        ctx: WorkflowContext[FraudRiskAssessment],
    ) -> None:
        logger.info(f"[FraudRiskAggregator] Aggregating {len(results)} analysis results")

        await self._ensure_agent()
        assert self._agent is not None

        # Build comprehensive prompt with all analysis results
        alert_id = results[0].alert_id
        customer_id = results[0].customer_id

        summaries = []
        for result in results:
            summary = f"""
Analysis Type: {result.analysis_type}
Risk Score: {result.risk_score}
Risk Indicators: {', '.join(result.risk_indicators) if result.risk_indicators else 'None'}
Findings: {result.findings}
"""
            summaries.append(summary)

        prompt = f"""Aggregate fraud risk assessment for Alert ID: {alert_id}, Customer ID: {customer_id}

You have received analysis results from three specialists:

{chr(10).join(summaries)}

Tasks:
1. Calculate an overall risk score (weighted average or your best judgment)
2. Determine risk level: low (<0.3), medium (0.3-0.6), high (0.6-0.8), critical (>0.8)
3. Recommend action: clear, lock_account, refund_charges, or both
4. Provide reasoning that references specific findings from the analysts

Respond in this format:
OVERALL_RISK_SCORE: [0.0-1.0]
RISK_LEVEL: [low/medium/high/critical]
RECOMMENDED_ACTION: [clear/lock_account/refund_charges/both]
REASONING: [Your comprehensive reasoning]
"""

        thread = self._agent.get_new_thread()
        response_parts = []
        async for chunk in self._agent.run_stream(prompt, thread=thread):
            if hasattr(chunk, "text") and chunk.text:
                response_parts.append(chunk.text)

        response = "".join(response_parts)
        logger.info(f"[FraudRiskAggregator] Assessment complete")

        # Parse response
        overall_risk_score = 0.5
        risk_level = "medium"
        recommended_action = "clear"
        reasoning = response

        try:
            if "OVERALL_RISK_SCORE:" in response:
                score_line = [line for line in response.split("\n") if "OVERALL_RISK_SCORE:" in line][0]
                overall_risk_score = float(score_line.split("OVERALL_RISK_SCORE:")[1].strip())

            if "RISK_LEVEL:" in response:
                level_line = [line for line in response.split("\n") if "RISK_LEVEL:" in line][0]
                risk_level = level_line.split("RISK_LEVEL:")[1].strip().lower()

            if "RECOMMENDED_ACTION:" in response:
                action_line = [line for line in response.split("\n") if "RECOMMENDED_ACTION:" in line][0]
                recommended_action = action_line.split("RECOMMENDED_ACTION:")[1].strip().lower()
        except (IndexError, ValueError) as e:
            logger.warning(f"[FraudRiskAggregator] Error parsing response: {e}")

        # Create assessment
        assessment = FraudRiskAssessment(
            alert_id=alert_id,
            customer_id=customer_id,
            overall_risk_score=overall_risk_score,
            risk_level=risk_level,
            recommended_action=recommended_action,
            reasoning=reasoning,
            analysis_summaries=[f"{r.analysis_type}: {r.risk_score}" for r in results],
        )

        await ctx.send_message(assessment)
        logger.info(
            f"[FraudRiskAggregator] Sent assessment (risk_score={overall_risk_score}, action={recommended_action})"
        )


class ReviewGatewayExecutor(Executor):
    """Gateway that routes high-risk assessments to RequestInfoExecutor for human review."""

    def __init__(self, analyst_review_id: str, fraud_action_id: str, id: str = "review_gateway") -> None:
        super().__init__(id=id)
        self._analyst_review_id = analyst_review_id
        self._fraud_action_id = fraud_action_id

    @handler
    async def handle_assessment(
        self, assessment: FraudRiskAssessment, ctx: WorkflowContext[AnalystReviewRequest]
    ) -> None:
        logger.info(f"[ReviewGateway] Routing high-risk assessment {assessment.alert_id} to analyst")

        # Create analyst review request
        request = AnalystReviewRequest(
            assessment=assessment,
            prompt=f"Review fraud case for alert {assessment.alert_id}. Risk score: {assessment.overall_risk_score:.2f}. Recommended action: {assessment.recommended_action}",
        )

        # Send to RequestInfoExecutor
        await ctx.send_message(request, target_id=self._analyst_review_id)

    @handler
    async def handle_analyst_response(
        self, response: RequestResponse[AnalystReviewRequest, AnalystDecision], ctx: WorkflowContext[AnalystDecision]
    ) -> None:
        logger.info(f"[ReviewGateway] Received analyst decision")

        assessment = response.original_request.assessment if response.original_request else None
        decision = response.data

        if assessment and getattr(decision, "customer_id", None) in (None, 0):
            # Now using dataclasses, use replace() to update fields
            from dataclasses import replace
            decision = replace(decision, customer_id=assessment.customer_id)

        # Forward the analyst decision to fraud action executor
        await ctx.send_message(decision, target_id=self._fraud_action_id)


class AutoClearExecutor(Executor):
    """Automatically clears low-risk alerts."""

    def __init__(self, id: str = "auto_clear_executor") -> None:
        super().__init__(id=id)

    @handler
    async def handle_assessment(
        self, assessment: FraudRiskAssessment, ctx: WorkflowContext[ActionResult]
    ) -> None:
        logger.info(f"[AutoClear] Auto-clearing alert {assessment.alert_id} (low risk)")

        result = ActionResult(
            alert_id=assessment.alert_id,
            customer_id=assessment.customer_id,
            action_taken="cleared",
            success=True,
            details=f"Alert auto-cleared. Risk score: {assessment.overall_risk_score}",
            timestamp=datetime.now().isoformat(),
        )

        await ctx.send_message(result)
        logger.info(f"[AutoClear] Alert {assessment.alert_id} cleared")


class FraudActionExecutor(Executor):
    """Executes fraud mitigation actions based on analyst decision."""

    def __init__(self, id: str = "fraud_action_executor") -> None:
        super().__init__(id=id)

    @handler
    async def handle_decision(self, decision: AnalystDecision, ctx: WorkflowContext[ActionResult]) -> None:
        logger.info(f"[FraudAction] Executing action: {decision.approved_action} for alert {decision.alert_id}")

        # Add delay to make workflow progression visible in UI
        await asyncio.sleep(2)

        # Simulate action execution
        action_details = []
        if "lock" in decision.approved_action:
            action_details.append("Account locked")
        if "refund" in decision.approved_action:
            action_details.append("Charges reversed")
        if decision.approved_action == "clear":
            action_details.append("Alert cleared, no action taken")

        result = ActionResult(
            alert_id=decision.alert_id,
            customer_id=decision.customer_id,
            action_taken=decision.approved_action,
            success=True,
            details=f"{', '.join(action_details)}. Analyst: {decision.analyst_id}. Notes: {decision.analyst_notes}",
            timestamp=datetime.now().isoformat(),
        )

        await ctx.send_message(result)
        logger.info(f"[FraudAction] Action executed for alert {decision.alert_id}")


class FinalNotificationExecutor(Executor):
    """Sends final notification and logs audit trail."""

    def __init__(self, id: str = "final_notification_executor") -> None:
        super().__init__(id=id)

    @handler
    async def handle_result(
        self, result: ActionResult, ctx: WorkflowContext[None, FinalNotification]
    ) -> None:
        logger.info(f"[FinalNotification] Processing result for alert {result.alert_id}")

        # Add delay to make workflow progression visible in UI
        await asyncio.sleep(2)

        # Simulate notification and audit logging
        notification = FinalNotification(
            alert_id=result.alert_id,
            customer_id=result.customer_id,
            resolution=result.details,
            customer_notified=True,
            audit_logged=True,
        )

        # Yield as workflow output
        await ctx.yield_output(notification)

        logger.info(f"[FinalNotification] Alert {result.alert_id} completed and logged")


# ============================================================================
# Workflow Builder
# ============================================================================


async def create_fraud_detection_workflow(
    mcp_tool: MCPStreamableHTTPTool,
    chat_client: AzureOpenAIChatClient,
    model: str,
    checkpoint_storage: Any | None = None,
) -> Any:
    """
    Build the fraud detection workflow.

    Topology:
    AlertRouter → [UsagePattern, Location, Billing] → FraudRiskAggregator
                                                            ↓
                                            (Switch based on risk score)
                                                            ↓
                                    ┌───────────────────────┴──────────────────────┐
                                    ↓                                              ↓
                            (High Risk)                                     (Low Risk)
                        RequestInfoExecutor                              AutoClearExecutor
                                    ↓                                              ↓
                           (Analyst Decision)                                      ↓
                        FraudActionExecutor ────────────────────→ FinalNotificationExecutor
    """

    # Create executors
    alert_router = AlertRouterExecutor()
    usage_executor = UsagePatternExecutor(mcp_tool, chat_client, model)
    location_executor = LocationAnalysisExecutor(mcp_tool, chat_client, model)
    billing_executor = BillingChargeExecutor(mcp_tool, chat_client, model)
    aggregator = FraudRiskAggregatorExecutor(chat_client, model)
    auto_clear = AutoClearExecutor()
    fraud_action = FraudActionExecutor()
    final_notification = FinalNotificationExecutor()

    # Create human-in-the-loop executors
    analyst_review = RequestInfoExecutor(id="analyst_review")
    review_gateway = ReviewGatewayExecutor(
        analyst_review_id=analyst_review.id,
        fraud_action_id=fraud_action.id,
    )

    # Build workflow
    builder = WorkflowBuilder()

    # Fan-out edges: AlertRouter → 3 analysts (parallel branches)
    builder.add_fan_out_edges(alert_router, [usage_executor, location_executor, billing_executor])

    # Fan-in edge: 3 analysts → Aggregator (waits for all 3)
    builder.add_fan_in_edges([usage_executor, location_executor, billing_executor], aggregator)

    # # Switch/case edges: Aggregator → High risk OR Low risk
    builder.add_switch_case_edge_group(
        aggregator,
        [
            # High risk → Review Gateway → Analyst review
            Case(condition=lambda assessment: assessment.overall_risk_score >= 0.6, target=review_gateway),
            # Low risk → Auto clear
            Default(target=auto_clear),
        ],
    )

    # # Review gateway routes to analyst review and back, then to fraud action
    builder.add_edge(review_gateway, analyst_review)
    builder.add_edge(analyst_review, review_gateway)
    builder.add_edge(review_gateway, fraud_action)

    # # Both paths → Final notification
    builder.add_edge(auto_clear, final_notification)
    builder.add_edge(fraud_action, final_notification)

    # Set start executor
    builder.set_start_executor(alert_router)

    if checkpoint_storage:
        builder = builder.with_checkpointing(checkpoint_storage=checkpoint_storage)

    workflow = builder.build()

    print("\n" + "=" * 80)
    print(f"[WORKFLOW STRUCTURE]")
    print(f"Total executors: {len(workflow.executors)}")
    print(f"Executor IDs: {list(workflow.executors.keys())}")
    print("=" * 80 + "\n")
    
    logger.info("[Workflow] Fraud detection workflow built successfully")
    
    return workflow


# ============================================================================
# Main Console Application
# ============================================================================


async def main() -> None:
    """Main console application."""
    # Load environment variables from .env file

    logger.info("=" * 80)
    logger.info("Contoso Fraud Detection & Escalation Workflow")
    logger.info("=" * 80)

    # Load configuration
    azure_openai_key = os.getenv("AZURE_OPENAI_API_KEY")
    azure_deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
    azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    mcp_server_uri = os.getenv("MCP_SERVER_URI", "http://localhost:8000/mcp")
    if not all([azure_openai_key, azure_deployment, azure_endpoint]):
        logger.error("Missing required environment variables. Please set:")
        logger.error("  AZURE_OPENAI_API_KEY")
        logger.error("  AZURE_OPENAI_CHAT_DEPLOYMENT")
        logger.error("  AZURE_OPENAI_ENDPOINT")
        logger.error("  MCP_SERVER_URI (optional, defaults to http://localhost:8000)")
        return

    # Create Azure OpenAI client
    chat_client = AzureOpenAIChatClient(
        api_key=azure_openai_key,
        deployment_name=azure_deployment,
        endpoint=azure_endpoint,
    )

    # Create MCP tool
    logger.info(f"[Setup] Connecting to MCP server at {mcp_server_uri}")
    mcp_tool = MCPStreamableHTTPTool(
        name="contoso_mcp",
        url=mcp_server_uri,
        headers={"Content-Type": "application/json"},
        timeout=30,
        request_timeout=30,
    )

    # Connect to MCP server
    await mcp_tool.__aenter__()
    logger.info(f"[Setup] Connected to MCP server, loaded {len(mcp_tool.functions)} tools")

    # Create checkpoint storage
    # checkpoint_storage=None
    checkpoint_storage = FileCheckpointStorage("./checkpoints/fraud_detection")

    # Build workflow
    workflow = await create_fraud_detection_workflow(
        mcp_tool=mcp_tool,
        chat_client=chat_client,
        model=azure_deployment,
        checkpoint_storage=checkpoint_storage,
    )

    # Sample suspicious activity alerts
    alerts = [
        SuspiciousActivityAlert(
            alert_id="ALERT-001",
            customer_id=1,
            alert_type="multi_country_login",
            description="Login attempts from USA and Russia within 2 hours",
            timestamp=datetime.now().isoformat(),
            severity="high",
        ),
        SuspiciousActivityAlert(
            alert_id="ALERT-002",
            customer_id=2,
            alert_type="data_spike",
            description="Data usage increased by 500% in last 24 hours",
            timestamp=datetime.now().isoformat(),
            severity="medium",
        ),
        SuspiciousActivityAlert(
            alert_id="ALERT-003",
            customer_id=3,
            alert_type="unusual_charges",
            description="Three large purchases totaling $5,000 in 10 minutes",
            timestamp=datetime.now().isoformat(),
            severity="high",
        ),
    ]

    # Process first alert
    logger.info("\n" + "=" * 80)
    logger.info(f"Processing Alert: {alerts[0].alert_id}")
    logger.info("=" * 80)

    try:
        # Run workflow with streaming
        logger.info("[Workflow] Starting fraud detection workflow...")

        event_count = 0
        final_output: FinalNotification | None = None
        last_checkpoint_id: str | None = None

        async def consume_stream(stream: Any) -> tuple[list[RequestInfoEvent], FinalNotification | None, str | None]:
            nonlocal event_count
            pending_requests: list[RequestInfoEvent] = []
            output: FinalNotification | None = None
            checkpoint_id: str | None = None

            async for event in stream:
                event_count += 1
                logger.info(f"[Workflow] Event #{event_count}: {event.__class__.__name__}")
                print(f"\n[Event Type: {event.__class__.__name__}]")

                if isinstance(event, ExecutorInvokedEvent):
                    print(f"  ▶ Executor '{event.executor_id}' invoked")
                    if getattr(event, "message", None):
                        print(f"  📥 Input: {event.message}")
                elif isinstance(event, ExecutorCompletedEvent):
                    print(f"  ✓ Executor '{event.executor_id}' completed")
                    if getattr(event, "data", None):
                        print("  📤 Data:")
                        if isinstance(event.data, dict):
                            for key, value in event.data.items():
                                print(f"     • {key}: {value}")
                        elif hasattr(event.data, "__dict__"):
                            for key, value in event.data.__dict__.items():
                                if not key.startswith("_"):
                                    print(f"     • {key}: {value}")
                        else:
                            print(f"     {event.data}")
                elif isinstance(event, RequestInfoEvent) and isinstance(event.data, AnalystReviewRequest):
                    pending_requests.append(event)
                    logger.info("\n" + "=" * 80)
                    logger.info("ANALYST REVIEW REQUIRED")
                    logger.info("=" * 80)
                    request = event.data
                    logger.info(f"Request ID: {event.request_id}")
                    risk_level = request.assessment.risk_level if request.assessment else "N/A"
                    logger.info(f"Assessment Risk Level: {risk_level}")
                    print("  ⚠ Analyst review required")
                    if request.assessment:
                        print(
                            f"     • Alert: {request.assessment.alert_id} | Risk Score: {request.assessment.overall_risk_score:.2f}"
                        )
                        print(f"     • Recommended Action: {request.assessment.recommended_action}")
                    if request.prompt:
                        print(f"     • Prompt: {request.prompt}")
                    
                    # Capture the checkpoint ID from the workflow context
                    if hasattr(workflow, '_runner_context') and hasattr(workflow._runner_context, '_last_checkpoint_id'):
                        checkpoint_id = workflow._runner_context._last_checkpoint_id
                elif isinstance(event, WorkflowOutputEvent):
                    if isinstance(event.data, FinalNotification):
                        output = event.data
                    print(f"\n{'=' * 80}")
                    print("  🎯 WORKFLOW COMPLETED")
                    print(f"{'=' * 80}")
                    if output:
                        print("  Final Output:")
                        if hasattr(output, "__dict__"):
                            for key, value in output.__dict__.items():
                                if not key.startswith("_"):
                                    print(f"     • {key}: {value}")
                        else:
                            print(f"     {output}")
                elif isinstance(event, WorkflowStatusEvent):
                    print(f"  ℹ Status: {event.state.name}")

                logger.info(f"[Event] {event}")

            return pending_requests, output, checkpoint_id

        pending_requests, final_output, last_checkpoint_id = await consume_stream(workflow.run_stream(alerts[0]))

        while final_output is None and pending_requests:
            logger.info("\n" + "=" * 80)
            logger.info("CHECKPOINT SAVED - Workflow paused for analyst input")
            logger.info("=" * 80)
            
            if last_checkpoint_id:
                logger.info(f"Checkpoint ID: {last_checkpoint_id}")
            
            # Collect analyst decisions from command line
            responses: dict[str, AnalystDecision] = {}
            for request_event in pending_requests:
                assessment = request_event.data.assessment if request_event.data else None
                alert_id = assessment.alert_id if assessment else alerts[0].alert_id
                customer_id = assessment.customer_id if assessment else alerts[0].customer_id
                
                print("\n" + "=" * 80)
                print(f"ANALYST DECISION REQUIRED")
                print("=" * 80)
                print(f"Request ID: {request_event.request_id}")
                if assessment:
                    print(f"Alert ID: {assessment.alert_id}")
                    print(f"Customer ID: {assessment.customer_id}")
                    print(f"Risk Score: {assessment.overall_risk_score:.2f}")
                    print(f"Risk Level: {assessment.risk_level}")
                    print(f"Recommended Action: {assessment.recommended_action}")
                    print(f"\nReasoning:\n{assessment.reasoning[:500]}...")
                
                print("\n" + "-" * 80)
                print("Available actions:")
                print("  1. clear - No fraud detected, close alert")
                print("  2. lock_account - Lock customer account")
                print("  3. refund_charges - Reverse fraudulent charges")
                print("  4. both - Lock account AND refund charges")
                print("-" * 80)
                
                # Get analyst decision from command line
                while True:
                    action_choice = input("\nEnter action (1-4): ").strip()
                    action_map = {
                        "1": "clear",
                        "2": "lock_account",
                        "3": "refund_charges",
                        "4": "both"
                    }
                    if action_choice in action_map:
                        approved_action = action_map[action_choice]
                        break
                    print("Invalid choice. Please enter 1, 2, 3, or 4.")
                
                analyst_notes = input("Enter analyst notes: ").strip()
                if not analyst_notes:
                    analyst_notes = f"Analyst decision: {approved_action}"
                
                analyst_id = input("Enter analyst ID (default: analyst_cli): ").strip()
                if not analyst_id:
                    analyst_id = "analyst_cli"
                
                decision = AnalystDecision(
                    alert_id=alert_id,
                    customer_id=customer_id,
                    approved_action=approved_action,
                    analyst_notes=analyst_notes,
                    analyst_id=analyst_id,
                )
                responses[request_event.request_id] = decision
                logger.info(f"[Analyst] Decision for {request_event.request_id}: {decision.approved_action}")
            
            # Resume workflow with analyst responses
            logger.info("\n" + "=" * 80)
            logger.info("RESUMING WORKFLOW with analyst decisions")
            logger.info("=" * 80)
            
            pending_requests, final_output, last_checkpoint_id = await consume_stream(workflow.send_responses_streaming(responses))

        if final_output is None and not pending_requests:
            logger.warning(
                "Workflow reached an idle state without producing a final notification or pending analyst review."
            )

        logger.info("\n" + "=" * 80)
        logger.info("Workflow completed successfully!" if final_output else "Workflow ended without final output.")
        if final_output:
            logger.info(
                "Final notification: alert_id=%s customer_id=%s resolution=%s",
                final_output.alert_id,
                final_output.customer_id,
                final_output.resolution,
            )
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"[Error] Workflow failed: {e}", exc_info=True)

    finally:
        # Cleanup
        await mcp_tool.__aexit__(None, None, None)
        logger.info("[Cleanup] MCP connection closed")


if __name__ == "__main__":
    asyncio.run(main())
