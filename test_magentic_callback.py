"""
Minimal test to verify Magentic callback mechanism works.
This will help diagnose if the issue is with our code or the agent framework version.
"""
import asyncio
import os
import sys
from pathlib import Path

# Add agentic_ai to path
sys.path.insert(0, str(Path(__file__).parent / "agentic_ai"))

from dotenv import load_dotenv

from agent_framework import (
    ChatAgent,
    MagenticBuilder,
    MagenticCallbackEvent,
    MagenticCallbackMode,
    MagenticOrchestratorMessageEvent,
    MagenticAgentDeltaEvent,
    MagenticAgentMessageEvent,
    MagenticFinalResultEvent,
    WorkflowOutputEvent,
)
from agent_framework.azure import AzureOpenAIChatClient

load_dotenv("agentic_ai/applications/.env")

CALLBACK_INVOCATION_COUNT = 0

async def test_callback(event: MagenticCallbackEvent) -> None:
    """Test callback to verify it's being invoked."""
    global CALLBACK_INVOCATION_COUNT
    CALLBACK_INVOCATION_COUNT += 1
    print(f"[CALLBACK #{CALLBACK_INVOCATION_COUNT}] Event type: {type(event).__name__}")
    
    if isinstance(event, MagenticOrchestratorMessageEvent):
        print(f"  - Orchestrator: {event.kind}")
    elif isinstance(event, MagenticAgentDeltaEvent):
        print(f"  - Agent delta: {event.agent_id}, text={event.text[:50] if event.text else ''}")
    elif isinstance(event, MagenticAgentMessageEvent):
        print(f"  - Agent message: {event.agent_id}")
    elif isinstance(event, MagenticFinalResultEvent):
        print(f"  - Final result")


async def main():
    print("=== Magentic Callback Test ===\n")
    
    # Create chat client
    chat_client = AzureOpenAIChatClient(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        deployment_name=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT"),
        endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    )
    
    # Create two simple participants
    agent1 = ChatAgent(
        name="agent1",
        chat_client=chat_client,
        instructions="You are a helpful assistant. Answer briefly.",
        model="gpt-4o",
    )
    
    agent2 = ChatAgent(
        name="agent2",
        chat_client=chat_client,
        instructions="You are another helpful assistant. Answer briefly.",
        model="gpt-4o",
    )
    
    # Initialize agents
    await agent1.__aenter__()
    await agent2.__aenter__()
    
    print("Building workflow with callback...")
    
    # Build workflow with streaming callback
    workflow = (
        MagenticBuilder()
        .participants(agent1=agent1, agent2=agent2)
        .on_event(test_callback, mode=MagenticCallbackMode.STREAMING)
        .with_standard_manager(
            chat_client=chat_client,
            max_round_count=3,
            max_stall_count=2,
            max_reset_count=1,
        )
        .build()
    )
    
    print("Workflow built successfully!")
    print("\nRunning workflow with simple task...\n")
    
    task = "What is 2+2? Agent1 should answer, then Agent2 should verify."
    
    try:
        async for event in workflow.run_stream(task):
            if isinstance(event, WorkflowOutputEvent):
                print(f"\n[WORKFLOW OUTPUT] {event.data}\n")
        
        print(f"\n=== Test Complete ===")
        print(f"Total callback invocations: {CALLBACK_INVOCATION_COUNT}")
        
        if CALLBACK_INVOCATION_COUNT == 0:
            print("❌ PROBLEM: Callback was NEVER invoked!")
            print("   This suggests the agent framework version doesn't support callbacks properly.")
        else:
            print(f"✅ SUCCESS: Callback was invoked {CALLBACK_INVOCATION_COUNT} times")
            
    except Exception as e:
        print(f"❌ Error running workflow: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
