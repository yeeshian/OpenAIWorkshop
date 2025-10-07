# Part 1: MCP Set Up

## Pre-requisites
- Complete [Part 0](../SETUP.md)

## Summary
In this part, you will set up the MCP (Model Control Protocol) for the Microsoft AI Agentic Workshop. This involves installing the necessary Python dependencies and running the MCP server.

## Steps
1. Install uv

- ⚡Use `uv` for fastest setup

- [**uv**](https://github.com/astral-sh/uv) is a blazing-fast Python package installer and resolver written in Rust. It's 10-100x faster than `pip` and automatically manages virtual environments.

    > **Action Items:**
    > Install `uv` by running the following command in your terminal:
    > Windows (PowerShell):
    ```bash
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```
    > macOS/Linux:
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

2. Install dependencies with uv:

    > Note: uv automatically creates .venv and installs dependencies from pyproject.toml
    > **Action Items**:
    > Navigate to the `agentic_ai/applications` folder and install the dependencies by running the following command:
    ```bash
    # Navigate to the applications directory
    cd agentic_ai/applications

    # Create virtual environment and install all dependencies in one command
    uv sync
    ```
2. Run MCP Server

    > **Action Items:**
    > Note: If you are currently in the `agentic_ai/applications` folder, go back to the root folder first:
    ```bash
    cd ../..
    ```
    > Navigate to the `mcp` folder and start the MCP server:
    ```bash
    cd mcp
    uv run python mcp_service.py
    ```
    > Note: Let the MCP server run in this terminal window. Open a new terminal window to proceed to the next step. 
## Success criteria
- MCP server is running and ready to accept requests.
- A sample curl command for ensuring the MCP server is online: 
`curl -sS -i -X POST "http://localhost:8000/mcp" -H "Accept: application/json, text/event-stream" -H 'Content-Type: application/json'  --data '{"jsonrpc":"2.0","id":"init-1","method":"initialize", "params":{"protocolVersion":"2024-11-05","capabilities":{}, "clientInfo":{"name":"curl","version":"8"}}}'`

**Alternative**: Use `pip` and `venv` (slower): [Run MCP with pip](01_mcp_pip.md)

**Next Step**: [Run the Backend Application](02_backend_uv.md)
