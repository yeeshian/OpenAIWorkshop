# Microsoft AI Agentic Workshop MCP Setup

Previous step: [SETUP.md](../SETUP.md)

### 1. Install Python dependencies  

#### ⚡Use `uv` for fastest setup

[**uv**](https://github.com/astral-sh/uv) is a blazing-fast Python package installer and resolver written in Rust. It's 10-100x faster than `pip` and automatically manages virtual environments.

#### Install uv:
**Windows (PowerShell)**:
```bash
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```
**macOS/Linux**:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

#### Setup dependencies with uv:
Note: uv automatically creates .venv and installs dependencies from pyproject.toml
```bash
# Navigate to the applications directory
cd agentic_ai/applications

# Create virtual environment and install all dependencies in one command
uv sync
```
#### 2. Run MCP Server


Note: If you are currently in the `agentic_ai/applications` folder, go back to the root folder first:
```bash
cd ../..
```
Navigate to the `mcp` folder and start the MCP server:
```bash
cd mcp
uv run python mcp_service.py
# Keep this terminal open; open another terminal for the next step.
```

**Alternative**: Use `pip` and `venv` (slower): [Run MCP with pip](mcp_traditional.md)

**Next Step**: [Run the Backend Application](02_backend_uv.md)