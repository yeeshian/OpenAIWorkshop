![alt text](docs/media/image-1.png)
# Microsoft AI Agentic Workshop Repository  
  
Welcome to the official repository for the Microsoft AI Agentic Workshop! This repository provides all the resources, code, and documentation you need to explore, prototype, and compare various agent-based AI solutions using Microsoft's leading AI technologies.  
  
---  
  
## Quick Links  
  
- [Business Scenario and Agent Design](./SCENARIO.md)  
- [Getting Started (Setup Instructions)](./SETUP.md)  
- [System Architecture Overview](./ARCHITECTURE.md)  
- [Data Sets](./DATA.md)  
- [APIM + MCP Security (Optional)](./mcp/MULTI_TENANT_MCP_SECURITY.md)  
- [Code of Conduct](./CODE_OF_CONDUCT.md)  
- [Security Guidelines](./SECURITY.md)  
- [Support](./SUPPORT.md)  
- [License](./LICENSE)  
  
---  
  
## What You Can Do With This Workshop  
  
- **Design and prototype agent solutions** for real-world business scenarios.  
- **Compare single-agent vs. multi-agent** architectures and approaches.  
- **Develop and contrast agent implementations** using different platforms:  
  - **[Microsoft Agent Framework](https://github.com/microsoft/agent-framework)** (NEW!) - Microsoft's latest agentic AI framework with advanced multi-agent orchestration (Magentic workflows, handoffs, checkpointing)  
  - Azure AI Agent Service  
  - Semantic Kernel  
  - Autogen  
  
---  
  
## Key Features  
  
- **🎯 Microsoft Agent Framework Support (NEW!):** Full integration with [Microsoft's Agent Framework](https://github.com/microsoft/agent-framework) featuring:
  - **Now available via pip!** Install with: `pip install agent-framework` or `uv add agent-framework`
  - **Single-agent** with MCP tools and streaming token-by-token responses
  - **Multi-agent Magentic orchestration** with intelligent task delegation and progress tracking
  - **Handoff-based multi-domain agents** for specialized task routing with smart context transfer
  - **Checkpointing and resumable workflows** for long-running agentic tasks
  - **Real-time WebSocket streaming** with internal agent process visibility
  - 📚 **[See detailed pattern guide and documentation →](agentic_ai/agents/agent_framework/README.md)**
  
- **🖥️ Advanced UI Options:**  
  - **React Frontend:** Real-time streaming visualization with agent internal processes, tool calls, orchestrator planning, and turn-by-turn history tracking
  - **Streamlit Frontend:** Simple, elegant chat interface for quick prototyping and demos

- **🔄 Workflow Orchestration (NEW!):** Enterprise-grade workflow capabilities with [comprehensive orchestration patterns](agentic_ai/workflow/):
  - **Pregel-style execution engine** for complex multi-agent coordination
  - **Type-safe messaging** with runtime contract enforcement
  - **Checkpointing & resume** for long-running workflows
  - **Human-in-the-loop** approval patterns with RequestInfoExecutor
  - **Control flow patterns**: Switch/case routing, fan-out/fan-in, conditional edges
  - **Real-time observability**: OpenTelemetry tracing, event streaming, WebSocket updates
  - 🎯 **[Featured Demo: Fraud Detection System](agentic_ai/workflow/fraud_detection/)** - Production-ready workflow with React dashboard
  
- **Configurable LLM Backend:** Use the latest Azure OpenAI GPT models (e.g., GPT-5, GPT-4.1, GPT-4o).  
- **MCP Server Integration:** Advanced tools to enhance agent orchestration and capabilities with Model Context Protocol.  
- **A2A (Agent-to-Agent) Protocol Support:** Enables strict cross-domain, black-box multi-agent collaboration using [Google's A2A protocol](https://github.com/google-a2a/A2A). [Learn more &rarr;](agentic_ai/agents/semantic_kernel/multi_agent/a2a).  
- **Durable Agent Pattern:** Includes a demo of a robust agent that persists its state, survives restarts, and manages long-running workflows. [Learn more &rarr;](agentic_ai/scenarios/durable_agent/README.md)  
- **Flexible Agent Architecture:**  
  - Supports single-agent, multi-agent, or reflection-based agents (selectable via `.env`).  
  - Agents can self-loop, collaborate, reflect, or take on dynamic roles as defined in modules.  
  - Multiple frameworks: Agent Framework, Autogen, Semantic Kernel, Azure AI Agent Service.  
- **Session-Based Chat:** Persistent conversation history for each session.  
- **Full-Stack Application:**  
  - FastAPI backend with WebSocket and RESTful endpoints (chat, reset, history, etc.).  
  - Choice of frontend: React (advanced streaming visualization) or Streamlit (simple chat).  
- **Environment-Based Configuration:** Easily configure the system using `.env` files.  
  
---  
  
## Getting Started  
  
1. Review the [Setup Instructions](./SETUP.md) for environment prerequisites and step-by-step installation.  
2. Explore the [Business Scenario and Agent Design](./SCENARIO.md) to understand the workshop challenge.  
3. Check out the **[Agent Framework Implementation Patterns](agentic_ai/agents/agent_framework/README.md)** to choose the right multi-agent approach (single-agent, Magentic orchestration, or handoff pattern).
4. Try the **[Fraud Detection Workflow Demo](agentic_ai/workflow/fraud_detection/)** to see enterprise orchestration patterns in action.
5. Dive into [System Architecture](./ARCHITECTURE.md) before building and customizing your agent solutions.  
6. Utilize the [Support Guide](./SUPPORT.md) for troubleshooting and assistance.  
  
---  
  
## Contributing  
  
Please review our [Code of Conduct](./CODE_OF_CONDUCT.md) and [Security Guidelines](./SECURITY.md) before contributing.  
  
---  
  
## License  
  
This project is licensed under the terms described in the [LICENSE](./LICENSE) file.  
  
