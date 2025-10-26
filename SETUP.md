# Part 0: Microsoft AI Agentic Workshop Setup
> Note: Read the Workshop scenario overview [here](SCENARIO.md) before starting the setup.

## Goal
- Clone the repository
- Deploy a Large Language Model (LLM) using Azure AI Foundry
- Configure the applications to use your deployed model and other Azure resources

## Prerequisites for Part 0
- An Azure Account and Subscription
- An understanding of:
    - Azure Subscriptions and Resources
    - Github Mechanics (creating an account, cloning a repo, etc.)

## Steps
[1. Clone the Repository](#1-clone-the-repository)  
[2. Deploy LLM model using Azure AI Foundry](#2-deploy-llm-model-using-azure-ai-foundry)  
[3. Set up your environment variables](#3-set-up-your-environment-variables)

  
### 1. Open Terminal and Clone the Repository

> Open a new terminal window in VS Code or your preferred terminal application:
> ![new terminal](docs/media/01_mcp_open_terminal.png)

In the terminal, run the following command to clone the repository:

```bash 
git clone https://github.com/microsoft/OpenAIWorkshop.git 
```

### 2. Deploy LLM model using Azure AI Foundry

1. Login to **ai.azure.com**. Create account if you don't already have access to an account.
2. Create project, use new hub is none exists. This will setup a hub, project container, AI services, Storage account and Key Vault

    <img src="docs/media/01_foundry_create_hub.jpg"/>

3. On project page, go to **Models + endpoints** -> Deploy model -> Deploy base model -> gpt-4.1
4. Select deployment type **Global Standard** and **Korea Central** region if desired
5. Customize deployment details to reduce tokens per minute to 10k or desired amount
6. Under **Models + endpoints**, select **gpt-4.1** deployment and copy Azure OpenAI Service endpoint and API Key, to add to .env file (next step)

    <img src="docs/media/01_foundry_deploy_gpt4.jpg"/>

  
### 3. Set up your environment variables 
  
Inside of the `agentic_ai/applications` folder, rename `.env.sample` to `.env` and fill in all required fields. Here is a sample configuration:  
  
```bash  
############################################  
#  Azure OpenAI – chat model configuration #  
############################################  
# Replace with your model-deployment endpoint in Azure AI Foundry  
AZURE_OPENAI_ENDPOINT="https://YOUR-OPENAI-SERVICE-ENDPOINT.openai.azure.com"  
  
# Replace with your Foundry project’s API key  
AZURE_OPENAI_API_KEY="YOUR-OPENAI-API-KEY"  
  
# Connection-string that identifies your Foundry project / workspace. Only needed if you're using Azure Agent Service
AZURE_AI_AGENT_PROJECT_CONNECTION_STRING="YOUR-OPENAI-PROJECT-CONNECTION-STRING"  
  
# Model deployment & API version  
AZURE_OPENAI_CHAT_DEPLOYMENT="gpt-4.1"  
AZURE_AI_AGENT_MODEL_DEPLOYMENT_NAME="gpt-4.1" # only needed if you're using Azure Agent Service 
AZURE_OPENAI_API_VERSION="2025-01-01-preview"  
OPENAI_MODEL_NAME="gpt-4.1-2025-04-14"  #only applicable for Autogen
  
############################################  
#     Local URLs for backend & MCP server  #  
############################################  
BACKEND_URL="http://localhost:7000"  
MCP_SERVER_URI="http://localhost:8000/mcp"  
  
############################################  
  
############################################  
#         Agent module to be executed      #  
############################################  
# AGENT_MODULE="agents.autogen.multi_agent.reflection_agent"
# AGENT_MODULE="agents.autogen.single_agent.loop_agent"
# AGENT_MODULE="agents.autogen.multi_agent.collaborative_multi_agent_round_robin"
# AGENT_MODULE="agents.autogen.multi_agent.collaborative_multi_agent_selector_group"
# AGENT_MODULE="agents.autogen.multi_agent.handoff_multi_domain_agent"
# AGENT_MODULE="agents.agent_framework.single_agent"
# AGENT_MODULE="agents.agent_framework.multi_agent.handoff_multi_domain_agent"
# AGENT_MODULE="agents.agent_framework.multi_agent.magentic_group"
# AGENT_MODULE="agents.semantic_kernel.multi_agent.collaborative_multi_agent"
# AGENT_MODULE="agents.semantic_kernel.multi_agent.a2a.collaborative_multi_agent"
AGENT_MODULE="agents.autogen.single_agent.loop_agent"  
  
# -----------------------------------------------------------  
# If you are experimenting with Logistics-A2A, uncomment:  
# LOGISTIC_MCP_SERVER_URI="http://localhost:8100/sse"  
# LOGISTICS_A2A_URL="http://localhost:9100"  
# -----------------------------------------------------------  
  
  
#############################################################  
#          Cosmos DB – state persistence settings           #  
#############################################################  
# Endpoint for your Cosmos DB account (SQL API)  
COSMOSDB_ENDPOINT="https://YOUR-COSMOS-ACCOUNT.documents.azure.com:443/"  
  
# ---------  Choose ONE authentication method  --------------  
# (1) Account key  
#COSMOSDB_KEY="YOUR-COSMOS-ACCOUNT-KEY"  
  
# (2) Azure AD service-principal (preferred in production)  
#AAD_CLIENT_ID="00000000-0000-0000-0000-000000000000"  
#AAD_CLIENT_SECRET="YOUR-AAD-CLIENT-SECRET"  
#AAD_TENANT_ID="11111111-1111-1111-1111-111111111111"  
# -----------------------------------------------------------  
  
# Logical (application) tenant for data isolation  
# Leave as "default" unless you partition data by customer / org  
DATA_TENANT_ID="default"  
  
# Database & container names (created automatically if not present)  
COSMOSDB_DB_NAME="ai_state_db"  
COSMOSDB_CONTAINER_NAME="state_store"  
```
  
#### Choosing a State Store  
  
- **Do nothing** ➜ the workshop uses an in-memory Python `dict` (fast, but data is lost when the process exits).  
- **Fill in the Cosmos variables** ➜ the app automatically switches to an Azure Cosmos DB container with a hierarchical partition-key (`/tenant_id + /id`) so chat history survives restarts and scales across instances.  
  
If neither `COSMOSDB_KEY` nor the AAD credential set is provided, the code silently falls back to the in-memory store.  
> **Important:**    
>
> If you choose Cosmos DB and use Azure AD service-principal authentication, you must grant the service principal a custom role for data plane (read/write) access in Cosmos DB.
>
> **See**: [Grant data plane access using custom roles in Azure Cosmos DB](https://learn.microsoft.com/en-us/azure/cosmos-db/nosql/how-to-grant-data-plane-access?tabs=custom-definition%2Ccsharp&pivots=azure-interface-cli)  
>  
> Without this role, the application will not be able to access or persist chat history in Cosmos DB using Azure AD authentication.  

### 4. Deploy embedding model using Azure AI Foundry

1. In the same project, go to **Models + endpoints** -> Deploy model -> Deploy base model -> text-embedding-ada-002
2. Select deployment type **Global Standard** and **Korea Central** region if desired
3. Customize deployment details to reduce tokens per minute to 10k or desired amount
4. Under **Models + endpoints**, select **text-embedding-ada-002** deployment. Copy Azure OpenAI Service endpoint and API Key to add to .env file (next step)

    <img src="docs/media/01_foundry_deploy_embedding.jpg"/>

5. In your source repo, from the root folder, navigate to the `mcp` folder, rename `.env.sample` to `.env`, and fill in all required fields. Here is a sample configuration:  
  
    ```bash
    # This file is a sample configuration for the MCP backend services's knowledge retrieval APIs which uses text-embedding-ada-002 embedding model
    AZURE_OPENAI_ENDPOINT="YOUR-OPENAI-SERVICE-ENDPOINT.openai.azure.com"
    AZURE_OPENAI_API_KEY="YOUR-OPENAI-API-KEY"
    AZURE_OPENAI_API_VERSION=2025-03-01-preview
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT="text-embedding-ada-002"
    DB_PATH="data/contoso.db"
    AAD_TENANT_ID=""
    MCP_API_AUDIENCE=""
    MCP_SERVER_URI="http://localhost:8000/mcp"
    DISABLE_AUTH="true"
    ```


**Make sure your Azure resources are configured to use the correct model deployment names, endpoints, and API versions.**
  
---

## Next Step: Running MCP Server

Once your `.env` files are configured, you can start the MCP server. 
- Click here for [MCP setup instructions using uv](docs/01_mcp_uv.md).
- Click here for [MCP setup instructions using traditional method](docs/01_mcp_pip.md).
