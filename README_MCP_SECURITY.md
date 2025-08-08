# APIM + MCP Security (Optional)

This document explains how to secure the User → App (Frontend) → Backend → Agent (Semantic Kernel) → MCP Server path with Azure API Management (APIM) and Microsoft Entra ID. The same pattern works for other agent implementations once the backend forwards the bearer token and the agent/plugin includes it in outbound calls.

---

## High‑level flow

1) User signs in from the Streamlit frontend via MSAL (device code flow) requesting the MCP API scope (example: api://<mcp-api-app-id>/contoso.mcp.fullaccess).
2) Frontend sends requests to the backend including Authorization: Bearer <access_token>.
3) Backend validates the token against Azure AD JWKS (audience and optional scope), then passes the token to the Semantic Kernel Agent.
4) The SK Agent attaches the same Authorization header when calling the MCP server through APIM using MCPStreamableHttpPlugin (SSE/HTTP).
5) APIM validate-jwt checks the incoming token and optionally forwards Authorization to the MCP upstream. It can also set headers like X-Principal-Id based on token claims.

---

## Components and files

- Frontend (Streamlit)
  - File: `agentic_ai/applications/frontend.py`
  - Auth helper: `agentic_ai/applications/msal_streamlit.py`
  - Behavior:
    - Acquires a user token via MSAL device code flow.
    - Sends Authorization to backend for chat, history, and reset endpoints.

- Backend (FastAPI)
  - File: `agentic_ai/applications/backend.py`
  - Behavior:
    - Validates JWT with Azure AD JWKS using PyJWT (PyJWKClient).
    - Audience is configurable via `MCP_API_AUDIENCE`.
    - Optional scope enforcement via `REQUIRED_SCOPE`.
    - Propagates token to the SK agent constructor.

- Semantic Kernel Agent (Single Agent)
  - File: `agentic_ai/agents/semantic_kernel/single_agent/chat_agent.py`
  - Behavior:
    - Accepts `access_token` from backend.
    - Adds `Authorization: Bearer <token>` to `MCPStreamableHttpPlugin` headers.

- MCP Server (FastMCP)
  - File: `agentic_ai/backend_services/mcp_service.py`
  - Behavior:
    - Exposes tools over HTTP/SSE (no direct auth), protected by APIM at the edge.

- APIM policy
  - File: `agentic_ai/applications/apim_inbound_policy.xml`
  - Behavior:
    - CORS for the frontend origin.
    - `validate-jwt` with tenant, audience, and required scope.
    - Forwards `Authorization` downstream and sets `X-Principal-Id` claim.

---

## Azure AD app registrations

You need two apps in the same tenant:

1) API app (protects MCP via APIM)
   - Expose an API with an App ID URI: `api://<mcp-api-app-id>`.
   - Add a scope: `contoso.mcp.fullaccess`.

2) Frontend public client (Streamlit)
   - Type: public client (desktop/native).
   - Allow device code flow.
   - Add API permission to the above API scope (admin consent if required).

Note the following identifiers:
- Tenant ID: AAD_TENANT_ID
- Frontend Client ID: CLIENT_ID
- API App ID URI: MCP_API_AUDIENCE (e.g., `api://<mcp-api-app-id>`)
- Full scope to request from the frontend: `api://<mcp-api-app-id>/contoso.mcp.fullaccess`

---

## APIM configuration

- Create (or update) an API that fronts your MCP server (FastMCP) upstream.
- Import the policy from `agentic_ai/applications/apim_inbound_policy.xml`.
  - Parameterize named values: `aad-tenant-id`, `mcp-app-id-uri`, `required-scope`.
  - Add your frontend origin(s) to the CORS list.
- Ensure a route points to your MCP SSE/HTTP endpoint (e.g., `/mcp` or `/sse`).
- If using subscription keys on the same API, either disable keys or handle them alongside JWT.

---

## Environment configuration

Application `.env` (in `agentic_ai/applications/`):

- AAD_TENANT_ID="<tenant-guid>"
- CLIENT_ID="<frontend-public-client-id>"
- MCP_API_AUDIENCE="api://<mcp-api-app-id>"
- REQUIRED_SCOPE="contoso.mcp.fullaccess"
- BACKEND_URL="http://localhost:7000"
- MCP_SERVER_URI="https://<your-apim-gateway>/mcp/sse"   # match your APIM route
- Azure OpenAI settings…
- AGENT_MODULE="agents.semantic_kernel.single_agent.chat_agent"

Streamlit secrets (`.streamlit/secrets.toml`):

- MCP_SCOPE = "api://<mcp-api-app-id>/contoso.mcp.fullaccess"

MCP local (if running FastMCP locally):

- Start FastMCP (defaults to `http://localhost:8000`).
- Configure APIM to forward from a public path to this upstream.

---

## Quick start

1) Create the two Entra apps (API + frontend) and grant the frontend permission to the API scope.
2) Configure APIM policy and backend route to your MCP upstream.
3) Fill in `.env` and Streamlit secrets with tenant, client id, audience, and scope.
4) Run the MCP service locally (or ensure your upstream is reachable).
5) Start backend (`uvicorn ...` or the VS Code task) and Streamlit frontend.
6) Sign in (device code), then chat. Verify APIM trace shows `validate-jwt` success and upstream calls.

---

## Troubleshooting

- 401 No bearer token: Frontend didn’t send Authorization; ensure you’re signed in.
- 401 Token invalid/audience: `MCP_API_AUDIENCE` mismatch; confirm the API App ID URI matches what the token was issued for.
- 403 Insufficient scope: Scope value in APIM policy and backend `REQUIRED_SCOPE` must match what the frontend requested.
- CORS preflight blocked: Add your frontend origin to APIM CORS policy and include OPTIONS in allowed methods.
- SSE connection issues (502/504): Confirm `MCP_SERVER_URI` targets the APIM route that maps to the SSE endpoint and that APIM timeout settings are sufficient.

---

## Notes

- This guide documents the SK single‑agent path, but the model applies to other agents as long as the backend forwards the token and the agent/plugin sets the Authorization header on MCP calls.
- Keep APIM policy and backend audience/scope settings in sync with your Entra app registration values.
