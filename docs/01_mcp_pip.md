# Microsoft AI Agentic Workshop MCP Setup

Previous step: [SETUP.md](../SETUP.md)

### 1. Install Python dependencies  
If you prefer the traditional approach or don't want to install `uv`, start by creating and activating a virtual environment, then install the dependencies using `pip`.:

##### Activate virtual environment:
**Windows:**

```bash

python -m venv venv
venv\Scripts\activate
```
**macOS/Linux:**
```bash 
# Creating and activating virtual environment on macOS/Linux
python -m venv venv
source venv/bin/activate
```

##### Install dependencies:
```bash
# Install dependencies from `agentic_ai/applications`
cd agentic_ai/applications
pip install -r requirements.txt  
```

#### 2. Run MCP Server


Note: If you are currently in the `agentic_ai/applications` folder, go back to the root folder first:
```bash
cd ../..
```
Navigate to the `mcp` folder and start the MCP server:
```bash
cd mcp
# Make sure your virtual environment is activated
python mcp_service.py
# Keep this terminal open; open another terminal for the next step.
```

**Next Step**: [Run the Backend Application](02_backend_pip.md)