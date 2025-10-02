# Part 1: MCP Set Up

## Pre-requisites
- Complete [Part 0](../SETUP.md)

## Summary
In this part, you will set up the MCP (Model Control Protocol) for the Microsoft AI Agentic Workshop. This involves installing the necessary Python dependencies and running the MCP server.

If you prefer the traditional approach or don't want to install `uv`, start by creating and activating a virtual environment, then install the dependencies using `pip`. If you'd prefer to use `uv`, follow the instructions found in the [uv version of this guide](/01_mcp_uv.md).
 ## Steps
1. Install Python dependencies  

    > **Action Items:**
    > Activate virtual environment:
    >
    > Windows:
    > 
    ```bash

    python -m venv venv
    venv\Scripts\activate
    ```
    > macOS/Linux:
    ```bash 
    python -m venv venv
    source venv/bin/activate
    ```

2. Install dependencies:
    > **Action Items**:
    > Navigate to the `agentic_ai/applications` folder and install the required packages:
    ```bash
    cd agentic_ai/applications
    pip install -r requirements.txt
    ```
3. Run MCP Server
    > **Action Items**:
    > Ensure your virutal environment is activated.
    > - Note: If you are currently in the `agentic_ai/applications` folder, go back to the root folder first:
    ```bash
    cd ../..
    ```
    > Navigate to the `mcp` folder and start the MCP server with the follwing command:
    ```bash
    cd mcp
    python mcp_service.
    ```
    > Note: Let the MCP server run in this terminal window. Open a new terminal window to proceed to the next step. 
## Success criteria
- MCP server is running and ready to accept requests.

**Next Step**: [Run the Backend Application](02_backend_pip.md)