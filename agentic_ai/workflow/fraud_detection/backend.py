"""
FastAPI backend for Fraud Detection Workflow Visualization.

Provides REST API endpoints and WebSocket for real-time workflow event streaming.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from fraud_detection_workflow import (
    AnalystDecision,
    SuspiciousActivityAlert,
    create_fraud_detection_workflow,
)
from agent_framework import (
    FileCheckpointStorage,
    MCPStreamableHTTPTool,
    ExecutorInvokedEvent,
    ExecutorCompletedEvent,
    WorkflowOutputEvent,
    WorkflowStatusEvent,
    RequestInfoEvent,
    RequestInfoExecutor,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, force=True)
logger = logging.getLogger(__name__)

# Keep agent_framework at INFO level
logging.getLogger("agent_framework").setLevel(logging.INFO)

# FastAPI app
app = FastAPI(title="Fraud Detection Workflow API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],  # React dev servers
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Exception Handlers
# ============================================================================


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log validation errors for debugging."""
    try:
        body = await request.body()
        body_str = body.decode('utf-8')
    except Exception:
        body_str = "<unable to read body>"
    
    logger.error(f"Validation error on {request.url}: {exc.errors()}")
    logger.error(f"Request body: {body_str}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "body": body_str},
    )


# ============================================================================
# Request/Response Models
# ============================================================================


class StartWorkflowRequest(BaseModel):
    """Request to start a workflow with a specific alert."""

    alert_id: str
    customer_id: int
    alert_type: str
    description: str
    severity: str


class AnalystDecisionRequest(BaseModel):
    """Analyst decision submitted from UI."""

    request_id: str
    alert_id: str | None = None  # Optional - tracked via request_id
    customer_id: int | str | None = None  # Optional - tracked via request_id
    approved_action: str
    analyst_notes: str
    analyst_id: str = "analyst_ui"


class WorkflowStatus(BaseModel):
    """Current workflow status."""

    status: str
    current_executor: str | None = None
    pending_requests: list[dict[str, Any]] = []


# ============================================================================
# Global State
# ============================================================================

# Store active workflows and their states
active_workflows: dict[str, Any] = {}  # Stores workflow state AND the workflow instance
workflow_events: dict[str, list[dict[str, Any]]] = {}
pending_decisions: dict[str, dict[str, Any]] = {}
pending_request_events: dict[str, RequestInfoEvent] = {}

# WebSocket connections
active_connections: list[WebSocket] = []

# Pre-initialized resources (created once on startup)
mcp_tool: MCPStreamableHTTPTool | None = None
chat_client: AzureOpenAIChatClient | None = None
checkpoint_storage: FileCheckpointStorage | None = None


# ============================================================================
# WebSocket Connection Manager
# ============================================================================


class ConnectionManager:
    """Manages WebSocket connections for real-time event streaming."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        if not self.active_connections:
            logger.warning(f"No active WebSocket connections to broadcast to. Message type: {message.get('type', 'unknown')}")
            return
            
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to WebSocket: {e}")
                disconnected.append(connection)

        # Remove disconnected clients
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


# ============================================================================
# Sample Alerts
# ============================================================================

SAMPLE_ALERTS = {
    "ALERT-001": SuspiciousActivityAlert(
        alert_id="ALERT-001",
        customer_id=1,
        alert_type="multi_country_login",
        description="Login attempts from USA and Russia within 2 hours",
        timestamp=datetime.now().isoformat(),
        severity="high",
    ),
    "ALERT-002": SuspiciousActivityAlert(
        alert_id="ALERT-002",
        customer_id=2,
        alert_type="data_spike",
        description="Data usage increased by 500% in last 24 hours",
        timestamp=datetime.now().isoformat(),
        severity="medium",
    ),
    "ALERT-003": SuspiciousActivityAlert(
        alert_id="ALERT-003",
        customer_id=3,
        alert_type="unusual_charges",
        description="Three large purchases totaling $5,000 in 10 minutes",
        timestamp=datetime.now().isoformat(),
        severity="high",
    ),
}


def _serialize_analyst_request(event: RequestInfoEvent) -> dict[str, Any]:
    """Convert a RequestInfoEvent into a UI-friendly payload."""
    from dataclasses import is_dataclass, asdict

    request_data = getattr(event, "data", None)
    assessment = getattr(request_data, "assessment", None)

    def serialize_assessment(data: Any) -> dict[str, Any]:
        if data is None:
            return {}
        # Handle dataclasses first (FraudRiskAssessment is a dataclass)
        if is_dataclass(data):
            return asdict(data)
        # Handle Pydantic models
        if hasattr(data, "model_dump"):
            return data.model_dump()
        if hasattr(data, "dict"):
            return data.dict()
        return {}

    assessment_payload = serialize_assessment(assessment)

    return {
        "request_id": event.request_id,
        "alert_id": assessment_payload.get("alert_id") or getattr(request_data, "alert_id", None),
        "customer_id": assessment_payload.get("customer_id"),
        "risk_score": assessment_payload.get("overall_risk_score", 0.0),
        "risk_level": assessment_payload.get("risk_level"),
        "recommended_action": assessment_payload.get("recommended_action"),
        "reasoning": assessment_payload.get("reasoning", ""),
        "analysis_summaries": assessment_payload.get("analysis_summaries", []),
        "prompt": getattr(request_data, "prompt", ""),
    }


async def cleanup_checkpoints(workflow_id: str | None):
    """Clean up checkpoint files for a completed workflow."""
    if not checkpoint_storage or not workflow_id:
        return
    
    try:
        import pathlib
        checkpoint_dir = pathlib.Path("./checkpoints")
        if not checkpoint_dir.exists():
            return
        
        # List all checkpoints for this workflow
        checkpoints = await checkpoint_storage.list_checkpoints(workflow_id=workflow_id)
        deleted_count = 0
        
        for checkpoint in checkpoints:
            try:
                checkpoint_file = checkpoint_dir / f"{checkpoint.checkpoint_id}.json"
                if checkpoint_file.exists():
                    checkpoint_file.unlink()
                    deleted_count += 1
            except Exception as e:
                logger.warning(f"Failed to delete checkpoint {checkpoint.checkpoint_id}: {e}")
        
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} checkpoint file(s) for workflow {workflow_id}")
    except Exception as e:
        logger.error(f"Error cleaning up checkpoints: {e}")


async def _resolve_checkpoint_for_request(alert_id: str, request_id: str) -> tuple[str | None, int | None]:
    """Locate the checkpoint that contains the pending request."""

    if checkpoint_storage is None:
        return None, None

    workflow_state = active_workflows.get(alert_id)
    if not workflow_state:
        return None, None

    workflow_id = workflow_state.get("workflow_id")
    if not workflow_id:
        return None, None

    async def _lookup() -> tuple[str | None, int | None]:
        try:
            checkpoints = await checkpoint_storage.list_checkpoints(workflow_id=workflow_id)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning(
                "Failed to list checkpoints for alert %s (workflow_id=%s): %s",
                alert_id,
                workflow_id,
                exc,
            )
            return None, None

        checkpoints_sorted = sorted(
            checkpoints,
            key=lambda cp: getattr(cp, "timestamp", "") or "",
            reverse=True,
        )

        for checkpoint in checkpoints_sorted:
            try:
                pending_requests = RequestInfoExecutor.pending_requests_from_checkpoint(checkpoint)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.debug(
                    "Unable to inspect checkpoint %s for alert %s: %s",
                    getattr(checkpoint, "checkpoint_id", "<unknown>"),
                    alert_id,
                    exc,
                )
                continue

            for pending in pending_requests:
                if pending.request_id == request_id:
                    return checkpoint.checkpoint_id, pending.iteration

        return None, None

    # Retry multiple times in case the checkpoint is written just after the event
    # The checkpoint is written AFTER the superstep completes, so we need to wait
    max_attempts = 20  # Increased from 10
    for attempt in range(max_attempts):
        checkpoint_id, iteration = await _lookup()
        if checkpoint_id:
            logger.info(
                "Found checkpoint %s for alert %s request %s after %d attempt(s)",
                checkpoint_id,
                alert_id,
                request_id,
                attempt + 1,
            )
            return checkpoint_id, iteration
        if attempt < max_attempts - 1:
            # Exponential backoff: 0.5s, 1s, 1.5s, 2s, 2.5s, etc. (max ~10 seconds total)
            await asyncio.sleep(0.5 * (attempt + 1))
            if attempt % 5 == 4:  # Log every 5 attempts
                logger.debug(
                    "Still waiting for checkpoint for alert %s request %s (attempt %d/%d)",
                    alert_id,
                    request_id,
                    attempt + 1,
                    max_attempts,
                )

    logger.warning(
        "Checkpoint not found for alert %s request %s (workflow_id=%s) after %s attempts (~%.1f seconds)",
        alert_id,
        request_id,
        workflow_state.get("workflow_id"),
        max_attempts,
        sum(0.5 * (i + 1) for i in range(max_attempts)),
    )
    return None, None


# ============================================================================
# API Endpoints
# ============================================================================


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Fraud Detection Workflow API", "status": "running"}


@app.get("/api/alerts")
async def get_sample_alerts():
    """Get list of sample alerts."""
    return {
        "alerts": [
            {
                "alert_id": alert.alert_id,
                "customer_id": alert.customer_id,
                "alert_type": alert.alert_type,
                "description": alert.description,
                "severity": alert.severity,
            }
            for alert in SAMPLE_ALERTS.values()
        ]
    }


@app.post("/api/workflow/start")
async def start_workflow(request: StartWorkflowRequest):
    """Start a new workflow with the specified alert."""
    alert_id = request.alert_id

    # Check if alert exists in samples or create new one
    if alert_id in SAMPLE_ALERTS:
        alert = SAMPLE_ALERTS[alert_id]
    else:
        alert = SuspiciousActivityAlert(
            alert_id=alert_id,
            customer_id=request.customer_id,
            alert_type=request.alert_type,
            description=request.description,
            timestamp=datetime.now().isoformat(),
            severity=request.severity,
        )

    # Initialize workflow events storage
    workflow_events[alert_id] = []
    pending_decisions[alert_id] = {}
    pending_request_events.pop(alert_id, None)

    # Start workflow in background
    asyncio.create_task(run_workflow(alert))

    return {"status": "started", "alert_id": alert_id, "message": "Workflow started successfully"}


@app.post("/api/workflow/decision")
async def submit_decision(decision: AnalystDecisionRequest):
    """Submit analyst decision for pending review."""
    logger.info(f"Received decision request: {decision}")
    request_id = decision.request_id

    # Find the alert_id for this request_id
    alert_id = None
    for aid, pending_info in pending_decisions.items():
        if pending_info.get("request_id") == request_id:
            alert_id = aid
            break
    
    if not alert_id:
        logger.error(f"No pending decision found for request_id {request_id}")
        logger.error(f"Available pending decisions: {list(pending_decisions.keys())}")
        return {"status": "error", "message": f"No pending decision found for request {request_id}"}

    if alert_id not in active_workflows:
        return {"status": "error", "message": f"No active workflow for alert {alert_id}"}

    pending_info = pending_decisions.get(alert_id)
    pending_event = pending_request_events.get(alert_id)
    if not pending_info:
        return {"status": "error", "message": f"No pending analyst review for alert {alert_id}"}

    checkpoint_id = pending_info.get("checkpoint_id")
    if not checkpoint_id:
        checkpoint_id, iteration = await _resolve_checkpoint_for_request(alert_id, request_id)
        if checkpoint_id:
            pending_info["checkpoint_id"] = checkpoint_id
            pending_info["checkpoint_iteration"] = iteration
            workflow_state = active_workflows.get(alert_id)
            if workflow_state is not None:
                workflow_state["pending_checkpoint_id"] = checkpoint_id
                workflow_state["last_checkpoint_id"] = checkpoint_id
        else:
            checkpoint_id = None

    checkpoint_id = pending_info.get("checkpoint_id")

    if not checkpoint_id:
        return {
            "status": "error",
            "message": (
                "No checkpoint available for this decision yet. Please wait a moment and try again, or restart the workflow."
            ),
        }

    # Normalize customer_id to int
    customer_id = decision.customer_id or pending_info.get("customer_id") or 0
    if isinstance(customer_id, str):
        try:
            customer_id = int(customer_id)
        except (ValueError, TypeError):
            customer_id = 0

    # Create AnalystDecision object
    analyst_decision = AnalystDecision(
        alert_id=alert_id,
        customer_id=customer_id,
        approved_action=decision.approved_action,
        analyst_notes=decision.analyst_notes,
        analyst_id=decision.analyst_id,
    )

    responses = {request_id: analyst_decision}

    # Continue workflow execution
    logger.info(f"About to continue workflow for alert {alert_id} with checkpoint {checkpoint_id}")
    logger.info(f"Request ID for response: {request_id}")
    logger.info(f"Analyst decision: {analyst_decision}")
    logger.info(f"Responses dict keys: {list(responses.keys())}")
    task = asyncio.create_task(continue_workflow(alert_id, responses, checkpoint_id=checkpoint_id))
    
    # Add error handler to catch exceptions in the background task
    def task_done_callback(t):
        try:
            t.result()
        except Exception as e:
            logger.error(f"Error in continue_workflow task: {e}", exc_info=True)
    
    task.add_done_callback(task_done_callback)

    return {"status": "submitted", "message": "Decision submitted successfully"}


@app.get("/api/workflow/status/{alert_id}")
async def get_workflow_status(alert_id: str):
    """Get current workflow status."""
    if alert_id not in active_workflows:
        return {"status": "not_found", "message": f"No workflow found for alert {alert_id}"}

    workflow_state = active_workflows[alert_id]
    return {
        "status": workflow_state.get("status", "unknown"),
        "current_executor": workflow_state.get("current_executor"),
        "events": workflow_events.get(alert_id, []),
        "pending_decision": pending_decisions.get(alert_id),
        "pending_checkpoint_id": workflow_state.get("pending_checkpoint_id"),
        "last_checkpoint_id": workflow_state.get("last_checkpoint_id"),
        "workflow_id": workflow_state.get("workflow_id"),
    }


# ============================================================================
# WebSocket Endpoint
# ============================================================================


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time event streaming."""
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and receive any messages from client
            data = await websocket.receive_text()
            logger.info(f"Received from client: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ============================================================================
# Workflow Execution
# ============================================================================


async def run_workflow(alert: SuspiciousActivityAlert):
    """Run the fraud detection workflow and stream events."""
    alert_id = alert.alert_id

    try:
        # Broadcast workflow initialization started
        await manager.broadcast(
            {
                "type": "workflow_initializing",
                "alert_id": alert_id,
                "message": "Initializing workflow...",
                "timestamp": datetime.now().isoformat(),
            }
        )

        logger.info(f"Creating workflow for alert {alert_id}...")

        # Send periodic updates to keep connection alive during initialization
        async def send_progress_updates():
            messages = [
                "Creating workflow graph...",
                "Initializing executors...",
                "Setting up agent tools...",
                "Workflow ready!"
            ]
            for i, msg in enumerate(messages):
                await asyncio.sleep(2)  # Wait 2 seconds between updates
                await manager.broadcast({
                    "type": "workflow_initializing",
                    "alert_id": alert_id,
                    "message": msg,
                    "progress": (i + 1) / len(messages) * 100,
                    "timestamp": datetime.now().isoformat(),
                })

        # Create workflow using pre-initialized resources (this takes time!)
        progress_task = asyncio.create_task(send_progress_updates())
        
        try:
            workflow = await create_fraud_detection_workflow(
                mcp_tool=mcp_tool,
                chat_client=chat_client,
                model=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4"),
                checkpoint_storage=checkpoint_storage,
            )
            progress_task.cancel()  # Stop progress updates
        except asyncio.CancelledError:
            pass

        logger.info(f"✓ Workflow created for alert {alert_id}")

        # Broadcast workflow ready
        await manager.broadcast(
            {
                "type": "workflow_started",
                "alert_id": alert_id,
                "message": "Workflow ready, starting execution...",
                "timestamp": datetime.now().isoformat(),
            }
        )

        # Store workflow reference AND instance
        active_workflows[alert_id] = {
            "status": "running",
            "workflow_id": workflow.id,
            "workflow_instance": workflow,  # Store the workflow instance for reuse
            "current_executor": None,
            "pending_checkpoint_id": None,
            "last_checkpoint_id": None,
        }

        # Small delay to ensure WebSocket connection is fully established
        await asyncio.sleep(0.1)

        # Run workflow and stream events
        async for event in workflow.run_stream(alert):
            await process_event(alert_id, event)

            # Check for human-in-the-loop request
            if isinstance(event, RequestInfoEvent):
                request_payload = _serialize_analyst_request(event)
                checkpoint_id, checkpoint_iteration = await _resolve_checkpoint_for_request(
                    alert_id,
                    event.request_id,
                )

                timestamp = datetime.now().isoformat()

                pending_decisions[alert_id] = {
                    **request_payload,
                    "timestamp": timestamp,
                    "source_executor_id": event.source_executor_id,
                    "checkpoint_id": checkpoint_id,
                    "checkpoint_iteration": checkpoint_iteration,
                }
                pending_request_events[alert_id] = event
                active_workflows[alert_id]["status"] = "awaiting_decision"
                active_workflows[alert_id]["pending_checkpoint_id"] = checkpoint_id
                if checkpoint_id:
                    active_workflows[alert_id]["last_checkpoint_id"] = checkpoint_id
                else:
                    logger.warning(
                        "No checkpoint recorded for alert %s request %s; resume will be unavailable until one is created.",
                        alert_id,
                        event.request_id,
                    )

                await manager.broadcast(
                    {
                        "type": "decision_required",
                        "alert_id": alert_id,
                        "request_id": event.request_id,
                        "data": request_payload,
                        "checkpoint_id": checkpoint_id,
                        "checkpoint_iteration": checkpoint_iteration,
                        "timestamp": timestamp,
                    }
                )

                logger.info(f"Workflow {alert_id} awaiting analyst decision")
                return

        # If we exit the loop naturally, mark as completed
        if alert_id in active_workflows:
            active_workflows[alert_id]["status"] = "completed"
            active_workflows[alert_id]["current_executor"] = None
            active_workflows[alert_id]["pending_checkpoint_id"] = None
        pending_decisions.pop(alert_id, None)
        pending_request_events.pop(alert_id, None)

        await manager.broadcast(
            {
                "type": "workflow_completed",
                "alert_id": alert_id,
                "timestamp": datetime.now().isoformat(),
            }
        )

        logger.info(f"✓ Workflow completed for alert {alert_id}")
        
        # Clean up checkpoint files for this completed workflow
        if alert_id in active_workflows:
            await cleanup_checkpoints(active_workflows[alert_id].get("workflow_id"))

    except Exception as e:
        logger.error(f"Error in workflow execution: {e}", exc_info=True)
        await manager.broadcast(
            {
                "type": "workflow_error",
                "alert_id": alert_id,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
        )


async def continue_workflow(alert_id: str, responses: dict[str, Any], checkpoint_id: str | None = None):
    """Continue workflow execution after analyst decision."""
    logger.info(f"=== continue_workflow called for alert {alert_id} ===")
    logger.info(f"Checkpoint ID: {checkpoint_id}")
    logger.info(f"Responses: {responses}")
    logger.info(f"Active workflows: {list(active_workflows.keys())}")
    
    if alert_id not in active_workflows:
        logger.warning("Attempted to continue unknown workflow for alert %s", alert_id)
        return

    workflow_state = active_workflows[alert_id]
    logger.info(f"Workflow state: {workflow_state}")
    pending_info = pending_decisions.get(alert_id)
    effective_checkpoint_id = checkpoint_id or workflow_state.get("pending_checkpoint_id")
    if not effective_checkpoint_id and pending_info:
        effective_checkpoint_id = pending_info.get("checkpoint_id")

    if not effective_checkpoint_id:
        logger.error("No checkpoint available to resume workflow for alert %s", alert_id)
        await manager.broadcast(
            {
                "type": "workflow_error",
                "alert_id": alert_id,
                "error": "Missing checkpoint for analyst decision",
                "timestamp": datetime.now().isoformat(),
            }
        )
        return

    # Clear pending state before resuming
    pending_decisions.pop(alert_id, None)
    pending_request_events.pop(alert_id, None)
    workflow_state["pending_checkpoint_id"] = None
    workflow_state["last_checkpoint_id"] = effective_checkpoint_id

    try:
        # Create a NEW workflow instance for resuming (like the reference example)
        # The checkpoint contains all the state needed to restore everything
        logger.info(f"Creating new workflow instance for resume")
        workflow = await create_fraud_detection_workflow(
            mcp_tool=mcp_tool,
            chat_client=chat_client,
            model=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4"),
            checkpoint_storage=checkpoint_storage,
        )
        
        workflow_state["workflow_instance"] = workflow
        workflow_state.setdefault("workflow_id", workflow.id)
        workflow_state["status"] = "running"

        # Debug: Check what's in the checkpoint
        checkpoint = await checkpoint_storage.load_checkpoint(effective_checkpoint_id)
        if checkpoint:
            logger.info(f"Checkpoint has {len(checkpoint.executor_states)} executor states")
            analyst_state = checkpoint.executor_states.get("analyst_review", {})
            logger.info(f"analyst_review state keys: {list(analyst_state.keys()) if isinstance(analyst_state, dict) else 'not a dict'}")
            if isinstance(analyst_state, dict):
                shared_state_key = RequestInfoExecutor._PENDING_SHARED_STATE_KEY
                pending_requests = checkpoint.shared_state.get(shared_state_key, {})
                logger.info(f"Pending requests in shared state: {list(pending_requests.keys())}")
        
        logger.info(f"Starting run_stream_from_checkpoint with responses keys: {list(responses.keys())}")
        logger.info(f"Checkpoint ID: {effective_checkpoint_id}")

        # Track request info executors that completed during resume
        completed_request_executors = set()
        
        async for event in workflow.run_stream_from_checkpoint(
            effective_checkpoint_id,
            checkpoint_storage=checkpoint_storage,
            responses=responses,
        ):
            logger.info(f"Event received: {type(event).__name__}")
            
            # Track when analyst_review completes so we can re-broadcast at the end
            if isinstance(event, ExecutorCompletedEvent) and event.executor_id == "analyst_review":
                completed_request_executors.add(event.executor_id)
            
            await process_event(alert_id, event)

            if isinstance(event, RequestInfoEvent):
                # Skip RequestInfoEvents that we already provided responses for
                if event.request_id in responses:
                    logger.info(f"Skipping already-responded RequestInfoEvent {event.request_id}")
                    continue
                request_payload = _serialize_analyst_request(event)
                checkpoint_id_next, checkpoint_iteration = await _resolve_checkpoint_for_request(
                    alert_id,
                    event.request_id,
                )

                timestamp = datetime.now().isoformat()
                pending_decisions[alert_id] = {
                    **request_payload,
                    "timestamp": timestamp,
                    "source_executor_id": event.source_executor_id,
                    "checkpoint_id": checkpoint_id_next,
                    "checkpoint_iteration": checkpoint_iteration,
                }
                pending_request_events[alert_id] = event
                workflow_state["status"] = "awaiting_decision"
                workflow_state["pending_checkpoint_id"] = checkpoint_id_next
                if checkpoint_id_next:
                    workflow_state["last_checkpoint_id"] = checkpoint_id_next
                else:
                    logger.warning(
                        "No checkpoint found after resuming workflow for alert %s request %s",
                        alert_id,
                        event.request_id,
                    )

                await manager.broadcast(
                    {
                        "type": "decision_required",
                        "alert_id": alert_id,
                        "request_id": event.request_id,
                        "data": request_payload,
                        "checkpoint_id": checkpoint_id_next,
                        "checkpoint_iteration": checkpoint_iteration,
                        "timestamp": timestamp,
                    }
                )

                logger.info(f"Workflow {alert_id} awaiting additional analyst decision")
                return

        # Workflow completed
        logger.info(f"Workflow loop finished for alert {alert_id}")
        logger.info(f"Pending decisions remaining: {list(pending_decisions.keys())}")
        
        # If workflow finished without another decision request, mark as completed
        if alert_id not in pending_decisions:
            workflow_state["status"] = "completed"
            logger.info(f"Workflow {alert_id} completed successfully")
            
            # Small delay to ensure all events are sent to UI before completion message
            await asyncio.sleep(0.5)
            
            # Re-broadcast completion for request info executors that may have been missed
            if 'completed_request_executors' in locals() and completed_request_executors:
                for executor_id in completed_request_executors:
                    await manager.broadcast({
                        "alert_id": alert_id,
                        "type": "ExecutorCompletedEvent",
                        "event_type": "executor_completed",
                        "executor_id": executor_id,
                        "timestamp": datetime.now().isoformat(),
                    })
                    logger.info(f"Re-broadcast completion for {executor_id}")
            
            # Broadcast completion to UI
            await manager.broadcast(
                {
                    "type": "workflow_completed",
                    "alert_id": alert_id,
                    "message": "Workflow completed successfully",
                    "timestamp": datetime.now().isoformat(),
                }
            )
            
            # Clean up checkpoint files for this completed workflow
            await cleanup_checkpoints(workflow_state.get("workflow_id"))
            workflow_state["status"] = "awaiting_decision"
        else:
            workflow_state["status"] = "completed"
            workflow_state["current_executor"] = None

            await manager.broadcast(
                {
                    "type": "workflow_completed",
                    "alert_id": alert_id,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            logger.info(f"Workflow {alert_id} completed after resuming checkpoint {effective_checkpoint_id}")

    except Exception as e:
        logger.error(f"Error continuing workflow: {e}", exc_info=True)
        workflow_state["status"] = "error"
        await manager.broadcast(
            {
                "type": "workflow_error",
                "alert_id": alert_id,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }
        )


async def process_event(alert_id: str, event: Any):
    """Process and broadcast workflow event."""
    event_data = {
        "alert_id": alert_id,
        "type": event.__class__.__name__,
        "timestamp": datetime.now().isoformat(),
    }

    if isinstance(event, ExecutorInvokedEvent):
        event_data.update(
            {
                "event_type": "executor_invoked",
                "executor_id": event.executor_id,
            }
        )
        active_workflows[alert_id]["current_executor"] = event.executor_id

    elif isinstance(event, ExecutorCompletedEvent):
        event_data.update(
            {
                "event_type": "executor_completed",
                "executor_id": event.executor_id,
            }
        )
        logger.info(f"Broadcasting executor_completed for {event.executor_id}")

    elif isinstance(event, WorkflowStatusEvent):
        event_data.update(
            {
                "event_type": "status_change",
                "status": str(event.state) if hasattr(event, "state") else "unknown",
            }
        )

    elif isinstance(event, WorkflowOutputEvent):
        event_data.update(
            {
                "event_type": "workflow_output",
                "output": str(event.data) if hasattr(event, "data") else None,
            }
        )

    # Store event
    if alert_id not in workflow_events:
        workflow_events[alert_id] = []
    workflow_events[alert_id].append(event_data)

    # Broadcast to all connected clients
    await manager.broadcast(event_data)


# ============================================================================
# Startup/Shutdown Events
# ============================================================================


@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup."""
    global mcp_tool, chat_client, checkpoint_storage

    logger.info("Initializing backend resources...")

    try:
        # Initialize MCP tool
        mcp_server_uri = os.getenv("MCP_SERVER_URI", "http://localhost:8000/mcp")
        mcp_tool = MCPStreamableHTTPTool(
            name="contoso_mcp",
            url=mcp_server_uri,
            headers={"Content-Type": "application/json"},
            timeout=30,
            request_timeout=30,
        )
        await mcp_tool.__aenter__()
        logger.info(f"✓ MCP tool initialized at {mcp_server_uri}")

        # Initialize Azure OpenAI client
        chat_client = AzureOpenAIChatClient(credential=AzureCliCredential())
        logger.info("✓ Azure OpenAI client initialized")

        # Initialize checkpoint storage
        import pathlib
        checkpoint_dir = pathlib.Path("./checkpoints")
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_storage = FileCheckpointStorage(str(checkpoint_dir))
        logger.info(f"✓ Checkpoint storage initialized at {checkpoint_dir.absolute()}")

        logger.info("Backend ready! 🚀")

    except Exception as e:
        logger.error(f"Failed to initialize backend resources: {e}", exc_info=True)
        raise


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup resources on shutdown."""
    global mcp_tool

    logger.info("Shutting down backend...")

    if mcp_tool:
        try:
            await mcp_tool.__aexit__(None, None, None)
            logger.info("✓ MCP tool cleaned up")
        except Exception as e:
            logger.error(f"Error cleaning up MCP tool: {e}")


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
